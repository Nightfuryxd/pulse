"""
Multi-Environment Support — manage and switch between prod/staging/dev.
Each environment has its own set of nodes, alerts, and configuration.
"""
import uuid
from datetime import datetime
from typing import Any

# ── In-memory store ──────────────────────────────────────────────────────────
_environments: dict[str, dict] = {}

# Seed environments
_seeds = [
    {
        "id": "env-production",
        "name": "Production",
        "slug": "prod",
        "color": "#f87171",
        "icon": "server",
        "description": "Live production environment — customer-facing",
        "region": "us-east-1",
        "cluster": "pulse-prod-k8s",
        "node_count": 7,
        "alert_count": 3,
        "status": "healthy",
        "is_default": True,
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "env-staging",
        "name": "Staging",
        "slug": "staging",
        "color": "#fbbf24",
        "icon": "flask-conical",
        "description": "Pre-production staging — mirrors prod",
        "region": "us-east-1",
        "cluster": "pulse-staging-k8s",
        "node_count": 4,
        "alert_count": 1,
        "status": "healthy",
        "is_default": False,
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "env-development",
        "name": "Development",
        "slug": "dev",
        "color": "#34d399",
        "icon": "code",
        "description": "Development and testing environment",
        "region": "us-west-2",
        "cluster": "pulse-dev-k8s",
        "node_count": 2,
        "alert_count": 0,
        "status": "healthy",
        "is_default": False,
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "env-dr",
        "name": "Disaster Recovery",
        "slug": "dr",
        "color": "#a78bfa",
        "icon": "shield-check",
        "description": "DR site — warm standby in eu-west-1",
        "region": "eu-west-1",
        "cluster": "pulse-dr-k8s",
        "node_count": 3,
        "alert_count": 0,
        "status": "standby",
        "is_default": False,
        "created_at": datetime.utcnow().isoformat(),
    },
]

for e in _seeds:
    _environments[e["id"]] = e


# ── CRUD ─────────────────────────────────────────────────────────────────────

def list_environments() -> list[dict]:
    return sorted(_environments.values(), key=lambda e: (not e.get("is_default"), e["name"]))


def get_environment(env_id: str) -> dict | None:
    return _environments.get(env_id)


def get_default_environment() -> dict | None:
    for e in _environments.values():
        if e.get("is_default"):
            return e
    envs = list(_environments.values())
    return envs[0] if envs else None


def create_environment(data: dict) -> dict:
    eid = f"env-{uuid.uuid4().hex[:8]}"
    env = {
        "id": eid,
        "name": data.get("name", "New Environment"),
        "slug": data.get("slug", eid),
        "color": data.get("color", "#6366f1"),
        "icon": data.get("icon", "server"),
        "description": data.get("description", ""),
        "region": data.get("region", ""),
        "cluster": data.get("cluster", ""),
        "node_count": 0,
        "alert_count": 0,
        "status": "healthy",
        "is_default": False,
        "created_at": datetime.utcnow().isoformat(),
    }
    _environments[eid] = env
    return env


def update_environment(env_id: str, data: dict) -> dict | None:
    env = _environments.get(env_id)
    if not env:
        return None
    for k in ("name", "slug", "color", "icon", "description", "region", "cluster", "status"):
        if k in data:
            env[k] = data[k]
    return env


def delete_environment(env_id: str) -> bool:
    env = _environments.get(env_id)
    if not env or env.get("is_default"):
        return False
    del _environments[env_id]
    return True


def set_default(env_id: str) -> dict | None:
    env = _environments.get(env_id)
    if not env:
        return None
    for e in _environments.values():
        e["is_default"] = False
    env["is_default"] = True
    return env


def get_summary() -> dict:
    envs = list(_environments.values())
    return {
        "total": len(envs),
        "by_status": {
            "healthy": sum(1 for e in envs if e.get("status") == "healthy"),
            "degraded": sum(1 for e in envs if e.get("status") == "degraded"),
            "down": sum(1 for e in envs if e.get("status") == "down"),
            "standby": sum(1 for e in envs if e.get("status") == "standby"),
        },
        "total_nodes": sum(e.get("node_count", 0) for e in envs),
        "total_alerts": sum(e.get("alert_count", 0) for e in envs),
        "default": next((e["name"] for e in envs if e.get("is_default")), None),
    }
