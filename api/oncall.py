"""
On-Call Scheduling & Escalation — PagerDuty replacement.
Supports rotation schedules, overrides, escalation policies, and ack tracking.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any

# ── In-memory stores ─────────────────────────────────────────────────────────
_schedules: dict[str, dict] = {}
_overrides: list[dict] = []
_escalation_policies: dict[str, dict] = {}
_oncall_events: list[dict] = []  # audit log of pages

# Seed demo data
_demo_schedule_id = "sched-default"
_schedules[_demo_schedule_id] = {
    "id": _demo_schedule_id,
    "name": "Primary On-Call",
    "description": "Main infrastructure on-call rotation",
    "timezone": "UTC",
    "rotation_type": "weekly",  # daily, weekly, custom
    "handoff_time": "09:00",
    "members": [
        {"id": "m1", "name": "Aniket Gupta", "email": "aniket@pulse.dev", "phone": "+1-555-0100"},
        {"id": "m2", "name": "Alex Chen", "email": "alex@pulse.dev", "phone": "+1-555-0101"},
        {"id": "m3", "name": "Sarah Kim", "email": "sarah@pulse.dev", "phone": "+1-555-0102"},
    ],
    "created_at": datetime.utcnow().isoformat(),
}

_demo_policy_id = "esc-default"
_escalation_policies[_demo_policy_id] = {
    "id": _demo_policy_id,
    "name": "Default Escalation",
    "rules": [
        {"level": 1, "target": "current_oncall", "schedule_id": _demo_schedule_id,
         "timeout_minutes": 5, "notify_via": ["email", "sms"]},
        {"level": 2, "target": "all_members", "schedule_id": _demo_schedule_id,
         "timeout_minutes": 15, "notify_via": ["email", "sms", "phone"]},
        {"level": 3, "target": "manager", "email": "manager@pulse.dev",
         "timeout_minutes": 30, "notify_via": ["phone"]},
    ],
}


def _current_week_index() -> int:
    """Week number since epoch, for rotation."""
    return int((datetime.utcnow() - datetime(2024, 1, 1)).days / 7)


def get_current_oncall(schedule_id: str | None = None) -> dict | None:
    sid = schedule_id or _demo_schedule_id
    sched = _schedules.get(sid)
    if not sched or not sched["members"]:
        return None

    # Check overrides first
    now = datetime.utcnow()
    for ov in _overrides:
        if ov["schedule_id"] == sid:
            start = datetime.fromisoformat(ov["start"])
            end = datetime.fromisoformat(ov["end"])
            if start <= now <= end:
                return {"schedule": sched["name"], "oncall": ov["user"], "override": True,
                        "until": ov["end"]}

    # Normal rotation
    members = sched["members"]
    if sched["rotation_type"] == "daily":
        idx = (now - datetime(2024, 1, 1)).days % len(members)
    else:
        idx = _current_week_index() % len(members)

    member = members[idx]
    next_idx = (idx + 1) % len(members)

    # Calculate next handoff
    handoff_h, handoff_m = map(int, sched.get("handoff_time", "09:00").split(":"))
    if sched["rotation_type"] == "daily":
        next_handoff = (now + timedelta(days=1)).replace(hour=handoff_h, minute=handoff_m, second=0)
    else:
        days_until_monday = (7 - now.weekday()) % 7 or 7
        next_handoff = (now + timedelta(days=days_until_monday)).replace(hour=handoff_h, minute=handoff_m, second=0)

    return {
        "schedule": sched["name"],
        "schedule_id": sid,
        "oncall": member,
        "next_oncall": members[next_idx],
        "rotation_type": sched["rotation_type"],
        "next_handoff": next_handoff.isoformat(),
        "override": False,
    }


# ── Schedule CRUD ────────────────────────────────────────────────────────────

def list_schedules() -> list[dict]:
    result = []
    for s in _schedules.values():
        oncall = get_current_oncall(s["id"])
        result.append({**s, "current_oncall": oncall})
    return result


def get_schedule(schedule_id: str) -> dict | None:
    sched = _schedules.get(schedule_id)
    if sched:
        sched = {**sched, "current_oncall": get_current_oncall(schedule_id)}
    return sched


def create_schedule(data: dict) -> dict:
    sid = f"sched-{uuid.uuid4().hex[:8]}"
    schedule = {
        "id": sid,
        "name": data.get("name", "New Schedule"),
        "description": data.get("description", ""),
        "timezone": data.get("timezone", "UTC"),
        "rotation_type": data.get("rotation_type", "weekly"),
        "handoff_time": data.get("handoff_time", "09:00"),
        "members": data.get("members", []),
        "created_at": datetime.utcnow().isoformat(),
    }
    # Ensure members have IDs
    for i, m in enumerate(schedule["members"]):
        if "id" not in m:
            m["id"] = f"m-{uuid.uuid4().hex[:6]}"
    _schedules[sid] = schedule
    return schedule


def update_schedule(schedule_id: str, data: dict) -> dict | None:
    sched = _schedules.get(schedule_id)
    if not sched:
        return None
    for key in ("name", "description", "timezone", "rotation_type", "handoff_time", "members"):
        if key in data:
            sched[key] = data[key]
    return sched


def delete_schedule(schedule_id: str) -> bool:
    if schedule_id in _schedules:
        del _schedules[schedule_id]
        return True
    return False


# ── Overrides ────────────────────────────────────────────────────────────────

def create_override(data: dict) -> dict:
    override = {
        "id": f"ov-{uuid.uuid4().hex[:6]}",
        "schedule_id": data.get("schedule_id", _demo_schedule_id),
        "user": data.get("user", {}),
        "start": data.get("start", datetime.utcnow().isoformat()),
        "end": data.get("end", (datetime.utcnow() + timedelta(hours=8)).isoformat()),
        "reason": data.get("reason", ""),
    }
    _overrides.append(override)
    return override


def list_overrides(schedule_id: str | None = None) -> list[dict]:
    if schedule_id:
        return [o for o in _overrides if o["schedule_id"] == schedule_id]
    return _overrides


def delete_override(override_id: str) -> bool:
    global _overrides
    before = len(_overrides)
    _overrides = [o for o in _overrides if o["id"] != override_id]
    return len(_overrides) < before


# ── Escalation Policies ──────────────────────────────────────────────────────

def list_policies() -> list[dict]:
    return list(_escalation_policies.values())


def get_policy(policy_id: str) -> dict | None:
    return _escalation_policies.get(policy_id)


def create_policy(data: dict) -> dict:
    pid = f"esc-{uuid.uuid4().hex[:8]}"
    policy = {
        "id": pid,
        "name": data.get("name", "New Policy"),
        "rules": data.get("rules", []),
    }
    _escalation_policies[pid] = policy
    return policy


def update_policy(policy_id: str, data: dict) -> dict | None:
    policy = _escalation_policies.get(policy_id)
    if not policy:
        return None
    for key in ("name", "rules"):
        if key in data:
            policy[key] = data[key]
    return policy


# ── On-Call Events / Pages ───────────────────────────────────────────────────

def log_page(incident_id: str, schedule_id: str, level: int, target: dict) -> dict:
    event = {
        "id": f"page-{uuid.uuid4().hex[:6]}",
        "incident_id": incident_id,
        "schedule_id": schedule_id,
        "level": level,
        "target": target,
        "status": "pending",  # pending, acknowledged, escalated, resolved
        "paged_at": datetime.utcnow().isoformat(),
        "acked_at": None,
    }
    _oncall_events.append(event)
    if len(_oncall_events) > 500:
        _oncall_events.pop(0)
    return event


def get_oncall_events(limit: int = 50) -> list[dict]:
    return list(reversed(_oncall_events[-limit:]))


def get_oncall_summary() -> dict:
    """Summary for the dashboard stat strip."""
    now = datetime.utcnow()
    schedules = list(_schedules.values())
    active_oncall = []
    for s in schedules:
        oc = get_current_oncall(s["id"])
        if oc:
            active_oncall.append(oc)

    pending_pages = sum(1 for e in _oncall_events if e["status"] == "pending")

    return {
        "total_schedules": len(schedules),
        "active_oncall": active_oncall,
        "pending_pages": pending_pages,
        "total_pages_today": sum(
            1 for e in _oncall_events
            if e["paged_at"][:10] == now.isoformat()[:10]
        ),
    }
