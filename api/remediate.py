"""
PULSE Auto-Remediation Engine

Loads playbooks from config/playbooks.yaml.
When an alert fires, checks for a matching playbook and executes it.

Supported actions:
  - run_command       — run a shell command on the affected node via SSH
  - http_request      — call a webhook / API endpoint
  - restart_service   — restart a systemd service on the remote node
  - notify_slack      — send a Slack message
  - notify_teams      — send a Teams message
  - scale_up          — placeholder for k8s/cloud scale-up hooks
  - run_local         — run a command on the PULSE server itself
"""
import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import yaml


_playbooks: list[dict] = []
_playbooks_loaded = False


def load_playbooks() -> list[dict]:
    global _playbooks, _playbooks_loaded
    if _playbooks_loaded:
        return _playbooks

    paths = [
        Path(__file__).parent.parent / "config" / "playbooks.yaml",
        Path(__file__).parent / "config" / "playbooks.yaml",
    ]
    for p in paths:
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f) or {}
                _playbooks = data.get("playbooks", [])
                _playbooks_loaded = True
                print(f"[Remediate] Loaded {len(_playbooks)} playbooks from {p}")
                return _playbooks

    print("[Remediate] No playbooks.yaml found — auto-remediation disabled")
    _playbooks_loaded = True
    return []


def find_playbooks(alert: dict) -> list[dict]:
    """Return all playbooks that match this alert."""
    playbooks = load_playbooks()
    matches   = []
    for pb in playbooks:
        # Match by rule_id, category, or severity
        if pb.get("trigger_rule") and pb["trigger_rule"] != alert.get("rule_id"):
            continue
        if pb.get("trigger_category") and pb["trigger_category"] not in (alert.get("category",""),):
            continue
        if pb.get("trigger_severity"):
            sevs = pb["trigger_severity"] if isinstance(pb["trigger_severity"], list) else [pb["trigger_severity"]]
            if alert.get("severity","") not in sevs:
                continue
        if pb.get("trigger_pattern") and not re.search(pb["trigger_pattern"], alert.get("message",""), re.I):
            continue
        matches.append(pb)
    return matches


def _render(template: str, context: dict) -> str:
    """Simple {var} template substitution."""
    for k, v in context.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template


async def _run_ssh_command(host: str, command: str, ssh_user: str = "") -> dict:
    if not ssh_user:
        ssh_user = os.getenv("REMEDIATION_SSH_USER", "root")
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
        f"{ssh_user}@{host}", command
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return {
            "status":  "ok" if proc.returncode == 0 else "failed",
            "rc":      proc.returncode,
            "stdout":  stdout.decode(errors="replace")[:2000],
            "stderr":  stderr.decode(errors="replace")[:500],
        }
    except asyncio.TimeoutError:
        return {"status": "timeout", "rc": -1, "stdout": "", "stderr": "Command timed out"}
    except Exception as e:
        return {"status": "error",   "rc": -1, "stdout": "", "stderr": str(e)}


async def _run_local_command(command: str) -> dict:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return {
            "status": "ok" if proc.returncode == 0 else "failed",
            "rc":     proc.returncode,
            "stdout": stdout.decode(errors="replace")[:2000],
            "stderr": stderr.decode(errors="replace")[:500],
        }
    except Exception as e:
        return {"status": "error", "rc": -1, "stdout": "", "stderr": str(e)}


async def _http_request(method: str, url: str, body: dict = None, headers: dict = None) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.request(
                method.upper(), url,
                json=body, headers=headers or {},
                timeout=15
            )
        return {"status": "ok", "http_status": r.status_code, "body": r.text[:500]}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def execute_playbook(playbook: dict, alert: dict, node_ip: str = "") -> dict:
    """
    Execute a single playbook against an alert.
    Returns execution log with step-by-step results.
    """
    context = {
        "node_id":    alert.get("node_id", ""),
        "node_ip":    node_ip,
        "rule_id":    alert.get("rule_id", ""),
        "rule_name":  alert.get("rule_name", ""),
        "severity":   alert.get("severity", ""),
        "message":    alert.get("message", ""),
        "ts":         datetime.utcnow().isoformat(),
        **alert.get("extra_context", {}),
    }

    results = []
    overall = "success"

    for step in playbook.get("steps", []):
        action  = step.get("action", "")
        result  = {"action": action, "step": step.get("name", action)}
        started = datetime.utcnow().isoformat()

        try:
            if action == "run_command" or action == "restart_service":
                cmd = _render(step.get("command", ""), context)
                if action == "restart_service":
                    svc = _render(step.get("service", ""), context)
                    cmd = f"systemctl restart {svc}"
                res = await _run_ssh_command(node_ip, cmd, step.get("ssh_user",""))
                result.update(res)

            elif action == "run_local":
                cmd = _render(step.get("command", ""), context)
                result.update(await _run_local_command(cmd))

            elif action == "http_request":
                url    = _render(step.get("url", ""), context)
                body   = {k: _render(str(v), context) for k, v in (step.get("body") or {}).items()}
                result.update(await _http_request(step.get("method","POST"), url, body, step.get("headers")))

            elif action in ("notify_slack", "notify_teams"):
                token   = os.getenv("SLACK_BOT_TOKEN", "")
                channel = _render(step.get("channel", "#incidents"), context)
                text    = _render(step.get("message", ""), context)
                if action == "notify_slack" and token:
                    res = await _http_request("POST", "https://slack.com/api/chat.postMessage", {
                        "channel": channel, "text": f"🔧 *Auto-Remediation* — {text}"
                    }, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                    result.update(res)
                elif action == "notify_teams":
                    webhook = _render(step.get("webhook", os.getenv("TEAMS_WEBHOOK_URL","")), context)
                    if webhook:
                        res = await _http_request("POST", webhook, {"text": f"🔧 Auto-Remediation: {text}"})
                        result.update(res)
                    else:
                        result["status"] = "skipped"
                else:
                    result["status"] = "skipped"

            elif action == "scale_up":
                # Placeholder — hook into k8s/AWS/Azure/GCP
                result["status"]  = "skipped"
                result["message"] = "scale_up requires cloud integration config"

            else:
                result["status"] = "unknown_action"

        except Exception as e:
            result["status"] = "error"
            result["error"]  = str(e)
            overall = "failed"

        result["started"] = started
        result["ended"]   = datetime.utcnow().isoformat()
        results.append(result)

        # Stop on failure unless continue_on_failure is set
        if result.get("status") not in ("ok", "skipped") and not step.get("continue_on_failure"):
            overall = "failed"
            if not playbook.get("continue_on_failure"):
                break

    return {
        "playbook_id": playbook.get("id", "?"),
        "playbook_name": playbook.get("name", ""),
        "status":  overall,
        "steps":   results,
        "context": {k: v for k, v in context.items() if k != "message"},
        "ts":      datetime.utcnow().isoformat(),
    }


async def run_playbooks_for_alert(alert: dict, node_ip: str = "") -> list[dict]:
    """Find and run all matching playbooks for an alert."""
    playbooks = find_playbooks(alert)
    if not playbooks:
        return []

    print(f"[Remediate] Running {len(playbooks)} playbook(s) for alert: {alert.get('rule_id')}")
    results = await asyncio.gather(
        *[execute_playbook(pb, alert, node_ip) for pb in playbooks],
        return_exceptions=True
    )
    return [r for r in results if isinstance(r, dict)]
