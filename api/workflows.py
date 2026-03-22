"""
Alerting Workflow Builder — visual if/then automation chains.
Connects triggers → conditions → actions into executable workflows.
"""
import uuid
from datetime import datetime
from typing import Any

# ── In-memory store ──────────────────────────────────────────────────────────
_workflows: dict[str, dict] = {}
_workflow_runs: list[dict] = []

# ── Available components ─────────────────────────────────────────────────────

TRIGGERS = [
    {"id": "metric_threshold", "name": "Metric Threshold",
     "description": "When a metric crosses a threshold value",
     "icon": "trending-up", "color": "#6366f1",
     "params": [
         {"key": "metric", "label": "Metric", "type": "select",
          "options": ["cpu_percent", "memory_percent", "disk_percent", "load_avg_1m", "process_count"]},
         {"key": "operator", "label": "Operator", "type": "select",
          "options": [">", ">=", "<", "<=", "=="]},
         {"key": "value", "label": "Threshold", "type": "number"},
     ]},
    {"id": "alert_fired", "name": "Alert Fired",
     "description": "When any alert is triggered by the detection engine",
     "icon": "bell", "color": "#f87171",
     "params": [
         {"key": "severity", "label": "Min Severity", "type": "select",
          "options": ["low", "medium", "high", "critical"]},
     ]},
    {"id": "event_detected", "name": "Security Event",
     "description": "When a security event is detected (port scan, suspicious process, etc.)",
     "icon": "shield", "color": "#fbbf24",
     "params": [
         {"key": "event_type", "label": "Event Type", "type": "select",
          "options": ["port_scan", "auth_failure", "suspicious_process", "oom_kill", "any"]},
     ]},
    {"id": "anomaly_detected", "name": "Anomaly Detected",
     "description": "When the anomaly detection engine flags unusual behavior",
     "icon": "activity", "color": "#22d3ee",
     "params": []},
    {"id": "slo_breach", "name": "SLO Breach",
     "description": "When an SLO error budget is exhausted",
     "icon": "target", "color": "#a78bfa",
     "params": [
         {"key": "slo_id", "label": "SLO", "type": "text"},
     ]},
    {"id": "schedule", "name": "Scheduled",
     "description": "Run on a recurring schedule (cron-like)",
     "icon": "clock", "color": "#34d399",
     "params": [
         {"key": "interval_minutes", "label": "Every N minutes", "type": "number"},
     ]},
]

CONDITIONS = [
    {"id": "time_window", "name": "Sustained For",
     "description": "Only trigger if condition holds for N minutes",
     "params": [{"key": "minutes", "label": "Minutes", "type": "number"}]},
    {"id": "node_filter", "name": "Node Filter",
     "description": "Only for specific nodes or node patterns",
     "params": [{"key": "pattern", "label": "Node pattern", "type": "text"}]},
    {"id": "severity_filter", "name": "Severity Filter",
     "description": "Only for specific severity levels",
     "params": [{"key": "min_severity", "label": "Min severity", "type": "select",
                 "options": ["low", "medium", "high", "critical"]}]},
    {"id": "business_hours", "name": "Business Hours",
     "description": "Only during/outside business hours",
     "params": [{"key": "mode", "label": "Mode", "type": "select",
                 "options": ["during", "outside"]}]},
    {"id": "cooldown", "name": "Cooldown",
     "description": "Don't re-trigger within N minutes",
     "params": [{"key": "minutes", "label": "Minutes", "type": "number"}]},
]

ACTIONS = [
    {"id": "notify", "name": "Send Notification",
     "description": "Send notification to a channel (Slack, email, etc.)",
     "icon": "send", "color": "#6366f1",
     "params": [
         {"key": "channel", "label": "Channel", "type": "select",
          "options": ["slack", "email", "teams", "discord", "telegram", "webhook"]},
         {"key": "target", "label": "Target (channel/email)", "type": "text"},
         {"key": "message", "label": "Custom message", "type": "text"},
     ]},
    {"id": "page_oncall", "name": "Page On-Call",
     "description": "Page the current on-call responder",
     "icon": "phone-call", "color": "#f87171",
     "params": [
         {"key": "schedule_id", "label": "Schedule", "type": "text"},
         {"key": "urgency", "label": "Urgency", "type": "select", "options": ["low", "high"]},
     ]},
    {"id": "create_incident", "name": "Create Incident",
     "description": "Automatically create an incident with AI RCA",
     "icon": "alert-triangle", "color": "#fbbf24",
     "params": [
         {"key": "title_template", "label": "Title template", "type": "text"},
         {"key": "severity", "label": "Severity", "type": "select",
          "options": ["critical", "high", "medium", "low"]},
     ]},
    {"id": "run_playbook", "name": "Run Playbook",
     "description": "Execute an auto-remediation playbook",
     "icon": "play", "color": "#34d399",
     "params": [
         {"key": "playbook_id", "label": "Playbook ID", "type": "text"},
     ]},
    {"id": "webhook", "name": "Fire Webhook",
     "description": "Send an HTTP POST to an external URL",
     "icon": "globe", "color": "#22d3ee",
     "params": [
         {"key": "url", "label": "Webhook URL", "type": "text"},
         {"key": "headers", "label": "Custom headers (JSON)", "type": "text"},
     ]},
    {"id": "update_status_page", "name": "Update Status Page",
     "description": "Change a service status on the public status page",
     "icon": "globe", "color": "#fb923c",
     "params": [
         {"key": "service_id", "label": "Service", "type": "text"},
         {"key": "status", "label": "Status", "type": "select",
          "options": ["operational", "degraded", "partial_outage", "major_outage"]},
     ]},
    {"id": "escalate", "name": "Escalate",
     "description": "Escalate to next level in escalation policy",
     "icon": "arrow-up-circle", "color": "#a78bfa",
     "params": [
         {"key": "policy_id", "label": "Escalation Policy", "type": "text"},
         {"key": "wait_minutes", "label": "Wait before escalation (min)", "type": "number"},
     ]},
]

# ── Seed demo workflows ─────────────────────────────────────────────────────

_workflows["wf-cpu-critical"] = {
    "id": "wf-cpu-critical",
    "name": "CPU Critical → Page + Incident",
    "description": "When CPU exceeds 95% for 3 minutes, page on-call and create an incident",
    "enabled": True,
    "trigger": {"type": "metric_threshold", "params": {"metric": "cpu_percent", "operator": ">", "value": 95}},
    "conditions": [
        {"type": "time_window", "params": {"minutes": 3}},
        {"type": "severity_filter", "params": {"min_severity": "critical"}},
    ],
    "actions": [
        {"type": "page_oncall", "params": {"schedule_id": "sched-default", "urgency": "high"}},
        {"type": "create_incident", "params": {"title_template": "CPU Critical on {node_id}", "severity": "critical"}},
        {"type": "notify", "params": {"channel": "slack", "target": "#incidents", "message": "CPU critical alert fired"}},
    ],
    "created_at": datetime.utcnow().isoformat(),
    "last_triggered": None,
    "trigger_count": 0,
}

_workflows["wf-security-event"] = {
    "id": "wf-security-event",
    "name": "Security Event → Alert + Webhook",
    "description": "On any security event, notify the security team and fire a SIEM webhook",
    "enabled": True,
    "trigger": {"type": "event_detected", "params": {"event_type": "any"}},
    "conditions": [],
    "actions": [
        {"type": "notify", "params": {"channel": "slack", "target": "#security", "message": "Security event detected"}},
        {"type": "webhook", "params": {"url": "https://siem.company.com/api/events", "headers": "{}"}},
    ],
    "created_at": datetime.utcnow().isoformat(),
    "last_triggered": None,
    "trigger_count": 0,
}

_workflows["wf-disk-auto-remediate"] = {
    "id": "wf-disk-auto-remediate",
    "name": "Disk Full → Auto Cleanup + Notify",
    "description": "When disk exceeds 90%, run cleanup playbook and notify ops",
    "enabled": True,
    "trigger": {"type": "metric_threshold", "params": {"metric": "disk_percent", "operator": ">", "value": 90}},
    "conditions": [
        {"type": "cooldown", "params": {"minutes": 30}},
    ],
    "actions": [
        {"type": "run_playbook", "params": {"playbook_id": "cleanup-disk"}},
        {"type": "notify", "params": {"channel": "email", "target": "ops@pulse.dev", "message": "Disk cleanup triggered"}},
    ],
    "created_at": datetime.utcnow().isoformat(),
    "last_triggered": None,
    "trigger_count": 0,
}


# ── Workflow CRUD ────────────────────────────────────────────────────────────

def list_workflows() -> list[dict]:
    return sorted(_workflows.values(), key=lambda w: w.get("created_at", ""), reverse=True)


def get_workflow(wf_id: str) -> dict | None:
    return _workflows.get(wf_id)


def create_workflow(data: dict) -> dict:
    wf_id = f"wf-{uuid.uuid4().hex[:8]}"
    wf = {
        "id": wf_id,
        "name": data.get("name", "New Workflow"),
        "description": data.get("description", ""),
        "enabled": data.get("enabled", True),
        "trigger": data.get("trigger", {}),
        "conditions": data.get("conditions", []),
        "actions": data.get("actions", []),
        "created_at": datetime.utcnow().isoformat(),
        "last_triggered": None,
        "trigger_count": 0,
    }
    _workflows[wf_id] = wf
    return wf


def update_workflow(wf_id: str, data: dict) -> dict | None:
    wf = _workflows.get(wf_id)
    if not wf:
        return None
    for k in ("name", "description", "enabled", "trigger", "conditions", "actions"):
        if k in data:
            wf[k] = data[k]
    return wf


def delete_workflow(wf_id: str) -> bool:
    if wf_id in _workflows:
        del _workflows[wf_id]
        return True
    return False


def toggle_workflow(wf_id: str) -> dict | None:
    wf = _workflows.get(wf_id)
    if not wf:
        return None
    wf["enabled"] = not wf["enabled"]
    return wf


# ── Component metadata ───────────────────────────────────────────────────────

def get_components() -> dict:
    """Return all available triggers, conditions, and actions for the UI builder."""
    return {
        "triggers": TRIGGERS,
        "conditions": CONDITIONS,
        "actions": ACTIONS,
    }


def get_workflow_runs(wf_id: str | None = None, limit: int = 20) -> list[dict]:
    runs = _workflow_runs
    if wf_id:
        runs = [r for r in runs if r.get("workflow_id") == wf_id]
    return list(reversed(runs[-limit:]))


def log_run(wf_id: str, trigger_data: dict, results: list[dict]) -> dict:
    run = {
        "id": f"run-{uuid.uuid4().hex[:6]}",
        "workflow_id": wf_id,
        "trigger_data": trigger_data,
        "action_results": results,
        "ran_at": datetime.utcnow().isoformat(),
    }
    _workflow_runs.append(run)
    if len(_workflow_runs) > 200:
        _workflow_runs.pop(0)

    # Update workflow stats
    wf = _workflows.get(wf_id)
    if wf:
        wf["last_triggered"] = run["ran_at"]
        wf["trigger_count"] = wf.get("trigger_count", 0) + 1

    return run
