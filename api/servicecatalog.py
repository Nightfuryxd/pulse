"""
Service Catalog — define, own, and track all your services.
Maps ownership, dependencies, tiers, and links to runbooks/SLOs.
"""
import uuid
from datetime import datetime
from typing import Any

# ── In-memory store ──────────────────────────────────────────────────────────
_services: dict[str, dict] = {}
_teams: dict[str, dict] = {}

# Service tiers
TIERS = ["tier-0", "tier-1", "tier-2", "tier-3"]  # 0 = most critical

# Seed teams
_teams = {
    "team-platform": {
        "id": "team-platform", "name": "Platform Engineering",
        "slack_channel": "#platform-eng", "email": "platform@pulse.dev",
        "members": ["Aniket Gupta", "Alex Chen", "Sarah Kim"],
        "oncall_schedule": "sched-default",
    },
    "team-backend": {
        "id": "team-backend", "name": "Backend Services",
        "slack_channel": "#backend", "email": "backend@pulse.dev",
        "members": ["Jordan Lee", "Maria Santos"],
        "oncall_schedule": None,
    },
    "team-data": {
        "id": "team-data", "name": "Data & Analytics",
        "slack_channel": "#data-eng", "email": "data@pulse.dev",
        "members": ["Chris Wang", "Priya Patel"],
        "oncall_schedule": None,
    },
}

# Seed services
_seeds = [
    {
        "id": "cat-api-gateway", "name": "API Gateway",
        "description": "Main API entry point — handles auth, rate limiting, routing",
        "owner_team": "team-platform", "tier": "tier-0",
        "language": "Python", "framework": "FastAPI",
        "repository": "github.com/pulse/api-gateway",
        "dependencies": ["cat-database", "cat-cache", "cat-auth"],
        "dependents": ["cat-dashboard", "cat-agent-collector"],
        "runbook_url": "/kb", "slo_id": "api-availability",
        "tags": ["api", "critical", "public-facing"],
        "status": "healthy",
        "last_deploy": (datetime.utcnow()).isoformat(),
        "deploy_frequency": "12/week",
        "mttr_minutes": 15,
        "incidents_30d": 2,
    },
    {
        "id": "cat-database", "name": "PostgreSQL Primary",
        "description": "Primary relational database — stores nodes, metrics, alerts, incidents",
        "owner_team": "team-platform", "tier": "tier-0",
        "language": "SQL", "framework": "PostgreSQL 15",
        "repository": None,
        "dependencies": [],
        "dependents": ["cat-api-gateway", "cat-auth"],
        "runbook_url": "/kb", "slo_id": "db-availability",
        "tags": ["database", "critical", "stateful"],
        "status": "healthy",
        "last_deploy": None,
        "deploy_frequency": "0/week",
        "mttr_minutes": 30,
        "incidents_30d": 0,
    },
    {
        "id": "cat-cache", "name": "Redis Cache",
        "description": "In-memory cache and pub/sub — session store, real-time data",
        "owner_team": "team-platform", "tier": "tier-1",
        "language": None, "framework": "Redis 7",
        "repository": None,
        "dependencies": [],
        "dependents": ["cat-api-gateway"],
        "runbook_url": "/kb",  "slo_id": None,
        "tags": ["cache", "in-memory"],
        "status": "healthy",
        "last_deploy": None,
        "deploy_frequency": "0/week",
        "mttr_minutes": 10,
        "incidents_30d": 0,
    },
    {
        "id": "cat-auth", "name": "Auth Service",
        "description": "JWT authentication, user management, RBAC",
        "owner_team": "team-backend", "tier": "tier-0",
        "language": "Python", "framework": "FastAPI",
        "repository": "github.com/pulse/auth",
        "dependencies": ["cat-database"],
        "dependents": ["cat-api-gateway", "cat-dashboard"],
        "runbook_url": "/kb", "slo_id": None,
        "tags": ["auth", "security", "critical"],
        "status": "healthy",
        "last_deploy": (datetime.utcnow()).isoformat(),
        "deploy_frequency": "4/week",
        "mttr_minutes": 20,
        "incidents_30d": 1,
    },
    {
        "id": "cat-dashboard", "name": "Dashboard UI",
        "description": "Web-based monitoring dashboard — single-page application",
        "owner_team": "team-platform", "tier": "tier-1",
        "language": "JavaScript", "framework": "Vanilla JS + Chart.js",
        "repository": "github.com/pulse/dashboard",
        "dependencies": ["cat-api-gateway", "cat-auth"],
        "dependents": [],
        "runbook_url": "/kb", "slo_id": None,
        "tags": ["frontend", "ui"],
        "status": "healthy",
        "last_deploy": (datetime.utcnow()).isoformat(),
        "deploy_frequency": "8/week",
        "mttr_minutes": 5,
        "incidents_30d": 0,
    },
    {
        "id": "cat-agent-collector", "name": "Agent Collector",
        "description": "Distributed metric collection agent — runs on every node",
        "owner_team": "team-platform", "tier": "tier-0",
        "language": "Python", "framework": "psutil + httpx",
        "repository": "github.com/pulse/agent",
        "dependencies": ["cat-api-gateway"],
        "dependents": [],
        "runbook_url": "/kb", "slo_id": "agent-uptime",
        "tags": ["agent", "distributed", "daemonset"],
        "status": "healthy",
        "last_deploy": (datetime.utcnow()).isoformat(),
        "deploy_frequency": "2/week",
        "mttr_minutes": 10,
        "incidents_30d": 0,
    },
    {
        "id": "cat-notification-engine", "name": "Notification Engine",
        "description": "Multi-channel alert delivery — Slack, email, PagerDuty, webhooks",
        "owner_team": "team-backend", "tier": "tier-1",
        "language": "Python", "framework": "FastAPI",
        "repository": "github.com/pulse/notifications",
        "dependencies": ["cat-api-gateway"],
        "dependents": [],
        "runbook_url": "/kb", "slo_id": None,
        "tags": ["notifications", "alerts"],
        "status": "healthy",
        "last_deploy": (datetime.utcnow()).isoformat(),
        "deploy_frequency": "3/week",
        "mttr_minutes": 15,
        "incidents_30d": 0,
    },
    {
        "id": "cat-analytics-pipeline", "name": "Analytics Pipeline",
        "description": "Metric aggregation, anomaly detection, predictive analysis",
        "owner_team": "team-data", "tier": "tier-2",
        "language": "Python", "framework": "NumPy + custom ML",
        "repository": "github.com/pulse/analytics",
        "dependencies": ["cat-database", "cat-cache"],
        "dependents": ["cat-api-gateway"],
        "runbook_url": "/kb", "slo_id": None,
        "tags": ["analytics", "ml", "data"],
        "status": "healthy",
        "last_deploy": (datetime.utcnow()).isoformat(),
        "deploy_frequency": "5/week",
        "mttr_minutes": 25,
        "incidents_30d": 1,
    },
]

for s in _seeds:
    s["created_at"] = datetime.utcnow().isoformat()
    _services[s["id"]] = s


# ── Service CRUD ─────────────────────────────────────────────────────────────

def list_services(tier: str | None = None, team: str | None = None,
                  tag: str | None = None) -> list[dict]:
    result = list(_services.values())
    if tier:
        result = [s for s in result if s.get("tier") == tier]
    if team:
        result = [s for s in result if s.get("owner_team") == team]
    if tag:
        result = [s for s in result if tag in s.get("tags", [])]
    # Enrich with team info
    for s in result:
        t = _teams.get(s.get("owner_team", ""))
        s["owner_team_name"] = t["name"] if t else "Unknown"
    return sorted(result, key=lambda s: (TIERS.index(s.get("tier", "tier-3")), s["name"]))


def get_service(service_id: str) -> dict | None:
    svc = _services.get(service_id)
    if svc:
        t = _teams.get(svc.get("owner_team", ""))
        svc["owner_team_info"] = t
        # Resolve dependency names
        svc["dependency_names"] = [_services[d]["name"] for d in svc.get("dependencies", []) if d in _services]
        svc["dependent_names"] = [_services[d]["name"] for d in svc.get("dependents", []) if d in _services]
    return svc


def create_service(data: dict) -> dict:
    sid = f"cat-{uuid.uuid4().hex[:8]}"
    svc = {
        "id": sid,
        "name": data.get("name", "New Service"),
        "description": data.get("description", ""),
        "owner_team": data.get("owner_team", ""),
        "tier": data.get("tier", "tier-2"),
        "language": data.get("language"),
        "framework": data.get("framework"),
        "repository": data.get("repository"),
        "dependencies": data.get("dependencies", []),
        "dependents": data.get("dependents", []),
        "runbook_url": data.get("runbook_url"),
        "slo_id": data.get("slo_id"),
        "tags": data.get("tags", []),
        "status": "healthy",
        "last_deploy": None,
        "deploy_frequency": "0/week",
        "mttr_minutes": 0,
        "incidents_30d": 0,
        "created_at": datetime.utcnow().isoformat(),
    }
    _services[sid] = svc
    return svc


def update_service(service_id: str, data: dict) -> dict | None:
    svc = _services.get(service_id)
    if not svc:
        return None
    updatable = ["name", "description", "owner_team", "tier", "language", "framework",
                 "repository", "dependencies", "dependents", "runbook_url", "slo_id",
                 "tags", "status", "last_deploy", "deploy_frequency", "mttr_minutes", "incidents_30d"]
    for k in updatable:
        if k in data:
            svc[k] = data[k]
    return svc


def delete_service(service_id: str) -> bool:
    if service_id in _services:
        del _services[service_id]
        return True
    return False


# ── Teams ────────────────────────────────────────────────────────────────────

def list_teams() -> list[dict]:
    result = []
    for t in _teams.values():
        svc_count = sum(1 for s in _services.values() if s.get("owner_team") == t["id"])
        result.append({**t, "service_count": svc_count})
    return result


def get_team(team_id: str) -> dict | None:
    t = _teams.get(team_id)
    if t:
        t["services"] = [s for s in _services.values() if s.get("owner_team") == team_id]
    return t


def create_team(data: dict) -> dict:
    tid = f"team-{uuid.uuid4().hex[:6]}"
    team = {
        "id": tid,
        "name": data.get("name", "New Team"),
        "slack_channel": data.get("slack_channel", ""),
        "email": data.get("email", ""),
        "members": data.get("members", []),
        "oncall_schedule": data.get("oncall_schedule"),
    }
    _teams[tid] = team
    return team


# ── Dependency Graph ─────────────────────────────────────────────────────────

def get_dependency_graph() -> dict:
    """Returns nodes and edges for the full service dependency graph."""
    nodes = []
    edges = []
    for svc in _services.values():
        nodes.append({
            "id": svc["id"], "name": svc["name"],
            "tier": svc.get("tier", "tier-3"),
            "status": svc.get("status", "healthy"),
            "team": svc.get("owner_team", ""),
        })
        for dep in svc.get("dependencies", []):
            if dep in _services:
                edges.append({"from": svc["id"], "to": dep})
    return {"nodes": nodes, "edges": edges}


def get_catalog_summary() -> dict:
    """Dashboard-level summary stats."""
    services = list(_services.values())
    return {
        "total_services": len(services),
        "by_tier": {t: sum(1 for s in services if s.get("tier") == t) for t in TIERS},
        "by_status": {
            "healthy": sum(1 for s in services if s.get("status") == "healthy"),
            "degraded": sum(1 for s in services if s.get("status") == "degraded"),
            "down": sum(1 for s in services if s.get("status") == "down"),
        },
        "total_teams": len(_teams),
        "total_incidents_30d": sum(s.get("incidents_30d", 0) for s in services),
        "avg_mttr_minutes": round(sum(s.get("mttr_minutes", 0) for s in services) / max(len(services), 1), 1),
    }
