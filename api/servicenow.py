"""
ServiceNow Integration — Enterprise ITSM integration for PULSE.

Creates and manages ServiceNow incidents from PULSE alerts/incidents.
Syncs status bidirectionally via webhooks.

Requires: SNOW_INSTANCE, SNOW_USERNAME, SNOW_PASSWORD env vars.
"""
import os
from datetime import datetime
from typing import Optional

import httpx

# ── Configuration ────────────────────────────────────────────────────────────

SNOW_INSTANCE = os.getenv("SNOW_INSTANCE", "")   # e.g. "company.service-now.com"
SNOW_USERNAME = os.getenv("SNOW_USERNAME", "")
SNOW_PASSWORD = os.getenv("SNOW_PASSWORD", "")
SNOW_CALLER   = os.getenv("SNOW_CALLER_ID", "")  # sys_id of default caller

# PULSE severity → ServiceNow impact/urgency
SEVERITY_MAP = {
    "critical": {"impact": "1", "urgency": "1"},  # 1-High
    "high":     {"impact": "2", "urgency": "1"},
    "medium":   {"impact": "2", "urgency": "2"},  # 2-Medium
    "low":      {"impact": "3", "urgency": "3"},  # 3-Low
    "info":     {"impact": "3", "urgency": "3"},
}

# ServiceNow state → PULSE status
SNOW_STATE_MAP = {
    "1": "open",          # New
    "2": "acknowledged",  # In Progress
    "3": "acknowledged",  # On Hold
    "6": "resolved",      # Resolved
    "7": "resolved",      # Closed
}

_ticket_cache: dict[int, str] = {}  # incident_id → sys_id


def is_configured() -> bool:
    return bool(SNOW_INSTANCE and SNOW_USERNAME and SNOW_PASSWORD)


def _get_base_url() -> str:
    instance = SNOW_INSTANCE
    if not instance.startswith("http"):
        instance = f"https://{instance}"
    return instance


# ── Create incident ──────────────────────────────────────────────────────────

async def create_incident(incident: dict, rca: dict = None) -> dict:
    """Create a ServiceNow incident from a PULSE incident."""
    if not is_configured():
        return {"error": "ServiceNow not configured. Set SNOW_INSTANCE, SNOW_USERNAME, SNOW_PASSWORD env vars."}

    incident_id = incident.get("id", 0)
    if incident_id in _ticket_cache:
        return {"already_exists": True, "sys_id": _ticket_cache[incident_id]}

    severity = incident.get("severity", "medium")
    node_id = incident.get("node_id", "unknown")
    title = incident.get("title", "PULSE Incident")
    sev_map = SEVERITY_MAP.get(severity, SEVERITY_MAP["medium"])

    description = f"PULSE Incident #{incident_id}\n"
    description += f"Node: {node_id}\n"
    description += f"Severity: {severity.upper()}\n"
    description += f"Time: {incident.get('ts', datetime.utcnow().isoformat())}\n"

    if rca:
        description += f"\n--- Root Cause Analysis ---\n"
        description += f"{rca.get('root_cause', 'Pending')}\n"
        description += f"Confidence: {rca.get('confidence', 'N/A')}\n"
        actions = rca.get("recommended_actions", {}).get("immediate", [])
        if actions:
            description += "\nRecommended Actions:\n"
            for a in actions:
                description += f"  - {a}\n"

    payload = {
        "short_description": f"[PULSE] {title} - {node_id}",
        "description": description,
        "impact": sev_map["impact"],
        "urgency": sev_map["urgency"],
        "category": "Infrastructure",
        "subcategory": "Monitoring",
    }
    if SNOW_CALLER:
        payload["caller_id"] = SNOW_CALLER

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_get_base_url()}/api/now/table/incident",
                auth=(SNOW_USERNAME, SNOW_PASSWORD),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
            )
            if resp.status_code in (200, 201):
                data = resp.json().get("result", {})
                sys_id = data.get("sys_id", "")
                number = data.get("number", "")
                _ticket_cache[incident_id] = sys_id
                return {
                    "created": True,
                    "sys_id": sys_id,
                    "number": number,
                    "url": f"{_get_base_url()}/nav_to.do?uri=incident.do?sys_id={sys_id}",
                    "incident_id": incident_id,
                }
            return {"error": f"ServiceNow API error {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"error": f"ServiceNow connection failed: {e}"}


# ── Update incident ──────────────────────────────────────────────────────────

async def update_incident(sys_id: str, updates: dict) -> dict:
    """Update a ServiceNow incident."""
    if not is_configured():
        return {"error": "ServiceNow not configured"}

    payload = {}
    if "comment" in updates:
        payload["comments"] = updates["comment"]
    if "state" in updates:
        payload["state"] = updates["state"]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.patch(
                f"{_get_base_url()}/api/now/table/incident/{sys_id}",
                auth=(SNOW_USERNAME, SNOW_PASSWORD),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
            )
            if resp.status_code == 200:
                return {"updated": True, "sys_id": sys_id}
            return {"error": f"ServiceNow update error {resp.status_code}"}
    except Exception as e:
        return {"error": f"ServiceNow update failed: {e}"}


# ── Webhook receiver ────────────────────────────────────────────────────────

async def handle_webhook(payload: dict) -> dict:
    """Process ServiceNow webhook — sync status back to PULSE."""
    sys_id = payload.get("sys_id", "")
    state = payload.get("state", "")

    incident_id = None
    for inc_id, sid in _ticket_cache.items():
        if sid == sys_id:
            incident_id = inc_id
            break

    if not incident_id:
        return {"ignored": True, "reason": "No matching PULSE incident"}

    pulse_status = SNOW_STATE_MAP.get(state, "")
    return {
        "incident_id": incident_id,
        "sys_id": sys_id,
        "status_sync": {"snow_state": state, "pulse_status": pulse_status} if pulse_status else None,
    }


# ── Query ────────────────────────────────────────────────────────────────────

async def get_incident_by_sysid(sys_id: str) -> dict:
    """Fetch a ServiceNow incident."""
    if not is_configured():
        return {"error": "ServiceNow not configured"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{_get_base_url()}/api/now/table/incident/{sys_id}",
                auth=(SNOW_USERNAME, SNOW_PASSWORD),
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json().get("result", {})
                return {
                    "sys_id": sys_id,
                    "number": data.get("number", ""),
                    "short_description": data.get("short_description", ""),
                    "state": data.get("state", ""),
                    "impact": data.get("impact", ""),
                    "urgency": data.get("urgency", ""),
                }
            return {"error": f"ServiceNow fetch error {resp.status_code}"}
    except Exception as e:
        return {"error": f"ServiceNow fetch failed: {e}"}


def get_ticket_for_incident(incident_id: int) -> Optional[str]:
    return _ticket_cache.get(incident_id)
