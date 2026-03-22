"""
Audit Log — compliance-grade tracking of all user actions.
Records who changed what, when, and why across the platform.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any

# ── In-memory store ──────────────────────────────────────────────────────────
_audit_entries: list[dict] = []
MAX_ENTRIES = 2000

# Categories
CATEGORIES = ["auth", "config", "alert", "incident", "oncall", "workflow",
              "dashboard", "status_page", "catalog", "api_key", "user", "environment"]

# Action types
ACTIONS = ["create", "update", "delete", "login", "logout", "acknowledge",
           "resolve", "escalate", "toggle", "export", "import", "override"]

# ── Seed demo entries ────────────────────────────────────────────────────────
_seeds = [
    {
        "actor": "aniket@pulse.dev",
        "actor_name": "Aniket Gupta",
        "category": "auth",
        "action": "login",
        "resource": "session",
        "resource_id": None,
        "description": "Logged in from 192.168.1.100",
        "metadata": {"ip": "192.168.1.100", "user_agent": "Chrome/120"},
        "ago_minutes": 5,
    },
    {
        "actor": "aniket@pulse.dev",
        "actor_name": "Aniket Gupta",
        "category": "config",
        "action": "update",
        "resource": "threshold",
        "resource_id": "cpu_critical",
        "description": "Changed CPU critical threshold from 90% to 95%",
        "metadata": {"field": "cpu_critical", "old_value": 90, "new_value": 95},
        "ago_minutes": 15,
    },
    {
        "actor": "aniket@pulse.dev",
        "actor_name": "Aniket Gupta",
        "category": "alert",
        "action": "acknowledge",
        "resource": "alert",
        "resource_id": "alert-001",
        "description": "Acknowledged critical CPU alert on node-1",
        "metadata": {"severity": "critical", "node": "node-1"},
        "ago_minutes": 30,
    },
    {
        "actor": "alex@pulse.dev",
        "actor_name": "Alex Chen",
        "category": "incident",
        "action": "resolve",
        "resource": "incident",
        "resource_id": "inc-042",
        "description": "Resolved incident: Database connection pool exhaustion",
        "metadata": {"resolution": "Increased pool size from 20 to 50", "duration_minutes": 45},
        "ago_minutes": 60,
    },
    {
        "actor": "aniket@pulse.dev",
        "actor_name": "Aniket Gupta",
        "category": "workflow",
        "action": "create",
        "resource": "workflow",
        "resource_id": "wf-cpu-critical",
        "description": "Created workflow: CPU Critical -> Page + Incident",
        "metadata": {"trigger": "metric_threshold", "actions": 3},
        "ago_minutes": 90,
    },
    {
        "actor": "sarah@pulse.dev",
        "actor_name": "Sarah Kim",
        "category": "oncall",
        "action": "override",
        "resource": "schedule",
        "resource_id": "sched-default",
        "description": "Created override: covering for Alex Chen (Mar 20-22)",
        "metadata": {"original": "Alex Chen", "override_by": "Sarah Kim"},
        "ago_minutes": 180,
    },
    {
        "actor": "aniket@pulse.dev",
        "actor_name": "Aniket Gupta",
        "category": "status_page",
        "action": "update",
        "resource": "service",
        "resource_id": "svc-api",
        "description": "Updated API status from degraded to operational",
        "metadata": {"old_status": "degraded", "new_status": "operational"},
        "ago_minutes": 240,
    },
    {
        "actor": "system",
        "actor_name": "System",
        "category": "alert",
        "action": "escalate",
        "resource": "alert",
        "resource_id": "alert-088",
        "description": "Auto-escalated unacknowledged alert to Level 2",
        "metadata": {"escalation_level": 2, "policy": "default"},
        "ago_minutes": 300,
    },
    {
        "actor": "aniket@pulse.dev",
        "actor_name": "Aniket Gupta",
        "category": "catalog",
        "action": "create",
        "resource": "service",
        "resource_id": "cat-payment",
        "description": "Added Payment Service to catalog (tier-1, team-backend)",
        "metadata": {"tier": "tier-1", "team": "team-backend"},
        "ago_minutes": 360,
    },
    {
        "actor": "aniket@pulse.dev",
        "actor_name": "Aniket Gupta",
        "category": "api_key",
        "action": "create",
        "resource": "api_key",
        "resource_id": "key-prod-001",
        "description": "Created API key: Production Monitoring (read-only)",
        "metadata": {"scope": "read", "name": "Production Monitoring"},
        "ago_minutes": 480,
    },
    {
        "actor": "aniket@pulse.dev",
        "actor_name": "Aniket Gupta",
        "category": "dashboard",
        "action": "create",
        "resource": "dashboard",
        "resource_id": "dash-infra",
        "description": "Created custom dashboard: Infrastructure Overview",
        "metadata": {"widgets": 7},
        "ago_minutes": 600,
    },
    {
        "actor": "alex@pulse.dev",
        "actor_name": "Alex Chen",
        "category": "config",
        "action": "update",
        "resource": "notification_channel",
        "resource_id": "slack",
        "description": "Updated Slack notification channel target to #incidents",
        "metadata": {"channel": "slack", "old_target": "#alerts", "new_target": "#incidents"},
        "ago_minutes": 720,
    },
]

now = datetime.utcnow()
for s in _seeds:
    _audit_entries.append({
        "id": f"audit-{uuid.uuid4().hex[:8]}",
        "actor": s["actor"],
        "actor_name": s["actor_name"],
        "category": s["category"],
        "action": s["action"],
        "resource": s["resource"],
        "resource_id": s.get("resource_id"),
        "description": s["description"],
        "metadata": s.get("metadata", {}),
        "ip_address": "192.168.1.100" if s["actor"] != "system" else None,
        "created_at": (now - timedelta(minutes=s["ago_minutes"])).isoformat(),
    })


# ── Core functions ───────────────────────────────────────────────────────────

def log(actor: str, actor_name: str, category: str, action: str,
        resource: str, resource_id: str | None = None,
        description: str = "", metadata: dict | None = None,
        ip_address: str | None = None) -> dict:
    """Record an audit log entry."""
    entry = {
        "id": f"audit-{uuid.uuid4().hex[:8]}",
        "actor": actor,
        "actor_name": actor_name,
        "category": category,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "description": description,
        "metadata": metadata or {},
        "ip_address": ip_address,
        "created_at": datetime.utcnow().isoformat(),
    }
    _audit_entries.append(entry)
    if len(_audit_entries) > MAX_ENTRIES:
        _audit_entries.pop(0)
    return entry


def list_entries(category: str | None = None, action: str | None = None,
                 actor: str | None = None, limit: int = 50,
                 offset: int = 0) -> dict:
    result = list(reversed(_audit_entries))
    if category:
        result = [e for e in result if e.get("category") == category]
    if action:
        result = [e for e in result if e.get("action") == action]
    if actor:
        result = [e for e in result if e.get("actor") == actor]
    total = len(result)
    return {
        "entries": result[offset:offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_entry(entry_id: str) -> dict | None:
    for e in _audit_entries:
        if e["id"] == entry_id:
            return e
    return None


def get_summary() -> dict:
    entries = _audit_entries
    now = datetime.utcnow()
    last_24h = [e for e in entries if e.get("created_at", "") >= (now - timedelta(hours=24)).isoformat()]
    last_7d = [e for e in entries if e.get("created_at", "") >= (now - timedelta(days=7)).isoformat()]

    actors = {}
    for e in last_24h:
        a = e.get("actor", "unknown")
        actors[a] = actors.get(a, 0) + 1

    return {
        "total_entries": len(entries),
        "last_24h": len(last_24h),
        "last_7d": len(last_7d),
        "by_category": {c: sum(1 for e in last_24h if e.get("category") == c) for c in CATEGORIES if any(e.get("category") == c for e in last_24h)},
        "by_action": {a: sum(1 for e in last_24h if e.get("action") == a) for a in ACTIONS if any(e.get("action") == a for e in last_24h)},
        "top_actors": sorted(
            [{"actor": k, "count": v} for k, v in actors.items()],
            key=lambda x: x["count"], reverse=True
        )[:5],
        "categories": CATEGORIES,
        "actions": ACTIONS,
    }
