"""
PULSE Escalation Engine — Multi-step escalation + maintenance windows.

Escalation: If an incident is not acknowledged within X minutes,
automatically escalate to the next tier (e.g., manager, then VP).

Maintenance Windows: Suppress notifications for specific nodes/groups
during planned maintenance periods.
"""
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import yaml

from notifications import format_incident_payload, notify_all_teams


# ── Locks for mutable state ──────────────────────────────────────────────────
_maintenance_lock = asyncio.Lock()
_escalation_lock = asyncio.Lock()

# ── Maintenance Windows ──────────────────────────────────────────────────────

_maintenance_windows: list[dict] = []


def load_maintenance_windows() -> list[dict]:
    """Load maintenance windows from config."""
    path = Path("config/maintenance.yaml")
    if not path.exists():
        path = Path("/app/config/maintenance.yaml")
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("windows") or []


async def add_maintenance_window(window: dict):
    """Add a runtime maintenance window (API-created)."""
    async with _maintenance_lock:
        _maintenance_windows.append(window)


async def remove_maintenance_window(window_id: str):
    """Remove a runtime maintenance window by ID."""
    global _maintenance_windows
    async with _maintenance_lock:
        _maintenance_windows = [w for w in _maintenance_windows if w.get("id") != window_id]


def is_in_maintenance(node_id: str, categories: Optional[list[str]] = None) -> bool:
    """Check if a node is currently in a maintenance window."""
    now = datetime.utcnow()
    all_windows = load_maintenance_windows() + _maintenance_windows

    for window in all_windows:
        # Parse time range
        start = _parse_time(window.get("start"))
        end = _parse_time(window.get("end"))
        if not start or not end:
            continue
        if not (start <= now <= end):
            continue

        # Check node match
        targets = window.get("targets", [])
        if targets and node_id not in targets and "*" not in targets:
            continue

        # Check category suppression
        suppress_categories = window.get("suppress_categories", [])
        if suppress_categories and categories:
            if not any(c in suppress_categories for c in categories):
                continue

        return True

    return False


def get_active_maintenance_windows() -> list[dict]:
    """Return all currently active maintenance windows."""
    now = datetime.utcnow()
    all_windows = load_maintenance_windows() + _maintenance_windows
    active = []
    for w in all_windows:
        start = _parse_time(w.get("start"))
        end = _parse_time(w.get("end"))
        if start and end and start <= now <= end:
            active.append(w)
    return active


def _parse_time(val) -> Optional[datetime]:
    """Parse a datetime string or return None."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
    return None


# ── Escalation Engine ────────────────────────────────────────────────────────

_escalation_policies: dict = {}
_pending_escalations: dict[int, dict] = {}  # incident_id -> escalation state


def load_escalation_policies() -> dict:
    """Load escalation policies from config."""
    path = Path("config/escalation.yaml")
    if not path.exists():
        path = Path("/app/config/escalation.yaml")
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data


def get_escalation_policy(severity: str) -> Optional[dict]:
    """Get the escalation policy for a given severity."""
    policies = load_escalation_policies()
    return policies.get("policies", {}).get(severity.lower())


async def register_escalation(incident_id: int, incident: dict, rca: dict, teams_routing: dict):
    """Register an incident for escalation tracking."""
    severity = incident.get("severity", "medium")
    policy = get_escalation_policy(severity)
    if not policy:
        return

    async with _escalation_lock:
        _pending_escalations[incident_id] = {
            "incident": incident,
            "rca": rca,
            "teams_routing": teams_routing,
            "created_at": datetime.utcnow(),
            "current_tier": 0,
            "tiers": policy.get("tiers", []),
            "acknowledged": False,
        }


async def acknowledge_incident(incident_id: int) -> bool:
    """Mark an incident as acknowledged — stops escalation."""
    async with _escalation_lock:
        if incident_id in _pending_escalations:
            _pending_escalations[incident_id]["acknowledged"] = True
            return True
        return False


async def check_escalations():
    """Check all pending escalations and escalate if needed. Run periodically."""
    now = datetime.utcnow()
    teams_config = _load_teams_for_escalation()

    async with _escalation_lock:
        for inc_id, state in list(_pending_escalations.items()):
            if state["acknowledged"]:
                continue

            tiers = state["tiers"]
            current_tier = state["current_tier"]

            if current_tier >= len(tiers):
                continue  # All tiers exhausted

            tier = tiers[current_tier]
            wait_minutes = tier.get("after_minutes", 5)
            elapsed = (now - state["created_at"]).total_seconds() / 60

            if elapsed >= wait_minutes:
                # Escalate to this tier
                escalation_targets = tier.get("notify", [])
                payload = format_incident_payload(
                    state["incident"], state["rca"], state["teams_routing"]
                )
                payload["title"] = f"[ESCALATION L{current_tier + 1}] {payload['title']}"

                # Build teams_routing for escalation targets
                esc_teams = {"owners": [], "observers": []}
                for target in escalation_targets:
                    team = teams_config.get(target)
                    if team:
                        esc_teams["owners"].append(team)

                if esc_teams["owners"]:
                    await notify_all_teams(esc_teams, payload)
                    print(f"[PULSE] Escalation L{current_tier + 1} for Incident #{inc_id} -> {escalation_targets}")

                state["current_tier"] = current_tier + 1


def _load_teams_for_escalation() -> dict:
    """Load team map for escalation routing."""
    path = Path("config/teams.yaml")
    if not path.exists():
        path = Path("/app/config/teams.yaml")
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return {t["id"]: t for t in data.get("teams", [])}


async def escalation_loop():
    """Background loop that checks escalations every 30 seconds."""
    while True:
        try:
            await check_escalations()
        except Exception as e:
            print(f"[PULSE] Escalation check error: {e}")
        await asyncio.sleep(30)
