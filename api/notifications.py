"""
PULSE Notification Engine — Provider-based alerting to any platform.

Supports: Slack, Microsoft Teams, Discord, Telegram, Google Chat, Zoom,
PagerDuty, Opsgenie, Email (SMTP), SMS (Twilio), Generic Webhooks.

Each provider is a simple async function that takes a formatted payload
and delivers it. Teams.yaml defines which providers each team uses.
"""
import asyncio
import json
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import httpx


# ── Payload Formatter ────────────────────────────────────────────────────────

def format_incident_payload(incident: dict, rca: dict, teams_routing: dict) -> dict:
    """Build a universal payload dict that providers adapt to their format."""
    all_teams = teams_routing.get("owners", []) + teams_routing.get("observers", [])
    team_names = ", ".join(t["name"] for t in all_teams)
    severity = incident.get("severity", "unknown").upper()
    title = incident.get("title", "Unknown Incident")
    node_id = incident.get("node_id", "unknown")
    ts = incident.get("ts", datetime.utcnow().isoformat())
    inc_id = incident.get("id", 0)

    root_cause = rca.get("root_cause", "Investigating...")
    confidence = rca.get("confidence", "unknown")
    blast_radius = rca.get("blast_radius", "Unknown")
    immediate_actions = rca.get("recommended_actions", {})
    if isinstance(immediate_actions, dict):
        immediate_actions = immediate_actions.get("immediate", [])
    elif not isinstance(immediate_actions, list):
        immediate_actions = [str(immediate_actions)]
    stack_advice = rca.get("stack_specific_advice", "N/A")

    return {
        "incident_id": inc_id,
        "title": title,
        "severity": severity,
        "node_id": node_id,
        "ts": ts,
        "team_names": team_names,
        "root_cause": root_cause,
        "confidence": confidence,
        "blast_radius": blast_radius,
        "immediate_actions": immediate_actions,
        "stack_advice": stack_advice,
        "rca": rca,
    }


# ── Provider: Slack ──────────────────────────────────────────────────────────

async def send_slack(channel: str, payload: dict, token: str = "") -> dict:
    """Send rich Slack Block Kit message to a channel."""
    token = token or os.getenv("SLACK_BOT_TOKEN", "")
    if not token:
        return {"provider": "slack", "status": "skipped", "reason": "SLACK_BOT_TOKEN not set"}

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"[{payload['severity']}] {payload['title']}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*Node:* `{payload['node_id']}` | *Time:* {payload['ts']}\n"
            f"*Teams paged:* {payload['team_names']}"
        )}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*Root Cause:* {payload['root_cause']}\n"
            f"*Confidence:* {payload['confidence']}\n"
            f"*Blast Radius:* {payload['blast_radius']}\n\n"
            f"*Immediate Actions:*\n" +
            "\n".join(f"• {a}" for a in payload["immediate_actions"]) +
            f"\n\n*Stack Advice:*\n{payload['stack_advice']}"
        )}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"_PULSE Incident #{payload['incident_id']}_"}},
    ]

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"channel": channel, "blocks": blocks},
            )
            data = resp.json()
            return {"provider": "slack", "channel": channel, "status": "sent" if data.get("ok") else "failed", "detail": data}
    except Exception as e:
        return {"provider": "slack", "channel": channel, "status": "error", "reason": str(e)}


# ── Provider: Microsoft Teams ────────────────────────────────────────────────

async def send_teams(webhook_url: str, payload: dict) -> dict:
    """Send Adaptive Card to Microsoft Teams via webhook."""
    webhook_url = webhook_url or os.getenv("TEAMS_WEBHOOK_URL", "")
    if not webhook_url:
        return {"provider": "teams", "status": "skipped", "reason": "No webhook URL"}

    color = "FF0000" if payload["severity"] == "CRITICAL" else "FFA500" if payload["severity"] == "HIGH" else "0078D7"
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": f"[PULSE] {payload['title']}",
        "sections": [{
            "activityTitle": f"[{payload['severity']}] {payload['title']}",
            "activitySubtitle": f"Node: {payload['node_id']} | Teams: {payload['team_names']}",
            "facts": [
                {"name": "Root Cause", "value": payload["root_cause"]},
                {"name": "Confidence", "value": str(payload["confidence"])},
                {"name": "Blast Radius", "value": payload["blast_radius"]},
                {"name": "Immediate Action", "value": payload["immediate_actions"][0] if payload["immediate_actions"] else "Investigate"},
            ],
        }],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(webhook_url, json=card)
            return {"provider": "teams", "status": "sent" if resp.status_code in (200, 202) else "failed", "code": resp.status_code}
    except Exception as e:
        return {"provider": "teams", "status": "error", "reason": str(e)}


# ── Provider: Discord ────────────────────────────────────────────────────────

async def send_discord(webhook_url: str, payload: dict) -> dict:
    """Send rich embed to Discord via webhook."""
    if not webhook_url:
        return {"provider": "discord", "status": "skipped", "reason": "No webhook URL"}

    color_map = {"CRITICAL": 0xFF0000, "HIGH": 0xFF8C00, "MEDIUM": 0xFFD700, "LOW": 0x0078D7}
    embed = {
        "title": f"[{payload['severity']}] {payload['title']}",
        "color": color_map.get(payload["severity"], 0x808080),
        "fields": [
            {"name": "Node", "value": f"`{payload['node_id']}`", "inline": True},
            {"name": "Teams Paged", "value": payload["team_names"], "inline": True},
            {"name": "Root Cause", "value": payload["root_cause"][:1024], "inline": False},
            {"name": "Confidence", "value": str(payload["confidence"]), "inline": True},
            {"name": "Blast Radius", "value": payload["blast_radius"][:1024], "inline": True},
            {"name": "Immediate Actions", "value": "\n".join(f"• {a}" for a in payload["immediate_actions"][:5]) or "Investigate", "inline": False},
        ],
        "footer": {"text": f"PULSE Incident #{payload['incident_id']}"},
        "timestamp": payload["ts"],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(webhook_url, json={"embeds": [embed]})
            return {"provider": "discord", "status": "sent" if resp.status_code in (200, 204) else "failed", "code": resp.status_code}
    except Exception as e:
        return {"provider": "discord", "status": "error", "reason": str(e)}


# ── Provider: Telegram ───────────────────────────────────────────────────────

async def send_telegram(chat_id: str, payload: dict, bot_token: str = "") -> dict:
    """Send formatted message to Telegram chat/group."""
    bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        return {"provider": "telegram", "status": "skipped", "reason": "TELEGRAM_BOT_TOKEN not set"}

    severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}.get(payload["severity"], "⚪")
    text = (
        f"{severity_emoji} <b>[{payload['severity']}] {payload['title']}</b>\n\n"
        f"<b>Node:</b> <code>{payload['node_id']}</code>\n"
        f"<b>Teams:</b> {payload['team_names']}\n\n"
        f"<b>Root Cause:</b> {payload['root_cause']}\n"
        f"<b>Confidence:</b> {payload['confidence']}\n"
        f"<b>Blast Radius:</b> {payload['blast_radius']}\n\n"
        f"<b>Actions:</b>\n" +
        "\n".join(f"• {a}" for a in payload["immediate_actions"][:5]) +
        f"\n\n<i>PULSE Incident #{payload['incident_id']}</i>"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
            data = resp.json()
            return {"provider": "telegram", "chat_id": chat_id, "status": "sent" if data.get("ok") else "failed", "detail": data}
    except Exception as e:
        return {"provider": "telegram", "status": "error", "reason": str(e)}


# ── Provider: Google Chat ────────────────────────────────────────────────────

async def send_google_chat(webhook_url: str, payload: dict) -> dict:
    """Send card to Google Chat via webhook."""
    if not webhook_url:
        return {"provider": "google_chat", "status": "skipped", "reason": "No webhook URL"}

    card = {
        "cards": [{
            "header": {
                "title": f"[{payload['severity']}] {payload['title']}",
                "subtitle": f"Node: {payload['node_id']} | PULSE Incident #{payload['incident_id']}",
            },
            "sections": [{
                "widgets": [
                    {"keyValue": {"topLabel": "Root Cause", "content": payload["root_cause"][:500]}},
                    {"keyValue": {"topLabel": "Confidence", "content": str(payload["confidence"])}},
                    {"keyValue": {"topLabel": "Blast Radius", "content": payload["blast_radius"][:500]}},
                    {"keyValue": {"topLabel": "Teams Paged", "content": payload["team_names"]}},
                    {"textParagraph": {"text": "<b>Actions:</b><br>" + "<br>".join(f"• {a}" for a in payload["immediate_actions"][:5])}},
                ]
            }],
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(webhook_url, json=card)
            return {"provider": "google_chat", "status": "sent" if resp.status_code == 200 else "failed", "code": resp.status_code}
    except Exception as e:
        return {"provider": "google_chat", "status": "error", "reason": str(e)}


# ── Provider: Zoom ───────────────────────────────────────────────────────────

async def send_zoom(webhook_url: str, payload: dict) -> dict:
    """Send notification to Zoom Team Chat via incoming webhook (or chatbot)."""
    if not webhook_url:
        return {"provider": "zoom", "status": "skipped", "reason": "No webhook URL"}

    body = {
        "head": {"text": f"[{payload['severity']}] {payload['title']}"},
        "body": [
            {"type": "message", "text": (
                f"**Node:** `{payload['node_id']}`\n"
                f"**Teams Paged:** {payload['team_names']}\n\n"
                f"**Root Cause:** {payload['root_cause']}\n"
                f"**Confidence:** {payload['confidence']}\n"
                f"**Blast Radius:** {payload['blast_radius']}\n\n"
                f"**Actions:**\n" +
                "\n".join(f"• {a}" for a in payload["immediate_actions"][:5]) +
                f"\n\n_PULSE Incident #{payload['incident_id']}_"
            )},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(webhook_url, json=body)
            return {"provider": "zoom", "status": "sent" if resp.status_code in (200, 201) else "failed", "code": resp.status_code}
    except Exception as e:
        return {"provider": "zoom", "status": "error", "reason": str(e)}


# ── Provider: PagerDuty ──────────────────────────────────────────────────────

async def send_pagerduty(routing_key: str, payload: dict, api_key: str = "") -> dict:
    """Create PagerDuty incident via Events API v2."""
    api_key = api_key or os.getenv("PAGERDUTY_API_KEY", "")
    if not routing_key and not api_key:
        return {"provider": "pagerduty", "status": "skipped", "reason": "No routing key or API key"}

    severity_map = {"CRITICAL": "critical", "HIGH": "error", "MEDIUM": "warning", "LOW": "info"}
    event = {
        "routing_key": routing_key or api_key,
        "event_action": "trigger",
        "dedup_key": f"pulse-incident-{payload['incident_id']}",
        "payload": {
            "summary": f"[PULSE] [{payload['severity']}] {payload['title']} on {payload['node_id']}",
            "source": f"pulse-{payload['node_id']}",
            "severity": severity_map.get(payload["severity"], "error"),
            "component": payload["node_id"],
            "custom_details": {
                "root_cause": payload["root_cause"],
                "confidence": payload["confidence"],
                "blast_radius": payload["blast_radius"],
                "immediate_actions": payload["immediate_actions"],
                "teams_paged": payload["team_names"],
                "incident_id": payload["incident_id"],
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post("https://events.pagerduty.com/v2/enqueue", json=event)
            data = resp.json()
            return {"provider": "pagerduty", "status": data.get("status", "failed"), "dedup_key": data.get("dedup_key")}
    except Exception as e:
        return {"provider": "pagerduty", "status": "error", "reason": str(e)}


# ── Provider: Opsgenie ───────────────────────────────────────────────────────

async def send_opsgenie(payload: dict, api_key: str = "") -> dict:
    """Create Opsgenie alert via REST API."""
    api_key = api_key or os.getenv("OPSGENIE_API_KEY", "")
    if not api_key:
        return {"provider": "opsgenie", "status": "skipped", "reason": "OPSGENIE_API_KEY not set"}

    priority_map = {"CRITICAL": "P1", "HIGH": "P2", "MEDIUM": "P3", "LOW": "P4"}
    alert = {
        "message": f"[PULSE] [{payload['severity']}] {payload['title']}",
        "alias": f"pulse-incident-{payload['incident_id']}",
        "priority": priority_map.get(payload["severity"], "P3"),
        "source": "PULSE",
        "entity": payload["node_id"],
        "description": (
            f"Root Cause: {payload['root_cause']}\n"
            f"Confidence: {payload['confidence']}\n"
            f"Blast Radius: {payload['blast_radius']}\n"
            f"Teams: {payload['team_names']}\n\n"
            f"Actions:\n" + "\n".join(f"- {a}" for a in payload["immediate_actions"])
        ),
        "tags": ["pulse", payload["severity"].lower(), payload["node_id"]],
        "details": {
            "incident_id": str(payload["incident_id"]),
            "node_id": payload["node_id"],
            "confidence": str(payload["confidence"]),
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                "https://api.opsgenie.com/v2/alerts",
                headers={"Authorization": f"GenieKey {api_key}", "Content-Type": "application/json"},
                json=alert,
            )
            data = resp.json()
            return {"provider": "opsgenie", "status": "sent" if resp.status_code == 202 else "failed", "request_id": data.get("requestId")}
    except Exception as e:
        return {"provider": "opsgenie", "status": "error", "reason": str(e)}


# ── Provider: Email (SMTP) ───────────────────────────────────────────────────

async def send_email(to_address: str, payload: dict) -> dict:
    """Send HTML email via SMTP. Runs in executor to avoid blocking."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host:
        return {"provider": "email", "status": "skipped", "reason": "SMTP_HOST not set"}

    severity_color = {"CRITICAL": "#FF0000", "HIGH": "#FF8C00", "MEDIUM": "#FFD700", "LOW": "#0078D7"}.get(payload["severity"], "#808080")

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px;">
        <div style="background: {severity_color}; color: white; padding: 12px 20px; border-radius: 6px 6px 0 0;">
            <h2 style="margin:0;">[{payload['severity']}] {payload['title']}</h2>
        </div>
        <div style="border: 1px solid #ddd; border-top: none; padding: 20px; border-radius: 0 0 6px 6px;">
            <p><strong>Node:</strong> <code>{payload['node_id']}</code> &nbsp;|&nbsp; <strong>Time:</strong> {payload['ts']}</p>
            <p><strong>Teams Paged:</strong> {payload['team_names']}</p>
            <hr>
            <p><strong>Root Cause:</strong> {payload['root_cause']}</p>
            <p><strong>Confidence:</strong> {payload['confidence']} &nbsp;|&nbsp; <strong>Blast Radius:</strong> {payload['blast_radius']}</p>
            <p><strong>Immediate Actions:</strong></p>
            <ul>{"".join(f"<li>{a}</li>" for a in payload['immediate_actions'])}</ul>
            <p><strong>Stack Advice:</strong> {payload['stack_advice']}</p>
            <hr>
            <p style="color: #888; font-size: 12px;">PULSE Incident #{payload['incident_id']}</p>
        </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[PULSE {payload['severity']}] {payload['title']} — {payload['node_id']}"
    msg["From"] = smtp_from
    msg["To"] = to_address
    msg.attach(MIMEText(html, "html"))

    def _send():
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                if smtp_port == 587:
                    server.starttls()
                if smtp_user:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, [to_address], msg.as_string())
            return {"provider": "email", "to": to_address, "status": "sent"}
        except Exception as e:
            return {"provider": "email", "to": to_address, "status": "error", "reason": str(e)}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _send)


# ── Provider: SMS (Twilio) ───────────────────────────────────────────────────

async def send_sms(to_number: str, payload: dict) -> dict:
    """Send SMS via Twilio."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM_NUMBER", "")

    if not account_sid or not from_number:
        return {"provider": "sms", "status": "skipped", "reason": "Twilio not configured"}

    text = (
        f"[PULSE {payload['severity']}] {payload['title']}\n"
        f"Node: {payload['node_id']}\n"
        f"Cause: {payload['root_cause'][:200]}\n"
        f"Action: {payload['immediate_actions'][0] if payload['immediate_actions'] else 'Investigate'}\n"
        f"Inc #{payload['incident_id']}"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                auth=(account_sid, auth_token),
                data={"To": to_number, "From": from_number, "Body": text},
            )
            data = resp.json()
            return {"provider": "sms", "to": to_number, "status": "sent" if resp.status_code == 201 else "failed", "sid": data.get("sid")}
    except Exception as e:
        return {"provider": "sms", "status": "error", "reason": str(e)}


# ── Provider: WhatsApp (Twilio) ───────────────────────────────────────────────

async def send_whatsapp_twilio(to_number: str, payload: dict) -> dict:
    """Send WhatsApp message via Twilio's WhatsApp API.
    Uses same Twilio credentials as SMS. Number format: +15551234567
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", os.getenv("TWILIO_FROM_NUMBER", ""))

    if not account_sid or not from_number:
        return {"provider": "whatsapp", "status": "skipped", "reason": "Twilio not configured"}

    severity_emoji = {"CRITICAL": "\U0001f534", "HIGH": "\U0001f7e0", "MEDIUM": "\U0001f7e1", "LOW": "\U0001f535"}.get(payload["severity"], "\u26aa")
    text = (
        f"{severity_emoji} *[{payload['severity']}] {payload['title']}*\n\n"
        f"*Node:* `{payload['node_id']}`\n"
        f"*Teams:* {payload['team_names']}\n\n"
        f"*Root Cause:* {payload['root_cause']}\n"
        f"*Confidence:* {payload['confidence']}\n"
        f"*Blast Radius:* {payload['blast_radius']}\n\n"
        f"*Actions:*\n" +
        "\n".join(f"\u2022 {a}" for a in payload["immediate_actions"][:5]) +
        f"\n\n_PULSE Incident #{payload['incident_id']}_"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                auth=(account_sid, auth_token),
                data={"To": f"whatsapp:{to_number}", "From": f"whatsapp:{from_number}", "Body": text},
            )
            data = resp.json()
            return {"provider": "whatsapp", "to": to_number, "status": "sent" if resp.status_code == 201 else "failed", "sid": data.get("sid")}
    except Exception as e:
        return {"provider": "whatsapp", "status": "error", "reason": str(e)}


# ── Provider: WhatsApp (Meta Cloud API) ──────────────────────────────────────

async def send_whatsapp_meta(to_number: str, payload: dict) -> dict:
    """Send WhatsApp message via Meta's Cloud API (WhatsApp Business Platform).
    Requires WHATSAPP_TOKEN and WHATSAPP_PHONE_ID from Meta Business dashboard.
    Number format: 15551234567 (no + prefix)
    """
    token = os.getenv("WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "")

    if not token or not phone_id:
        return {"provider": "whatsapp_meta", "status": "skipped", "reason": "WHATSAPP_TOKEN or WHATSAPP_PHONE_ID not set"}

    # Strip + prefix if present
    to_clean = to_number.lstrip("+")

    severity_emoji = {"CRITICAL": "\U0001f534", "HIGH": "\U0001f7e0", "MEDIUM": "\U0001f7e1", "LOW": "\U0001f535"}.get(payload["severity"], "\u26aa")
    text = (
        f"{severity_emoji} *[{payload['severity']}] {payload['title']}*\n\n"
        f"*Node:* {payload['node_id']}\n"
        f"*Teams:* {payload['team_names']}\n\n"
        f"*Root Cause:* {payload['root_cause']}\n"
        f"*Confidence:* {payload['confidence']}\n"
        f"*Blast Radius:* {payload['blast_radius']}\n\n"
        f"*Actions:*\n" +
        "\n".join(f"- {a}" for a in payload["immediate_actions"][:5]) +
        f"\n\n_PULSE Incident #{payload['incident_id']}_"
    )

    body = {
        "messaging_product": "whatsapp",
        "to": to_clean,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                f"https://graph.facebook.com/v21.0/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )
            data = resp.json()
            msg_id = None
            if "messages" in data:
                msg_id = data["messages"][0].get("id")
            return {"provider": "whatsapp_meta", "to": to_number, "status": "sent" if resp.status_code in (200, 201) else "failed", "message_id": msg_id}
    except Exception as e:
        return {"provider": "whatsapp_meta", "status": "error", "reason": str(e)}


# ── Provider: Generic Webhook ────────────────────────────────────────────────

async def send_webhook(url: str, payload: dict, headers: Optional[dict] = None) -> dict:
    """POST full payload JSON to any webhook URL."""
    if not url:
        return {"provider": "webhook", "status": "skipped", "reason": "No URL"}

    webhook_payload = {
        "source": "pulse",
        "event": "incident.created",
        "incident_id": payload["incident_id"],
        "severity": payload["severity"],
        "title": payload["title"],
        "node_id": payload["node_id"],
        "ts": payload["ts"],
        "root_cause": payload["root_cause"],
        "confidence": payload["confidence"],
        "blast_radius": payload["blast_radius"],
        "immediate_actions": payload["immediate_actions"],
        "teams_paged": payload["team_names"],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(url, json=webhook_payload, headers=headers or {})
            return {"provider": "webhook", "url": url, "status": "sent" if resp.status_code < 400 else "failed", "code": resp.status_code}
    except Exception as e:
        return {"provider": "webhook", "url": url, "status": "error", "reason": str(e)}


# ── Provider Dispatcher ──────────────────────────────────────────────────────

PROVIDER_MAP = {
    "slack":       lambda contact, payload: send_slack(contact, payload),
    "teams":       lambda contact, payload: send_teams(contact, payload),
    "discord":     lambda contact, payload: send_discord(contact, payload),
    "telegram":    lambda contact, payload: send_telegram(contact, payload),
    "google_chat": lambda contact, payload: send_google_chat(contact, payload),
    "zoom":        lambda contact, payload: send_zoom(contact, payload),
    "pagerduty":   lambda contact, payload: send_pagerduty(contact, payload),
    "opsgenie":    lambda contact, payload: send_opsgenie(payload),
    "email":       lambda contact, payload: send_email(contact, payload),
    "sms":         lambda contact, payload: send_sms(contact, payload),
    "webhook":     lambda contact, payload: send_webhook(contact, payload),
    "whatsapp":    lambda contact, payload: send_whatsapp_twilio(contact, payload),
    "whatsapp_meta": lambda contact, payload: send_whatsapp_meta(contact, payload),
}


async def notify_team(team: dict, payload: dict) -> dict:
    """Send notifications to a single team via all their configured channels."""
    contact = team.get("contact", {})
    results = {}

    tasks = []
    for provider_name, target in contact.items():
        if not target or provider_name not in PROVIDER_MAP:
            continue
        tasks.append((provider_name, PROVIDER_MAP[provider_name](target, payload)))

    for provider_name, coro in tasks:
        results[provider_name] = await coro

    return results


async def notify_all_teams(teams_routing: dict, payload: dict) -> dict:
    """Notify all owner and observer teams in parallel."""
    all_teams = teams_routing.get("owners", []) + teams_routing.get("observers", [])
    results = {}

    # Run all team notifications concurrently
    team_tasks = {team["id"]: notify_team(team, payload) for team in all_teams}
    team_results = await asyncio.gather(*team_tasks.values(), return_exceptions=True)

    for team_id, result in zip(team_tasks.keys(), team_results):
        if isinstance(result, Exception):
            results[team_id] = {"error": str(result)}
        else:
            results[team_id] = result

    sent_any = any(
        r.get("status") == "sent"
        for team_result in results.values()
        if isinstance(team_result, dict)
        for r in team_result.values()
        if isinstance(r, dict)
    )

    return {
        "notified": sent_any,
        "teams": results,
        "ts": datetime.utcnow().isoformat(),
    }
