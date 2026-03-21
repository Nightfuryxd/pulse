"""
Team Router + Collaboration Bridge.

Routes incidents to the right teams based on category/RCA output,
then optionally bridges a call via Slack/Teams.
"""
import json
import os
from pathlib import Path
from datetime import datetime
import httpx
import yaml


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


async def create_slack_bridge(incident: dict, teams: dict, rca: dict) -> dict:
    """
    Create a Slack channel for the incident and post a context brief to all teams.
    Returns bridge details dict.
    """
    token = os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        return {"status": "skipped", "reason": "SLACK_BOT_TOKEN not configured"}

    channel_name = f"inc-{incident['id']}-{datetime.utcnow().strftime('%m%d-%H%M')}"
    all_teams    = teams.get("owners", []) + teams.get("observers", [])
    team_names   = ", ".join(t["name"] for t in all_teams)

    # Format the context brief
    rca_text = (
        f"*Root Cause:* {rca.get('root_cause', 'Investigating...')}\n"
        f"*Confidence:* {rca.get('confidence', 'low')}\n"
        f"*Blast Radius:* {rca.get('blast_radius', 'Unknown')}\n\n"
        f"*Immediate Actions:*\n" +
        "\n".join(f"• {a}" for a in rca.get("recommended_actions", {}).get("immediate", [])) +
        f"\n\n*Stack Advice:*\n{rca.get('stack_specific_advice', 'N/A')}"
    )

    context_block = {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"[{incident['severity'].upper()}] {incident['title']}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Node:* `{incident['node_id']}` | *Time:* {incident['ts']}\n*Teams paged:* {team_names}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": rca_text}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"_Full incident: PULSE dashboard — Incident #{incident['id']}_"}},
        ]
    }

    results = {}
    async with httpx.AsyncClient(timeout=10) as http:
        # Notify each team's channel
        for team in all_teams:
            slack_channel = team.get("contact", {}).get("slack", "")
            if not slack_channel:
                continue
            try:
                resp = await http.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"channel": slack_channel, **context_block},
                )
                results[team["id"]] = resp.json().get("ok", False)
            except Exception as e:
                results[team["id"]] = f"error: {e}"

    return {
        "status":  "sent" if any(results.values()) else "failed",
        "channel": channel_name,
        "teams_notified": list(results.keys()),
        "results": results,
    }


async def send_teams_bridge(incident: dict, teams_routing: dict, rca: dict) -> dict:
    """Send Microsoft Teams adaptive card to all team channels."""
    webhook = os.getenv("TEAMS_WEBHOOK_URL", "")
    if not webhook:
        return {"status": "skipped", "reason": "TEAMS_WEBHOOK_URL not configured"}

    all_teams = teams_routing.get("owners", []) + teams_routing.get("observers", [])
    payload   = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "FF0000" if incident["severity"] == "critical" else "FFA500",
        "summary": f"[PULSE] {incident['title']}",
        "sections": [{
            "activityTitle": f"[{incident['severity'].upper()}] {incident['title']}",
            "activitySubtitle": f"Node: {incident['node_id']} | Teams: {', '.join(t['name'] for t in all_teams)}",
            "facts": [
                {"name": "Root Cause", "value": rca.get("root_cause", "Investigating")},
                {"name": "Confidence", "value": rca.get("confidence", "low")},
                {"name": "Blast Radius", "value": rca.get("blast_radius", "Unknown")},
                {"name": "Immediate Action", "value": (rca.get("recommended_actions", {}).get("immediate", ["Investigate"]))[0]},
            ],
        }],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(webhook, json=payload)
            return {"status": "sent" if resp.status_code == 200 else "failed", "code": resp.status_code}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


async def bridge_incident(incident: dict, teams_routing: dict, rca: dict) -> dict:
    """
    Bridge all relevant teams for an incident.
    Tries Slack first, Teams second, returns combined result.
    """
    results = {}

    slack_result = await create_slack_bridge(incident, teams_routing, rca)
    results["slack"] = slack_result

    teams_result = await send_teams_bridge(incident, teams_routing, rca)
    results["teams"] = teams_result

    bridged = slack_result.get("status") == "sent" or teams_result.get("status") == "sent"
    return {
        "bridged":  bridged,
        "channels": results,
        "ts":       datetime.utcnow().isoformat(),
    }
