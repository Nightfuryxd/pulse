"""
PULSE Root Cause Analysis Engine

Uses AI (GPT-4o or local Ollama for air-gapped) + Company Knowledge Base
to produce deep, specific, actionable root cause analysis.

The KB context ensures the AI knows about YOUR company's infrastructure,
past incidents, and known fixes — not just generic advice.
"""
import json
import os
from datetime import datetime


def _get_client():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        from openai import OpenAI
        return OpenAI(api_key=api_key), "openai"
    ollama_url = os.getenv("OLLAMA_URL", "")
    if ollama_url:
        from openai import OpenAI
        return OpenAI(base_url=f"{ollama_url}/v1", api_key="ollama"), "ollama"
    return None, "none"


async def analyse_incident(
    node_id:         str,
    node_info:       dict,
    alerts:          list[dict],
    recent_metrics:  list[dict],
    recent_events:   list[dict],
    tech_stack:      list[str] | None = None,
    correlation:     dict | None = None,
    topology:        dict | None = None,
) -> dict:
    """
    Run AI root cause analysis enriched with:
    - Correlated alerts across multiple nodes
    - Service topology (blast radius context)
    - Company knowledge base (past incidents + runbooks)
    """
    client, mode = _get_client()
    if not client:
        return _fallback_rca(alerts)

    model = "gpt-4o" if mode == "openai" else os.getenv("OLLAMA_MODEL", "llama3.1")

    # ── Build prompt sections ────────────────────────────────────────────────
    alert_summary = "\n".join(
        f"  [{a['severity'].upper()}] {a.get('rule_name','?')}: {a.get('message','')} (category: {a.get('category','')})"
        for a in alerts
    )

    metrics_summary = ""
    for m in recent_metrics[-5:]:
        metrics_summary += (
            f"  {m.get('ts','')}: CPU={m.get('cpu_percent',0):.1f}% "
            f"MEM={m.get('memory_percent',0):.1f}% "
            f"DISK={m.get('disk_percent',0):.1f}% "
            f"LOAD={m.get('load_avg_1m',0):.2f}\n"
        )

    events_summary = "\n".join(
        f"  [{e.get('ts','')}] {e.get('type','')}: {e.get('message','')}"
        for e in recent_events[-10:]
    ) or "  No recent events"

    stack_str = ", ".join(tech_stack) if tech_stack else "unknown"

    # ── Correlation context ──────────────────────────────────────────────────
    correlation_section = ""
    if correlation and correlation.get("node_count", 0) > 1:
        correlation_section = f"""
CORRELATION CONTEXT (this is NOT isolated to one node):
  Pattern: {correlation.get('pattern', 'unknown')}
  Affected nodes: {', '.join(correlation.get('affected_nodes', []))}
  Total alerts in group: {correlation.get('total_alerts', 1)}
  Timeline: {chr(10).join('  ' + t for t in (correlation.get('timeline_summary') or [])[:5])}
"""

    # ── Topology context ─────────────────────────────────────────────────────
    topology_section = ""
    if topology:
        deps     = topology.get("dependencies", [])[:5]
        dep_strs = [f"{d.get('dst_service','?')} on {d.get('dst_node','?')}" for d in deps]
        blast    = topology.get("blast_radius", {})
        topology_section = f"""
SERVICE TOPOLOGY:
  This node depends on: {', '.join(dep_strs) or 'none detected'}
  Blast radius if this fails: {blast.get('total_affected', 0)} downstream nodes
"""

    # ── Knowledge Base context ───────────────────────────────────────────────
    kb_section = ""
    try:
        from knowledge import search_for_incident, format_for_rca, record_use
        kb_results = search_for_incident(alerts[0] if alerts else {}, recent_events)
        if kb_results:
            kb_section = "\n" + format_for_rca(kb_results[:3])
            for r in kb_results[:3]:
                record_use(str(r.get("id","")))
    except Exception:
        pass

    prompt = f"""You are a senior SRE/SecOps engineer performing root cause analysis on a production incident.

NODE: {node_id} ({node_info.get('hostname', node_id)}) | OS: {node_info.get('os','unknown')} | IP: {node_info.get('ip','unknown')}
TECH STACK: {stack_str}
INCIDENT TIME: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

TRIGGERED ALERTS:
{alert_summary}

RECENT METRICS (last 5 readings):
{metrics_summary or '  No recent metrics'}

RECENT EVENTS (security + system):
{events_summary}
{correlation_section}{topology_section}{kb_section}

Instructions:
- Be specific — reference actual values and timestamps
- If the tech stack is known, give exact shell commands
- If a past incident in the KB matches, reference it and adapt the fix
- If this spans multiple nodes, identify the ROOT cause node
- Distinguish between root cause and symptoms

Respond ONLY as valid JSON:
{{
  "root_cause": "One precise sentence: the fundamental cause",
  "confidence": 0.0,
  "affected_components": ["list of affected services/components"],
  "timeline": "What happened in order — cause then cascade",
  "blast_radius": "What else could fail or is already failing",
  "recommended_actions": ["Immediate step 1", "Immediate step 2", "Short-term fix"],
  "owning_teams": ["from: secops, netops, appdev, dba, infra"],
  "escalate_to": ["teams to loop in but don't own it"],
  "stack_specific_advice": "Exact commands for their stack",
  "severity_assessment": "Why this severity is correct",
  "false_positive_likelihood": "low|medium|high with reason",
  "kb_reference": "Title of any matching KB entry, or null",
  "linked_playbook": "playbook_id to auto-run, or null"
}}"""

    try:
        resp  = client.chat.completions.create(
            model=model,
            max_tokens=2000,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw   = resp.choices[0].message.content
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        result = json.loads(raw[start:end])
        # Normalise confidence to float
        c = result.get("confidence", 0.5)
        if isinstance(c, str):
            result["confidence"] = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(c.lower(), 0.5)
        return result
    except Exception as e:
        print(f"[RCA] AI analysis failed: {e}")
        return _fallback_rca(alerts)


def _fallback_rca(alerts: list[dict]) -> dict:
    categories   = list({a.get("category","unknown") for a in alerts})
    severities   = [a.get("severity","info") for a in alerts]
    top_severity = next((s for s in ["critical","high","medium","low"] if s in severities), "info")
    team_map = {
        "performance": "infra", "cpu": "infra", "memory": "infra", "disk": "infra",
        "security": "secops", "auth": "secops", "network": "netops",
        "application": "appdev", "process": "appdev",
        "database": "dba",
    }
    owning_teams = list({team_map.get(c, "infra") for c in categories})

    # Try KB even without AI
    kb_note = ""
    try:
        from knowledge import search_for_incident, format_for_rca
        kb_results = search_for_incident(alerts[0] if alerts else {})
        if kb_results:
            kb_note = f" | KB match: {kb_results[0].get('title','')}"
    except Exception:
        pass

    return {
        "root_cause":    f"{', '.join(a.get('rule_name','?') for a in alerts[:3])}{kb_note}",
        "confidence":    0.2,
        "affected_components": categories,
        "timeline":      "Alert cluster — AI unavailable (configure OPENAI_API_KEY or OLLAMA_URL)",
        "blast_radius":  "Manual investigation required",
        "recommended_actions": [f"{a.get('rule_name','?')}: {a.get('message','')}" for a in alerts[:3]],
        "owning_teams":  owning_teams,
        "escalate_to":   [],
        "stack_specific_advice": "Set OPENAI_API_KEY or OLLAMA_URL in .env for AI-powered RCA",
        "severity_assessment":   f"Rule-based: {top_severity}",
        "false_positive_likelihood": "unknown",
        "kb_reference":  None,
        "linked_playbook": None,
    }
