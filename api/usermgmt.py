"""
User & Team Management — invite users, assign roles, manage teams.
"""
import uuid
from datetime import datetime
from typing import Any

# ── In-memory stores ─────────────────────────────────────────────────────────
_users: dict[str, dict] = {}
_invites: list[dict] = []

ROLES = [
    {"id": "admin", "name": "Admin", "description": "Full access to all features and settings", "color": "#f87171"},
    {"id": "editor", "name": "Editor", "description": "Can create/edit alerts, dashboards, and workflows", "color": "#fbbf24"},
    {"id": "viewer", "name": "Viewer", "description": "Read-only access to dashboards and data", "color": "#34d399"},
    {"id": "responder", "name": "Responder", "description": "Can acknowledge and resolve incidents", "color": "#6366f1"},
]

# Seed users
_seeds = [
    {"id": "user-1", "name": "Aniket Gupta", "email": "aniket@pulse.dev", "role": "admin",
     "status": "active", "last_login": datetime.utcnow().isoformat(),
     "avatar_color": "#6366f1", "teams": ["team-platform"]},
    {"id": "user-2", "name": "Alex Chen", "email": "alex@pulse.dev", "role": "editor",
     "status": "active", "last_login": (datetime.utcnow()).isoformat(),
     "avatar_color": "#22d3ee", "teams": ["team-platform"]},
    {"id": "user-3", "name": "Sarah Kim", "email": "sarah@pulse.dev", "role": "responder",
     "status": "active", "last_login": (datetime.utcnow()).isoformat(),
     "avatar_color": "#34d399", "teams": ["team-platform"]},
    {"id": "user-4", "name": "Jordan Lee", "email": "jordan@pulse.dev", "role": "editor",
     "status": "active", "last_login": None,
     "avatar_color": "#fbbf24", "teams": ["team-backend"]},
    {"id": "user-5", "name": "Maria Santos", "email": "maria@pulse.dev", "role": "viewer",
     "status": "active", "last_login": None,
     "avatar_color": "#a78bfa", "teams": ["team-backend"]},
    {"id": "user-6", "name": "Chris Wang", "email": "chris@pulse.dev", "role": "editor",
     "status": "inactive", "last_login": None,
     "avatar_color": "#fb923c", "teams": ["team-data"]},
    {"id": "user-7", "name": "Priya Patel", "email": "priya@pulse.dev", "role": "viewer",
     "status": "invited", "last_login": None,
     "avatar_color": "#ec4899", "teams": ["team-data"]},
]

for u in _seeds:
    u["created_at"] = datetime.utcnow().isoformat()
    _users[u["id"]] = u


# ── User CRUD ────────────────────────────────────────────────────────────────

def list_users(role: str | None = None, status: str | None = None) -> list[dict]:
    result = list(_users.values())
    if role:
        result = [u for u in result if u.get("role") == role]
    if status:
        result = [u for u in result if u.get("status") == status]
    return sorted(result, key=lambda u: u["name"])


def get_user(user_id: str) -> dict | None:
    return _users.get(user_id)


def invite_user(data: dict) -> dict:
    uid = f"user-{uuid.uuid4().hex[:6]}"
    user = {
        "id": uid,
        "name": data.get("name", ""),
        "email": data.get("email", ""),
        "role": data.get("role", "viewer"),
        "status": "invited",
        "last_login": None,
        "avatar_color": data.get("avatar_color", "#6366f1"),
        "teams": data.get("teams", []),
        "created_at": datetime.utcnow().isoformat(),
    }
    _users[uid] = user

    invite = {
        "id": f"inv-{uuid.uuid4().hex[:6]}",
        "user_id": uid,
        "email": user["email"],
        "role": user["role"],
        "invited_by": data.get("invited_by", "admin"),
        "created_at": datetime.utcnow().isoformat(),
        "status": "pending",
    }
    _invites.append(invite)
    return user


def update_user(user_id: str, data: dict) -> dict | None:
    user = _users.get(user_id)
    if not user:
        return None
    for k in ("name", "email", "role", "status", "teams", "avatar_color"):
        if k in data:
            user[k] = data[k]
    return user


def deactivate_user(user_id: str) -> dict | None:
    user = _users.get(user_id)
    if not user:
        return None
    user["status"] = "inactive"
    return user


def reactivate_user(user_id: str) -> dict | None:
    user = _users.get(user_id)
    if not user:
        return None
    user["status"] = "active"
    return user


def change_role(user_id: str, role: str) -> dict | None:
    user = _users.get(user_id)
    if not user:
        return None
    if role not in [r["id"] for r in ROLES]:
        return None
    user["role"] = role
    return user


def get_invites() -> list[dict]:
    return list(reversed(_invites))


def get_roles() -> list[dict]:
    return ROLES


def get_summary() -> dict:
    users = list(_users.values())
    return {
        "total_users": len(users),
        "active": sum(1 for u in users if u.get("status") == "active"),
        "invited": sum(1 for u in users if u.get("status") == "invited"),
        "inactive": sum(1 for u in users if u.get("status") == "inactive"),
        "by_role": {r["id"]: sum(1 for u in users if u.get("role") == r["id"]) for r in ROLES},
        "pending_invites": sum(1 for i in _invites if i.get("status") == "pending"),
    }
