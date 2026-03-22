"""
Natural Language Querying — AI-powered infrastructure queries for PULSE.

Users can ask questions like:
  "show me slow endpoints in the last hour"
  "which nodes have high CPU?"
  "what caused the last incident?"
  "are there any disk space issues?"

Uses OpenAI GPT to interpret the query, maps it to PULSE API calls,
and returns a structured, human-readable answer.
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from openai import AsyncOpenAI

# ── OpenAI client ────────────────────────────────────────────────────────────

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key and api_key != "sk-...":
            _client = AsyncOpenAI(api_key=api_key)
    return _client


# ── Data gathering functions ─────────────────────────────────────────────────

async def _gather_context(db) -> dict:
    """Gather current system state for the AI to reason about."""
    from sqlalchemy import select, func, desc
    from db import Node, Metric, Alert, Incident, Log, Span

    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)

    # Nodes
    nodes = (await db.execute(select(Node).order_by(Node.last_seen.desc()))).scalars().all()
    node_list = [{"id": n.id, "hostname": n.hostname, "ip": n.ip, "os": n.os, "status": n.status,
                  "last_seen": n.last_seen.isoformat()} for n in nodes]

    # Recent metrics (last reading per node)
    from main import _recent_metrics
    latest_metrics = {}
    for node_id, metrics in _recent_metrics.items():
        if metrics:
            latest_metrics[node_id] = metrics[-1]

    # Open alerts
    alerts = (await db.execute(
        select(Alert).where(Alert.resolved == False).order_by(Alert.ts.desc()).limit(20)
    )).scalars().all()
    alert_list = [{"id": a.id, "node_id": a.node_id, "rule_name": a.rule_name,
                   "severity": a.severity, "message": a.message, "ts": a.ts.isoformat()} for a in alerts]

    # Recent incidents
    incidents = (await db.execute(
        select(Incident).order_by(Incident.ts.desc()).limit(10)
    )).scalars().all()
    incident_list = [{"id": i.id, "node_id": i.node_id, "title": i.title, "severity": i.severity,
                      "status": i.status, "ts": i.ts.isoformat(),
                      "rca_summary": i.rca.get("root_cause", "") if i.rca else ""} for i in incidents]

    # Synthetic monitoring
    from synthetic import get_synthetic_results
    synthetic = get_synthetic_results()

    # Anomalies
    from anomaly import get_recent_anomalies
    anomalies = get_recent_anomalies(limit=20)

    # SLO status
    from slo import get_slo_status
    slo_status = get_slo_status()

    # Predictions
    from predict import get_predictions
    predictions = get_predictions(limit=10)

    return {
        "timestamp": now.isoformat(),
        "nodes": node_list,
        "latest_metrics": latest_metrics,
        "open_alerts": alert_list,
        "recent_incidents": incident_list,
        "synthetic_probes": synthetic,
        "recent_anomalies": anomalies,
        "slo_status": {k: {"status": v.get("status"), "compliance": v.get("compliance")}
                       for k, v in slo_status.items()} if slo_status else {},
        "predictions": predictions,
    }


# ── Query execution ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are PULSE AI Assistant — an expert infrastructure monitoring analyst.
You have access to real-time system data including nodes, metrics, alerts, incidents, synthetic probes, anomalies, SLOs, and predictive forecasts.

When answering questions:
1. Be concise and direct — infrastructure engineers want facts, not fluff
2. Reference specific node IDs, metric values, and timestamps
3. If there's a problem, state the severity and recommended action
4. Use tables or bullet points for clarity when listing multiple items
5. If the data doesn't contain enough info to answer, say so clearly

Format your response as JSON with these fields:
{
  "answer": "your natural language answer",
  "summary": "one-line summary",
  "data": [...optional structured data relevant to the answer...],
  "severity": "info|warning|critical" (overall assessment),
  "suggestions": ["optional action items"]
}"""


async def execute_query(question: str, db) -> dict:
    """Execute a natural language query against PULSE data."""
    client = _get_client()
    if not client:
        return await _local_query(question, db)

    # Gather context
    context = await _gather_context(db)

    try:
        response = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Current system state:\n```json\n{json.dumps(context, default=str)}\n```\n\nQuestion: {question}"},
            ],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        result["query"] = question
        result["ts"] = datetime.utcnow().isoformat()
        result["source"] = "ai"
        return result

    except Exception as e:
        print(f"[NLQuery] OpenAI error: {e}, falling back to local")
        return await _local_query(question, db)


async def _local_query(question: str, db) -> dict:
    """Fallback query handler when OpenAI is unavailable — pattern matching."""
    q = question.lower()
    context = await _gather_context(db)

    # Pattern: node/status questions
    if any(w in q for w in ["nodes", "servers", "hosts", "machines"]):
        nodes = context["nodes"]
        total = len(nodes)
        active = sum(1 for n in nodes if n.get("status") == "active")
        return {
            "answer": f"There are {total} monitored nodes, {active} active.",
            "summary": f"{total} nodes, {active} active",
            "data": nodes,
            "severity": "info",
            "query": question, "ts": datetime.utcnow().isoformat(), "source": "local",
        }

    # Pattern: CPU/memory/disk questions
    if any(w in q for w in ["cpu", "memory", "disk", "load", "resource"]):
        metrics = context["latest_metrics"]
        high_cpu = [(nid, m) for nid, m in metrics.items() if m.get("cpu_percent", 0) > 70]
        high_mem = [(nid, m) for nid, m in metrics.items() if m.get("memory_percent", 0) > 80]
        high_disk = [(nid, m) for nid, m in metrics.items() if m.get("disk_percent", 0) > 80]

        issues = []
        if high_cpu:
            issues.append(f"{len(high_cpu)} node(s) with CPU > 70%: {', '.join(n for n, _ in high_cpu)}")
        if high_mem:
            issues.append(f"{len(high_mem)} node(s) with Memory > 80%: {', '.join(n for n, _ in high_mem)}")
        if high_disk:
            issues.append(f"{len(high_disk)} node(s) with Disk > 80%: {', '.join(n for n, _ in high_disk)}")

        if issues:
            answer = "Resource concerns:\n" + "\n".join(f"- {i}" for i in issues)
            severity = "warning"
        else:
            answer = "All nodes are within normal resource limits."
            severity = "info"

        return {
            "answer": answer, "summary": f"{len(issues)} resource concerns",
            "data": metrics, "severity": severity,
            "query": question, "ts": datetime.utcnow().isoformat(), "source": "local",
        }

    # Pattern: alerts
    if any(w in q for w in ["alert", "alarm", "warning", "critical"]):
        alerts = context["open_alerts"]
        if alerts:
            answer = f"{len(alerts)} open alerts:\n" + "\n".join(
                f"- [{a['severity'].upper()}] {a['rule_name']} on {a['node_id']}: {a['message']}" for a in alerts[:10]
            )
            severity = "critical" if any(a["severity"] == "critical" for a in alerts) else "warning"
        else:
            answer = "No open alerts. All systems normal."
            severity = "info"

        return {
            "answer": answer, "summary": f"{len(alerts)} open alerts",
            "data": alerts, "severity": severity,
            "query": question, "ts": datetime.utcnow().isoformat(), "source": "local",
        }

    # Pattern: incidents
    if any(w in q for w in ["incident", "outage", "down", "problem", "issue", "cause", "rca"]):
        incidents = context["recent_incidents"]
        if incidents:
            latest = incidents[0]
            answer = f"Most recent incident: [{latest['severity'].upper()}] {latest['title']} on {latest['node_id']} ({latest['status']})"
            if latest.get("rca_summary"):
                answer += f"\nRoot cause: {latest['rca_summary']}"
            if len(incidents) > 1:
                answer += f"\n\n{len(incidents)} total recent incidents."
        else:
            answer = "No recent incidents."

        return {
            "answer": answer, "summary": f"{len(incidents)} recent incidents",
            "data": incidents, "severity": "info",
            "query": question, "ts": datetime.utcnow().isoformat(), "source": "local",
        }

    # Pattern: synthetic/uptime
    if any(w in q for w in ["synthetic", "uptime", "probe", "endpoint", "url", "health"]):
        probes = context["synthetic_probes"]
        up = sum(1 for p in probes if p.get("status") == "up")
        down = [p for p in probes if p.get("status") != "up"]
        if down:
            answer = f"{up}/{len(probes)} probes UP. Down: {', '.join(p.get('id','?') for p in down)}"
            severity = "critical"
        else:
            answer = f"All {len(probes)} synthetic probes are UP."
            severity = "info"

        return {
            "answer": answer, "summary": f"{up}/{len(probes)} probes UP",
            "data": probes, "severity": severity,
            "query": question, "ts": datetime.utcnow().isoformat(), "source": "local",
        }

    # Pattern: anomaly
    if any(w in q for w in ["anomaly", "anomalies", "unusual", "abnormal", "spike"]):
        anomalies = context["recent_anomalies"]
        if anomalies:
            answer = f"{len(anomalies)} recent anomalies detected:\n" + "\n".join(
                f"- {a.get('metric','')} on {a.get('node_id','')}: z-score {a.get('z_score','?')}" for a in anomalies[:10]
            )
            severity = "warning"
        else:
            answer = "No anomalies detected recently."
            severity = "info"

        return {
            "answer": answer, "summary": f"{len(anomalies)} anomalies",
            "data": anomalies, "severity": severity,
            "query": question, "ts": datetime.utcnow().isoformat(), "source": "local",
        }

    # Pattern: SLO
    if any(w in q for w in ["slo", "sla", "objective", "compliance", "error budget"]):
        slos = context.get("slo_status", {})
        if slos:
            breached = [k for k, v in slos.items() if v.get("status") == "breached"]
            if breached:
                answer = f"{len(breached)} SLO(s) breached: {', '.join(breached)}"
                severity = "critical"
            else:
                answer = f"All {len(slos)} SLOs are being met."
                severity = "info"
        else:
            answer = "No SLOs configured."
            severity = "info"

        return {
            "answer": answer, "summary": f"SLO status: {len(slos)} tracked",
            "data": slos, "severity": severity,
            "query": question, "ts": datetime.utcnow().isoformat(), "source": "local",
        }

    # Default: general status
    nodes = len(context["nodes"])
    alerts = len(context["open_alerts"])
    incidents = len(context["recent_incidents"])
    return {
        "answer": f"PULSE status: {nodes} nodes monitored, {alerts} open alerts, {incidents} recent incidents. Try asking about specific topics like CPU, alerts, incidents, or SLOs.",
        "summary": f"{nodes} nodes, {alerts} alerts",
        "data": {}, "severity": "info",
        "query": question, "ts": datetime.utcnow().isoformat(), "source": "local",
    }
