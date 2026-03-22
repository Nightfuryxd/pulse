"""
Jira Integration — Bidirectional incident ↔ Jira ticket management for PULSE.

Features:
  - Auto-create Jira issues from PULSE incidents
  - Sync status changes both ways (PULSE → Jira, Jira → PULSE via webhook)
  - Attach RCA analysis to Jira tickets
  - Link related tickets across incidents

Requires: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY env vars.
"""
import os
import base64
from datetime import datetime
from typing import Optional

import httpx

# ── Configuration ────────────────────────────────────────────────────────────

JIRA_URL       = os.getenv("JIRA_URL", "")           # e.g. https://company.atlassian.net
JIRA_EMAIL     = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT   = os.getenv("JIRA_PROJECT_KEY", "OPS") # default project key

# PULSE severity → Jira priority mapping
SEVERITY_TO_PRIORITY = {
    "critical": "Highest",
    "high":     "High",
    "medium":   "Medium",
    "low":      "Low",
    "info":     "Lowest",
}

# Jira status → PULSE status mapping
JIRA_STATUS_MAP = {
    "To Do":       "open",
    "In Progress": "acknowledged",
    "Done":        "resolved",
    "Closed":      "resolved",
}

# Track created tickets: incident_id → jira_key
_ticket_cache: dict[int, str] = {}


def is_configured() -> bool:
    return bool(JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN)


def _get_auth_header() -> dict:
    creds = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Create ticket ────────────────────────────────────────────────────────────

async def create_ticket(incident: dict, rca: dict = None) -> dict:
    """Create a Jira issue from a PULSE incident."""
    if not is_configured():
        return {"error": "Jira not configured. Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN env vars."}

    incident_id = incident.get("id", 0)

    # Check if ticket already exists
    if incident_id in _ticket_cache:
        return {"already_exists": True, "key": _ticket_cache[incident_id]}

    severity = incident.get("severity", "medium")
    node_id = incident.get("node_id", "unknown")
    title = incident.get("title", "PULSE Incident")

    # Build description with RCA
    description_parts = [
        f"*PULSE Incident #{incident_id}*",
        f"",
        f"||Field||Value||",
        f"|Node|{node_id}|",
        f"|Severity|{severity.upper()}|",
        f"|Time|{incident.get('ts', datetime.utcnow().isoformat())}|",
    ]

    if rca:
        description_parts.extend([
            f"",
            f"h3. Root Cause Analysis",
            f"{rca.get('root_cause', 'Pending analysis')}",
            f"",
            f"*Confidence:* {rca.get('confidence', 'N/A')}",
            f"*Blast Radius:* {rca.get('blast_radius', 'N/A')}",
        ])
        actions = rca.get("recommended_actions", {}).get("immediate", [])
        if actions:
            description_parts.append(f"")
            description_parts.append(f"h3. Recommended Actions")
            for a in actions:
                description_parts.append(f"* {a}")

    description = "\n".join(description_parts)

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT},
            "summary": f"[PULSE] {title} — {node_id}",
            "description": description,
            "issuetype": {"name": "Bug"},
            "priority": {"name": SEVERITY_TO_PRIORITY.get(severity, "Medium")},
            "labels": ["pulse", "auto-created", f"severity-{severity}"],
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{JIRA_URL}/rest/api/2/issue",
                headers=_get_auth_header(),
                json=payload,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                jira_key = data.get("key", "")
                _ticket_cache[incident_id] = jira_key
                return {
                    "created": True,
                    "key": jira_key,
                    "url": f"{JIRA_URL}/browse/{jira_key}",
                    "incident_id": incident_id,
                }
            else:
                return {"error": f"Jira API error {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"error": f"Jira connection failed: {e}"}


# ── Update ticket ────────────────────────────────────────────────────────────

async def update_ticket(jira_key: str, updates: dict) -> dict:
    """Update a Jira issue (status, comment, etc.)."""
    if not is_configured():
        return {"error": "Jira not configured"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Add comment if provided
            if "comment" in updates:
                await client.post(
                    f"{JIRA_URL}/rest/api/2/issue/{jira_key}/comment",
                    headers=_get_auth_header(),
                    json={"body": updates["comment"]},
                )

            # Transition status if provided
            if "status" in updates:
                # Get available transitions
                resp = await client.get(
                    f"{JIRA_URL}/rest/api/2/issue/{jira_key}/transitions",
                    headers=_get_auth_header(),
                )
                if resp.status_code == 200:
                    transitions = resp.json().get("transitions", [])
                    target = updates["status"]
                    transition = next((t for t in transitions if t["name"].lower() == target.lower()), None)
                    if transition:
                        await client.post(
                            f"{JIRA_URL}/rest/api/2/issue/{jira_key}/transitions",
                            headers=_get_auth_header(),
                            json={"transition": {"id": transition["id"]}},
                        )

            return {"updated": True, "key": jira_key}
    except Exception as e:
        return {"error": f"Jira update failed: {e}"}


# ── Sync from Jira (webhook receiver) ────────────────────────────────────────

async def handle_jira_webhook(payload: dict) -> dict:
    """Process Jira webhook events — sync status changes back to PULSE."""
    event = payload.get("webhookEvent", "")
    issue = payload.get("issue", {})
    jira_key = issue.get("key", "")

    # Find matching incident
    incident_id = None
    for inc_id, key in _ticket_cache.items():
        if key == jira_key:
            incident_id = inc_id
            break

    if not incident_id:
        return {"ignored": True, "reason": "No matching PULSE incident"}

    result = {"incident_id": incident_id, "jira_key": jira_key, "event": event}

    if event == "jira:issue_updated":
        changelog = payload.get("changelog", {}).get("items", [])
        for change in changelog:
            if change.get("field") == "status":
                new_status = change.get("toString", "")
                pulse_status = JIRA_STATUS_MAP.get(new_status, "")
                if pulse_status:
                    result["status_sync"] = {"jira_status": new_status, "pulse_status": pulse_status}

    return result


# ── Query tickets ────────────────────────────────────────────────────────────

async def get_ticket(jira_key: str) -> dict:
    """Fetch a Jira ticket's current state."""
    if not is_configured():
        return {"error": "Jira not configured"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{JIRA_URL}/rest/api/2/issue/{jira_key}",
                headers=_get_auth_header(),
            )
            if resp.status_code == 200:
                data = resp.json()
                fields = data.get("fields", {})
                return {
                    "key": jira_key,
                    "summary": fields.get("summary", ""),
                    "status": fields.get("status", {}).get("name", ""),
                    "priority": fields.get("priority", {}).get("name", ""),
                    "assignee": fields.get("assignee", {}).get("displayName", "") if fields.get("assignee") else "",
                    "url": f"{JIRA_URL}/browse/{jira_key}",
                }
            return {"error": f"Jira API error {resp.status_code}"}
    except Exception as e:
        return {"error": f"Jira fetch failed: {e}"}


async def search_tickets(query: str = "project = OPS AND labels = pulse ORDER BY created DESC") -> dict:
    """Search Jira with JQL."""
    if not is_configured():
        return {"error": "Jira not configured"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{JIRA_URL}/rest/api/2/search",
                headers=_get_auth_header(),
                params={"jql": query, "maxResults": 20},
            )
            if resp.status_code == 200:
                data = resp.json()
                issues = []
                for issue in data.get("issues", []):
                    fields = issue.get("fields", {})
                    issues.append({
                        "key": issue.get("key"),
                        "summary": fields.get("summary", ""),
                        "status": fields.get("status", {}).get("name", ""),
                        "priority": fields.get("priority", {}).get("name", ""),
                        "created": fields.get("created", ""),
                    })
                return {"total": data.get("total", 0), "issues": issues}
            return {"error": f"Jira search error {resp.status_code}"}
    except Exception as e:
        return {"error": f"Jira search failed: {e}"}


def get_ticket_for_incident(incident_id: int) -> Optional[str]:
    """Get the Jira ticket key for a PULSE incident."""
    return _ticket_cache.get(incident_id)
