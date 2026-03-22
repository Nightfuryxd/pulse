"""
Notification Center — persistent in-app notification feed.
Replaces ephemeral toasts with a scrollable, filterable history.
"""
import uuid
from datetime import datetime
from typing import Any

# ── In-memory store ──────────────────────────────────────────────────────────
_notifications: list[dict] = []
MAX_NOTIFICATIONS = 500

# Notification types
TYPES = ["alert", "incident", "oncall", "deployment", "system", "security"]

# Seed some demo notifications
_seeds = [
    ("alert", "critical", "CPU Critical on node-1", "CPU usage exceeded 95% for 3 minutes", 5),
    ("incident", "high", "INC-42: Database Connection Pool Exhaustion", "AI RCA identified root cause: max_connections limit reached", 12),
    ("oncall", "info", "On-Call Handoff", "Alex Chen is now on-call for Primary rotation", 60),
    ("system", "info", "PULSE v5.0 Deployed", "New features: Custom Dashboards, On-Call, Status Page", 120),
    ("security", "high", "Port Scan Detected", "20+ ports scanned from 192.168.1.105", 30),
    ("alert", "medium", "Memory Warning on node-2", "Memory usage at 87% — approaching threshold", 8),
    ("deployment", "info", "Playbook Executed", "auto-restart-service ran successfully on node-1", 15),
    ("incident", "critical", "INC-43: API Latency Spike", "P99 latency exceeded 2s on /api/metrics endpoint", 2),
]
from datetime import timedelta
for _type, _sev, _title, _body, _mins_ago in _seeds:
    _notifications.append({
        "id": f"notif-{uuid.uuid4().hex[:8]}",
        "type": _type,
        "severity": _sev,
        "title": _title,
        "body": _body,
        "read": _mins_ago > 30,
        "created_at": (datetime.utcnow() - timedelta(minutes=_mins_ago)).isoformat(),
        "source": None,
        "action_url": None,
    })


def push(ntype: str, severity: str, title: str, body: str = "",
         source: str | None = None, action_url: str | None = None) -> dict:
    """Push a new notification to the center."""
    notif = {
        "id": f"notif-{uuid.uuid4().hex[:8]}",
        "type": ntype if ntype in TYPES else "system",
        "severity": severity,
        "title": title,
        "body": body,
        "read": False,
        "created_at": datetime.utcnow().isoformat(),
        "source": source,
        "action_url": action_url,
    }
    _notifications.insert(0, notif)
    if len(_notifications) > MAX_NOTIFICATIONS:
        _notifications.pop()
    return notif


def list_notifications(limit: int = 50, ntype: str | None = None,
                       unread_only: bool = False) -> list[dict]:
    result = _notifications
    if ntype:
        result = [n for n in result if n["type"] == ntype]
    if unread_only:
        result = [n for n in result if not n["read"]]
    return result[:limit]


def get_unread_count() -> int:
    return sum(1 for n in _notifications if not n["read"])


def mark_read(notif_id: str) -> bool:
    for n in _notifications:
        if n["id"] == notif_id:
            n["read"] = True
            return True
    return False


def mark_all_read() -> int:
    count = 0
    for n in _notifications:
        if not n["read"]:
            n["read"] = True
            count += 1
    return count


def delete_notification(notif_id: str) -> bool:
    global _notifications
    before = len(_notifications)
    _notifications = [n for n in _notifications if n["id"] != notif_id]
    return len(_notifications) < before


def get_summary() -> dict:
    """Counts by type for the notification panel header."""
    unread = [n for n in _notifications if not n["read"]]
    by_type = {}
    for n in unread:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    return {
        "total_unread": len(unread),
        "by_type": by_type,
        "latest": _notifications[0] if _notifications else None,
    }
