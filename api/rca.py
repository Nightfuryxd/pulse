"""
Root Cause Analysis Engine.

Takes a cluster of correlated alerts + recent metrics/events for a node,
asks GPT-4o (or local Ollama for air-gapped) to reason about what happened,
why, and what each team should do.
"""
import json
import os
from datetime import datetime


def _get_client():
    """Return OpenAI client, or None if no key (air-gapped mode uses Ollama)."""
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
    node_id:     str,
    node_info:   dict,
    alerts:      list[dict],
    recent_metrics: list[dict],
    recent_events:  list[dict],
    tech_stack:  list[str] | None = None,
) -> dict:
    """
    Run AI root cause analysis on a cluster of alerts.

    Returns:
    {
        "root_cause": "...",
        "confidence": "high|medium|low",
        "affected_components": [...],
        "timeline": "...",
        "blast_radius": "...",
        "recommended_actions": {
            "immediate": [...],
            "short_term": [...],
        },
        "owning_teams": [...],
        "escalate_to": [...],
        "stack_specific_advice": "...",
    }
    """
    client, mode = _get_client()
    if not client:
        return _fallback_rca(alerts)

    model = "gpt-4o" if mode == "openai" else "llama3.1"

    # Format context for the prompt
    alert_summary = "\n".join(
        f"  [{a['severity'].upper()}] {a['rule_name']}: {a['message']} (category: {a['category']})"
        for a in alerts
    )

    # Last 5 metric snapshots
    metrics_summary = ""
    for m in recent_metrics[-5:]:
        metrics_summary += (
            f"  {m.get('ts', '')}: CPU={m.get('cpu_percent', 0):.1f}% "
            f"MEM={m.get('memory_percent', 0):.1f}% "
            f"DISK={m.get('disk_percent', 0):.1f}% "
            f"LOAD={m.get('load_avg_1m', 0):.2f}\n"
        )

    # Recent events (security + system)
    events_summary = "\n".join(
        f"  [{e.get('ts', '')}] {e.get('type', '')}: {e.get('message', '')}"
        for e in recent_events[-10:]
    ) or "  No recent events"

    stack_str = ", ".join(tech_stack) if tech_stack else "unknown (not configured)"

    prompt = f"""You are a senior SRE/SecOps engineer performing root cause analysis on a production incident.

NODE: {node_id} ({node_info.get('hostname', node_id)}) | OS: {node_info.get('os', 'unknown')} | IP: {node_info.get('ip', 'unknown')}
TECH STACK: {stack_str}
INCIDENT TIME: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

TRIGGERED ALERTS:
{alert_summary}

RECENT METRICS (last 5 readings):
{metrics_summary or '  No recent metrics'}

RECENT EVENTS (security + system):
{events_summary}

Perform a precise root cause analysis. Be specific — reference actual values and timestamps.
If the tech stack is known, give stack-specific commands and fixes.

Respond ONLY as JSON:
{{
  "root_cause": "One clear sentence: what is the fundamental cause",
  "confidence": "high|medium|low",
  "affected_components": ["list of affected services/components"],
  "timeline": "Brief narrative of what happened in order",
  "blast_radius": "What could fail next if not addressed",
  "recommended_actions": {{
    "immediate": ["Action 1 — do right now", "Action 2"],
    "short_term": ["Action for next 24h", "Action 2"]
  }},
  "owning_teams": ["team ids from: secops, netops, appdev, dba, infra"],
  "escalate_to": ["teams that should be looped in but don't own it"],
  "stack_specific_advice": "Specific commands or config changes for their exact stack",
  "severity_assessment": "Why this severity level is correct",
  "false_positive_likelihood": "low|medium|high — with reason"
}}"""

    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=1500,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        raw   = resp.choices[0].message.content
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception as e:
        print(f"[RCA] AI analysis failed: {e}")
        return _fallback_rca(alerts)


def _fallback_rca(alerts: list[dict]) -> dict:
    """Rule-based fallback when AI is unavailable."""
    categories = list({a["category"] for a in alerts})
    severities = [a["severity"] for a in alerts]
    top_severity = "critical" if "critical" in severities else "high" if "high" in severities else "medium"

    team_map = {
        "cpu": "infra", "memory": "infra", "disk": "infra", "oom": "infra",
        "auth_failure": "secops", "threat": "secops", "port_scan": "secops",
        "privilege_escalation": "secops", "intrusion": "secops",
        "network": "netops", "latency": "netops", "dns": "netops",
        "application": "appdev", "crash": "appdev", "code": "appdev",
        "database": "dba", "slow_query": "dba", "replication": "dba",
    }
    owning_teams = list({team_map.get(c, "infra") for c in categories})

    return {
        "root_cause": f"Multiple {top_severity} alerts detected: {', '.join(a['rule_name'] for a in alerts[:3])}",
        "confidence": "low",
        "affected_components": categories,
        "timeline": "Alert cluster detected — AI analysis unavailable (no API key or Ollama configured)",
        "blast_radius": "Unknown — manual investigation required",
        "recommended_actions": {
            "immediate": [f"Investigate {a['rule_name']}: {a['message']}" for a in alerts[:3]],
            "short_term": ["Configure OPENAI_API_KEY or OLLAMA_URL for AI-powered RCA"],
        },
        "owning_teams": owning_teams,
        "escalate_to": [],
        "stack_specific_advice": "Set OPENAI_API_KEY in .env for stack-specific guidance",
        "severity_assessment": f"Based on rule thresholds: {top_severity}",
        "false_positive_likelihood": "unknown",
    }
