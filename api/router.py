"""
Team Router + Notification Bridge.

Routes incidents to the right teams based on category/RCA output,
then dispatches notifications to all configured providers per team.
Supports: Slack, Teams, Discord, Telegram, Google Chat, Zoom,
PagerDuty, Opsgenie, Email, SMS, Generic Webhooks.
"""
import os
from pathlib import Path
from datetime import datetime
import yaml

from notifications import format_incident_payload, notify_all_teams
from escalation import is_in_maintenance, register_escalation


def load_teams() -> list[dict]:
    path = Path("config/teams.yaml")
    if not path.exists():
        path = Path("/app/config/teams.yaml")
    with open(path) as f:
        return yaml.safe_load(f).get("teams", [])


def route_incident(categories: list[str], rca: dict) -> dict:
    """
    Determine which teams own and should be looped in on this incident.
    Returns {"owners": [...], "observers": [...]}
    """
    teams = load_teams()

    # Use RCA owning_teams if available (AI-determined)
    ai_owners    = rca.get("owning_teams", [])
    ai_observers = rca.get("escalate_to", [])

    # Also match by category as fallback/supplement
    cat_owners = set()
    for team in teams:
        for domain in team.get("domains", []):
            if any(domain in cat or cat in domain for cat in categories):
                cat_owners.add(team["id"])

    owner_ids    = list(set(ai_owners) | cat_owners)
    observer_ids = [t for t in ai_observers if t not in owner_ids]

    # Build full team objects
    team_map   = {t["id"]: t for t in teams}
    owners     = [team_map[tid] for tid in owner_ids    if tid in team_map]
    observers  = [team_map[tid] for tid in observer_ids if tid in team_map]

    return {"owners": owners, "observers": observers}


async def bridge_incident(incident: dict, teams_routing: dict, rca: dict) -> dict:
    """
    Send notifications for an incident to all routed teams via all their
    configured channels. Checks maintenance windows and registers escalation.
    """
    node_id = incident.get("node_id", "")
    categories = [rca.get("category", "")]

    # Check maintenance window — suppress if node is in maintenance
    if is_in_maintenance(node_id, categories):
        return {
            "notified": False,
            "reason": "maintenance_window",
            "ts": datetime.utcnow().isoformat(),
        }

    # Format the universal payload
    payload = format_incident_payload(incident, rca, teams_routing)

    # Send to all teams via all their configured providers
    result = await notify_all_teams(teams_routing, payload)

    # Register for escalation tracking
    register_escalation(incident.get("id", 0), incident, rca, teams_routing)

    return result
