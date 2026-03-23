"""
Incident War Room — real-time collaborative incident timeline.
Auto-correlates alerts, metrics, logs, and responder actions.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any

# ── In-memory store ──────────────────────────────────────────────────────────
_war_rooms: dict[str, dict] = {}

# Event types for the timeline
EVENT_TYPES = ["alert", "metric_spike", "log_pattern", "responder_action",
               "status_change", "communication", "runbook_step", "deployment",
               "rca_update", "escalation"]

# ── Seed a demo war room ────────────────────────────────────────────────────
now = datetime.utcnow()

_war_rooms["wr-001"] = {
    "id": "wr-001",
    "incident_id": "inc-042",
    "title": "Database Connection Pool Exhaustion",
    "severity": "critical",
    "status": "active",
    "started_at": (now - timedelta(minutes=45)).isoformat(),
    "resolved_at": None,
    "commander": {"name": "Aniket Gupta", "email": "aniket@pulse.dev"},
    "responders": [
        {"name": "Aniket Gupta", "email": "aniket@pulse.dev", "role": "Incident Commander", "joined_at": (now - timedelta(minutes=45)).isoformat()},
        {"name": "Alex Chen", "email": "alex@pulse.dev", "role": "Database Lead", "joined_at": (now - timedelta(minutes=42)).isoformat()},
        {"name": "Sarah Kim", "email": "sarah@pulse.dev", "role": "SRE", "joined_at": (now - timedelta(minutes=38)).isoformat()},
    ],
    "affected_services": ["API Gateway", "Auth Service", "PostgreSQL Primary"],
    "timeline": [
        {"id": "evt-01", "type": "alert", "ts": (now - timedelta(minutes=45)).isoformat(),
         "title": "Alert: PostgreSQL connection count > 90%",
         "detail": "pg_connections at 94% capacity (188/200)", "actor": "system",
         "severity": "critical", "metadata": {"metric": "pg_connections", "value": 94}},
        {"id": "evt-02", "type": "metric_spike", "ts": (now - timedelta(minutes=44)).isoformat(),
         "title": "Metric spike: API latency P99 jumped to 2400ms",
         "detail": "P99 latency increased 8x from baseline 300ms", "actor": "system",
         "severity": "high", "metadata": {"metric": "http_latency_p99", "value": 2400}},
        {"id": "evt-03", "type": "alert", "ts": (now - timedelta(minutes=43)).isoformat(),
         "title": "Alert: HTTP Error Rate > 5%",
         "detail": "5xx error rate at 12.3% across API Gateway", "actor": "system",
         "severity": "critical", "metadata": {"metric": "http_error_rate", "value": 12.3}},
        {"id": "evt-04", "type": "escalation", "ts": (now - timedelta(minutes=42)).isoformat(),
         "title": "Auto-escalated to Level 2 — Alex Chen paged",
         "detail": "Escalation policy triggered after 3min unacknowledged", "actor": "system",
         "severity": "high", "metadata": {"level": 2, "target": "Alex Chen"}},
        {"id": "evt-05", "type": "responder_action", "ts": (now - timedelta(minutes=40)).isoformat(),
         "title": "Aniket acknowledged the incident",
         "detail": "Incident commander assigned", "actor": "Aniket Gupta",
         "severity": "info", "metadata": {}},
        {"id": "evt-06", "type": "log_pattern", "ts": (now - timedelta(minutes=39)).isoformat(),
         "title": "Log pattern: 'FATAL: too many connections for role'",
         "detail": "Detected 47 occurrences in the last 5 minutes from api-gateway pods", "actor": "system",
         "severity": "critical", "metadata": {"count": 47, "source": "api-gateway"}},
        {"id": "evt-07", "type": "communication", "ts": (now - timedelta(minutes=38)).isoformat(),
         "title": "Alex Chen: 'Checking pg_stat_activity for long-running queries'",
         "detail": "", "actor": "Alex Chen",
         "severity": "info", "metadata": {}},
        {"id": "evt-08", "type": "rca_update", "ts": (now - timedelta(minutes=35)).isoformat(),
         "title": "AI RCA: Connection leak in auth-service v2.3.1",
         "detail": "GPT-4o analysis: Auth service connection pool not releasing connections after JWT validation timeout. Introduced in deploy v2.3.1 (3 hours ago). Connections accumulate until pool exhaustion.",
         "actor": "PULSE AI", "severity": "high",
         "metadata": {"confidence": 0.87, "root_cause": "connection_leak", "deploy": "v2.3.1"}},
        {"id": "evt-09", "type": "deployment", "ts": (now - timedelta(minutes=34)).isoformat(),
         "title": "Correlated deployment: auth-service v2.3.1 deployed 3h ago",
         "detail": "Deployment by CI/CD pipeline. Changes: JWT validation refactor, added connection retry logic",
         "actor": "system", "severity": "medium",
         "metadata": {"service": "auth-service", "version": "v2.3.1"}},
        {"id": "evt-10", "type": "runbook_step", "ts": (now - timedelta(minutes=30)).isoformat(),
         "title": "Runbook: Increased connection pool from 200 to 400",
         "detail": "Applied temporary mitigation via ALTER SYSTEM SET max_connections = 400", "actor": "Alex Chen",
         "severity": "info", "metadata": {"action": "increase_pool", "old": 200, "new": 400}},
        {"id": "evt-11", "type": "status_change", "ts": (now - timedelta(minutes=28)).isoformat(),
         "title": "Status page updated: API — Degraded Performance",
         "detail": "Public status page updated to reflect degraded API performance", "actor": "Aniket Gupta",
         "severity": "info", "metadata": {"service": "API", "status": "degraded"}},
        {"id": "evt-12", "type": "metric_spike", "ts": (now - timedelta(minutes=25)).isoformat(),
         "title": "Metric recovery: pg_connections dropping (280 → 180)",
         "detail": "Connection count decreasing after pool increase", "actor": "system",
         "severity": "info", "metadata": {"metric": "pg_connections", "value": 180, "trend": "down"}},
        {"id": "evt-13", "type": "communication", "ts": (now - timedelta(minutes=20)).isoformat(),
         "title": "Sarah Kim: 'Rolling back auth-service to v2.3.0'",
         "detail": "Initiating rollback of the problematic deployment", "actor": "Sarah Kim",
         "severity": "info", "metadata": {}},
        {"id": "evt-14", "type": "deployment", "ts": (now - timedelta(minutes=15)).isoformat(),
         "title": "Rollback: auth-service reverted to v2.3.0",
         "detail": "Deployment rollback completed successfully. All pods healthy.", "actor": "Sarah Kim",
         "severity": "info", "metadata": {"service": "auth-service", "version": "v2.3.0", "action": "rollback"}},
        {"id": "evt-15", "type": "metric_spike", "ts": (now - timedelta(minutes=10)).isoformat(),
         "title": "Metrics normalizing: P99 latency back to 320ms, error rate 0.2%",
         "detail": "All key metrics returning to baseline", "actor": "system",
         "severity": "info", "metadata": {"http_latency_p99": 320, "http_error_rate": 0.2}},
    ],
    "notes": "Root cause: connection leak in auth-service v2.3.1. Mitigated by pool increase, resolved by rollback to v2.3.0. Post-mortem scheduled for Monday.",
    "tags": ["database", "connection-leak", "deployment-related"],
}

_war_rooms["wr-002"] = {
    "id": "wr-002",
    "incident_id": "inc-039",
    "title": "Redis Cache Cluster Failover",
    "severity": "high",
    "status": "resolved",
    "started_at": (now - timedelta(hours=6)).isoformat(),
    "resolved_at": (now - timedelta(hours=5)).isoformat(),
    "commander": {"name": "Alex Chen", "email": "alex@pulse.dev"},
    "responders": [
        {"name": "Alex Chen", "email": "alex@pulse.dev", "role": "Incident Commander", "joined_at": (now - timedelta(hours=6)).isoformat()},
        {"name": "Aniket Gupta", "email": "aniket@pulse.dev", "role": "Platform Lead", "joined_at": (now - timedelta(hours=5, minutes=55)).isoformat()},
    ],
    "affected_services": ["Redis Cache", "API Gateway"],
    "timeline": [
        {"id": "evt-20", "type": "alert", "ts": (now - timedelta(hours=6)).isoformat(),
         "title": "Alert: Redis primary node unreachable", "detail": "Health check failed 3 consecutive times",
         "actor": "system", "severity": "critical", "metadata": {}},
        {"id": "evt-21", "type": "status_change", "ts": (now - timedelta(hours=5, minutes=55)).isoformat(),
         "title": "Redis Sentinel initiated automatic failover", "detail": "Replica redis-2 promoted to primary",
         "actor": "system", "severity": "high", "metadata": {}},
        {"id": "evt-22", "type": "responder_action", "ts": (now - timedelta(hours=5, minutes=50)).isoformat(),
         "title": "Alex Chen acknowledged and investigating", "detail": "Checking Redis logs and node health",
         "actor": "Alex Chen", "severity": "info", "metadata": {}},
        {"id": "evt-23", "type": "status_change", "ts": (now - timedelta(hours=5)).isoformat(),
         "title": "Incident resolved — failover successful", "detail": "All services reconnected to new primary. Old primary restarted as replica.",
         "actor": "Alex Chen", "severity": "info", "metadata": {}},
    ],
    "notes": "Automatic failover worked as expected. Root cause: memory pressure on redis-1 node caused OOM kill.",
    "tags": ["redis", "failover", "auto-resolved"],
}


# ── CRUD ─────────────────────────────────────────────────────────────────────

def list_war_rooms(status: str | None = None) -> list[dict]:
    result = list(_war_rooms.values())
    if status:
        result = [r for r in result if r.get("status") == status]
    # Return without full timeline for list view
    return [{k: v for k, v in r.items() if k != "timeline"}
            | {"event_count": len(r.get("timeline", []))}
            for r in sorted(result, key=lambda r: r.get("started_at", ""), reverse=True)]


def get_war_room(room_id: str) -> dict | None:
    return _war_rooms.get(room_id)


def create_war_room(data: dict) -> dict:
    rid = f"wr-{uuid.uuid4().hex[:6]}"
    room = {
        "id": rid,
        "incident_id": data.get("incident_id"),
        "title": data.get("title", "New Incident"),
        "severity": data.get("severity", "high"),
        "status": "active",
        "started_at": datetime.utcnow().isoformat(),
        "resolved_at": None,
        "commander": data.get("commander", {}),
        "responders": data.get("responders", []),
        "affected_services": data.get("affected_services", []),
        "timeline": [],
        "notes": "",
        "tags": data.get("tags", []),
    }
    _war_rooms[rid] = room
    return room


def add_timeline_event(room_id: str, data: dict) -> dict | None:
    room = _war_rooms.get(room_id)
    if not room:
        return None
    event = {
        "id": f"evt-{uuid.uuid4().hex[:6]}",
        "type": data.get("type", "communication"),
        "ts": datetime.utcnow().isoformat(),
        "title": data.get("title", ""),
        "detail": data.get("detail", ""),
        "actor": data.get("actor", ""),
        "severity": data.get("severity", "info"),
        "metadata": data.get("metadata", {}),
    }
    room["timeline"].append(event)
    return event


def resolve_war_room(room_id: str, notes: str = "") -> dict | None:
    room = _war_rooms.get(room_id)
    if not room:
        return None
    room["status"] = "resolved"
    room["resolved_at"] = datetime.utcnow().isoformat()
    if notes:
        room["notes"] = notes
    # Add resolution event
    room["timeline"].append({
        "id": f"evt-{uuid.uuid4().hex[:6]}",
        "type": "status_change",
        "ts": datetime.utcnow().isoformat(),
        "title": "Incident resolved",
        "detail": notes or "Incident marked as resolved",
        "actor": "system",
        "severity": "info",
        "metadata": {},
    })
    return room


def add_responder(room_id: str, data: dict) -> dict | None:
    room = _war_rooms.get(room_id)
    if not room:
        return None
    responder = {
        "name": data.get("name", ""),
        "email": data.get("email", ""),
        "role": data.get("role", "Responder"),
        "joined_at": datetime.utcnow().isoformat(),
    }
    room["responders"].append(responder)
    room["timeline"].append({
        "id": f"evt-{uuid.uuid4().hex[:6]}",
        "type": "responder_action",
        "ts": datetime.utcnow().isoformat(),
        "title": f"{responder['name']} joined the war room",
        "detail": f"Role: {responder['role']}",
        "actor": responder["name"],
        "severity": "info",
        "metadata": {},
    })
    return responder


def get_summary() -> dict:
    rooms = list(_war_rooms.values())
    active = [r for r in rooms if r.get("status") == "active"]
    resolved = [r for r in rooms if r.get("status") == "resolved"]
    return {
        "total": len(rooms),
        "active": len(active),
        "resolved": len(resolved),
        "total_events": sum(len(r.get("timeline", [])) for r in rooms),
        "total_responders": sum(len(r.get("responders", [])) for r in rooms),
    }
