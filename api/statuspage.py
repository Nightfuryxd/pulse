"""
Public Status Page — Statuspage.io replacement.
Defines services, tracks uptime, publishes incidents, serves a public HTML page.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any

# ── In-memory stores ─────────────────────────────────────────────────────────
_services: dict[str, dict] = {}
_status_incidents: list[dict] = []
_uptime_ticks: dict[str, list[dict]] = {}  # service_id -> [{ts, status}]

# Status enum
STATUSES = ["operational", "degraded", "partial_outage", "major_outage", "maintenance"]

# Seed demo services
_seeds = [
    ("svc-api", "API", "Core API endpoints", "operational"),
    ("svc-dash", "Dashboard", "Web dashboard", "operational"),
    ("svc-db", "Database", "PostgreSQL primary", "operational"),
    ("svc-redis", "Cache", "Redis cache layer", "operational"),
    ("svc-agent", "Agent Collector", "Metric collection agents", "operational"),
    ("svc-ws", "WebSocket", "Real-time data stream", "operational"),
]
for sid, name, desc, status in _seeds:
    _services[sid] = {
        "id": sid, "name": name, "description": desc, "status": status,
        "group": "Core Infrastructure",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    # Seed 90 days of uptime history (all operational for demo)
    ticks = []
    for d in range(90):
        ts = (datetime.utcnow() - timedelta(days=89 - d)).replace(hour=0, minute=0, second=0)
        ticks.append({"ts": ts.isoformat(), "status": "operational"})
    _uptime_ticks[sid] = ticks

# Seed a past incident
_status_incidents.append({
    "id": "sinc-001",
    "title": "Elevated API Latency",
    "status": "resolved",
    "impact": "partial_outage",
    "affected_services": ["svc-api"],
    "created_at": (datetime.utcnow() - timedelta(days=3)).isoformat(),
    "resolved_at": (datetime.utcnow() - timedelta(days=3, hours=-2)).isoformat(),
    "updates": [
        {"ts": (datetime.utcnow() - timedelta(days=3)).isoformat(),
         "status": "investigating", "message": "We are investigating elevated API response times."},
        {"ts": (datetime.utcnow() - timedelta(days=3, hours=-1)).isoformat(),
         "status": "identified", "message": "Root cause identified: database connection pool exhaustion."},
        {"ts": (datetime.utcnow() - timedelta(days=3, hours=-2)).isoformat(),
         "status": "resolved", "message": "Connection pool limits increased. All systems operational."},
    ],
})


# ── Service CRUD ─────────────────────────────────────────────────────────────

def list_services() -> list[dict]:
    result = []
    for svc in _services.values():
        uptime = calculate_uptime(svc["id"], 90)
        result.append({**svc, "uptime_90d": uptime})
    return sorted(result, key=lambda s: s["name"])


def get_service(service_id: str) -> dict | None:
    svc = _services.get(service_id)
    if svc:
        svc = {**svc, "uptime_90d": calculate_uptime(service_id, 90),
               "uptime_history": _uptime_ticks.get(service_id, [])}
    return svc


def create_service(data: dict) -> dict:
    sid = f"svc-{uuid.uuid4().hex[:6]}"
    svc = {
        "id": sid,
        "name": data.get("name", "New Service"),
        "description": data.get("description", ""),
        "status": data.get("status", "operational"),
        "group": data.get("group", "Other"),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    _services[sid] = svc
    _uptime_ticks[sid] = [{"ts": datetime.utcnow().isoformat(), "status": "operational"}]
    return svc


def update_service(service_id: str, data: dict) -> dict | None:
    svc = _services.get(service_id)
    if not svc:
        return None
    old_status = svc["status"]
    for key in ("name", "description", "status", "group"):
        if key in data:
            svc[key] = data[key]
    svc["updated_at"] = datetime.utcnow().isoformat()

    # Record status change in uptime ticks
    if data.get("status") and data["status"] != old_status:
        _uptime_ticks.setdefault(service_id, []).append({
            "ts": datetime.utcnow().isoformat(), "status": data["status"]
        })
    return svc


def delete_service(service_id: str) -> bool:
    if service_id in _services:
        del _services[service_id]
        _uptime_ticks.pop(service_id, None)
        return True
    return False


# ── Status Incidents ─────────────────────────────────────────────────────────

def list_status_incidents(limit: int = 20) -> list[dict]:
    return sorted(_status_incidents, key=lambda i: i["created_at"], reverse=True)[:limit]


def create_status_incident(data: dict) -> dict:
    inc = {
        "id": f"sinc-{uuid.uuid4().hex[:6]}",
        "title": data.get("title", "New Incident"),
        "status": data.get("status", "investigating"),
        "impact": data.get("impact", "partial_outage"),
        "affected_services": data.get("affected_services", []),
        "created_at": datetime.utcnow().isoformat(),
        "resolved_at": None,
        "updates": [{
            "ts": datetime.utcnow().isoformat(),
            "status": data.get("status", "investigating"),
            "message": data.get("message", "We are investigating this issue."),
        }],
    }
    _status_incidents.append(inc)

    # Update affected services
    for sid in inc["affected_services"]:
        if sid in _services:
            _services[sid]["status"] = inc["impact"]
            _services[sid]["updated_at"] = datetime.utcnow().isoformat()

    return inc


def update_status_incident(incident_id: str, data: dict) -> dict | None:
    inc = next((i for i in _status_incidents if i["id"] == incident_id), None)
    if not inc:
        return None

    if data.get("status"):
        inc["status"] = data["status"]
    if data.get("message"):
        inc["updates"].append({
            "ts": datetime.utcnow().isoformat(),
            "status": data.get("status", inc["status"]),
            "message": data["message"],
        })
    if data.get("status") == "resolved":
        inc["resolved_at"] = datetime.utcnow().isoformat()
        # Restore affected services
        for sid in inc["affected_services"]:
            if sid in _services:
                _services[sid]["status"] = "operational"
                _services[sid]["updated_at"] = datetime.utcnow().isoformat()
    return inc


# ── Uptime Calculations ─────────────────────────────────────────────────────

def calculate_uptime(service_id: str, days: int = 90) -> float:
    ticks = _uptime_ticks.get(service_id, [])
    if not ticks:
        return 100.0
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    relevant = [t for t in ticks if t["ts"] >= cutoff]
    if not relevant:
        return 100.0
    up_count = sum(1 for t in relevant if t["status"] == "operational")
    return round(up_count / len(relevant) * 100, 2)


def get_overall_status() -> dict:
    """Overall system status for the public page."""
    services = list(_services.values())
    if not services:
        return {"status": "operational", "message": "All Systems Operational"}

    statuses = [s["status"] for s in services]
    if "major_outage" in statuses:
        return {"status": "major_outage", "message": "Major System Outage"}
    if "partial_outage" in statuses:
        return {"status": "partial_outage", "message": "Partial System Outage"}
    if "degraded" in statuses:
        return {"status": "degraded", "message": "Degraded Performance"}
    if "maintenance" in statuses:
        return {"status": "maintenance", "message": "Scheduled Maintenance"}
    return {"status": "operational", "message": "All Systems Operational"}


def get_public_status_data() -> dict:
    """Full data for the public status page."""
    services = list_services()
    # Group by group name
    groups: dict[str, list] = {}
    for svc in services:
        g = svc.get("group", "Other")
        groups.setdefault(g, []).append(svc)

    return {
        "overall": get_overall_status(),
        "groups": groups,
        "incidents": list_status_incidents(10),
        "generated_at": datetime.utcnow().isoformat(),
    }
