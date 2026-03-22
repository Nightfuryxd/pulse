"""
Log-Based Alerting — alert on log patterns (regex, keyword, rate-based).
Like Datadog Log Monitors: define patterns, set thresholds, get notified.
"""
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

# ── In-memory stores ─────────────────────────────────────────────────────────
_log_rules: dict[str, dict] = {}
_log_rule_hits: dict[str, list[dict]] = {}  # rule_id -> recent matches
_log_alerts: list[dict] = []

# Rule types
RULE_TYPES = [
    {"id": "keyword", "name": "Keyword Match", "description": "Alert when a log contains specific keywords"},
    {"id": "regex", "name": "Regex Pattern", "description": "Alert when a log matches a regular expression"},
    {"id": "rate", "name": "Rate Alert", "description": "Alert when log volume exceeds N per time window"},
    {"id": "absence", "name": "Log Absence", "description": "Alert when expected logs stop appearing"},
]

SEVERITY_LEVELS = ["info", "low", "medium", "high", "critical"]

# ── Seed demo rules ─────────────────────────────────────────────────────────
_seeds = [
    {
        "id": "lr-error-spike",
        "name": "Error Log Spike",
        "description": "Alert when error-level logs exceed 50 per 5 minutes",
        "enabled": True,
        "type": "rate",
        "pattern": "ERROR|error|FATAL|fatal|Exception|Traceback",
        "threshold": 50,
        "window_minutes": 5,
        "severity": "high",
        "notify_channels": ["slack"],
        "source_filter": "*",
        "tags": ["errors", "production"],
        "created_at": datetime.utcnow().isoformat(),
        "last_triggered": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
        "trigger_count": 7,
        "status": "active",
    },
    {
        "id": "lr-oom-killer",
        "name": "OOM Killer Detected",
        "description": "Alert immediately when kernel OOM killer is invoked",
        "enabled": True,
        "type": "keyword",
        "pattern": "Out of memory|oom_kill|OOM killer|invoked oom-killer",
        "threshold": 1,
        "window_minutes": 1,
        "severity": "critical",
        "notify_channels": ["slack", "pagerduty"],
        "source_filter": "*",
        "tags": ["memory", "kernel", "critical"],
        "created_at": datetime.utcnow().isoformat(),
        "last_triggered": None,
        "trigger_count": 0,
        "status": "active",
    },
    {
        "id": "lr-auth-failures",
        "name": "Authentication Failures Surge",
        "description": "Alert when auth failures exceed 20 in 10 minutes (possible brute force)",
        "enabled": True,
        "type": "rate",
        "pattern": "authentication failed|login failed|invalid password|401 Unauthorized",
        "threshold": 20,
        "window_minutes": 10,
        "severity": "high",
        "notify_channels": ["slack", "email"],
        "source_filter": "*",
        "tags": ["security", "auth"],
        "created_at": datetime.utcnow().isoformat(),
        "last_triggered": (datetime.utcnow() - timedelta(hours=6)).isoformat(),
        "trigger_count": 3,
        "status": "active",
    },
    {
        "id": "lr-disk-io",
        "name": "Disk I/O Errors",
        "description": "Alert on disk I/O errors in syslog",
        "enabled": True,
        "type": "regex",
        "pattern": r"(I/O error|EXT4-fs error|XFS.*error|blk_update_request.*I/O)",
        "threshold": 1,
        "window_minutes": 5,
        "severity": "critical",
        "notify_channels": ["slack", "pagerduty"],
        "source_filter": "*",
        "tags": ["disk", "hardware"],
        "created_at": datetime.utcnow().isoformat(),
        "last_triggered": None,
        "trigger_count": 0,
        "status": "active",
    },
    {
        "id": "lr-slow-query",
        "name": "Slow Database Queries",
        "description": "Alert when slow query logs exceed 10 per minute",
        "enabled": True,
        "type": "rate",
        "pattern": "slow query|duration: [0-9]{4,}ms|query took [0-9]{4,}",
        "threshold": 10,
        "window_minutes": 1,
        "severity": "medium",
        "notify_channels": ["slack"],
        "source_filter": "postgres*",
        "tags": ["database", "performance"],
        "created_at": datetime.utcnow().isoformat(),
        "last_triggered": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        "trigger_count": 12,
        "status": "active",
    },
    {
        "id": "lr-heartbeat",
        "name": "Agent Heartbeat Missing",
        "description": "Alert if no agent heartbeat log appears for 5 minutes",
        "enabled": False,
        "type": "absence",
        "pattern": "heartbeat|agent_checkin|pulse-agent.*alive",
        "threshold": 1,
        "window_minutes": 5,
        "severity": "high",
        "notify_channels": ["slack"],
        "source_filter": "pulse-agent*",
        "tags": ["agent", "heartbeat"],
        "created_at": datetime.utcnow().isoformat(),
        "last_triggered": None,
        "trigger_count": 0,
        "status": "disabled",
    },
]

for s in _seeds:
    _log_rules[s["id"]] = s


# ── CRUD ─────────────────────────────────────────────────────────────────────

def list_rules(rule_type: str | None = None, severity: str | None = None) -> list[dict]:
    result = list(_log_rules.values())
    if rule_type:
        result = [r for r in result if r.get("type") == rule_type]
    if severity:
        result = [r for r in result if r.get("severity") == severity]
    return sorted(result, key=lambda r: r.get("created_at", ""), reverse=True)


def get_rule(rule_id: str) -> dict | None:
    return _log_rules.get(rule_id)


def create_rule(data: dict) -> dict:
    rid = f"lr-{uuid.uuid4().hex[:8]}"
    rule = {
        "id": rid,
        "name": data.get("name", "New Log Rule"),
        "description": data.get("description", ""),
        "enabled": data.get("enabled", True),
        "type": data.get("type", "keyword"),
        "pattern": data.get("pattern", ""),
        "threshold": data.get("threshold", 1),
        "window_minutes": data.get("window_minutes", 5),
        "severity": data.get("severity", "medium"),
        "notify_channels": data.get("notify_channels", ["slack"]),
        "source_filter": data.get("source_filter", "*"),
        "tags": data.get("tags", []),
        "created_at": datetime.utcnow().isoformat(),
        "last_triggered": None,
        "trigger_count": 0,
        "status": "active" if data.get("enabled", True) else "disabled",
    }
    _log_rules[rid] = rule
    return rule


def update_rule(rule_id: str, data: dict) -> dict | None:
    rule = _log_rules.get(rule_id)
    if not rule:
        return None
    updatable = ["name", "description", "enabled", "type", "pattern", "threshold",
                 "window_minutes", "severity", "notify_channels", "source_filter", "tags"]
    for k in updatable:
        if k in data:
            rule[k] = data[k]
    rule["status"] = "active" if rule["enabled"] else "disabled"
    return rule


def delete_rule(rule_id: str) -> bool:
    if rule_id in _log_rules:
        del _log_rules[rule_id]
        _log_rule_hits.pop(rule_id, None)
        return True
    return False


def toggle_rule(rule_id: str) -> dict | None:
    rule = _log_rules.get(rule_id)
    if not rule:
        return None
    rule["enabled"] = not rule["enabled"]
    rule["status"] = "active" if rule["enabled"] else "disabled"
    return rule


def test_rule(rule_id: str, sample_log: str) -> dict:
    """Test a rule against a sample log line."""
    rule = _log_rules.get(rule_id)
    if not rule:
        return {"match": False, "error": "Rule not found"}
    try:
        pattern = rule.get("pattern", "")
        if rule["type"] == "regex":
            match = bool(re.search(pattern, sample_log))
        else:
            match = bool(re.search(pattern, sample_log, re.IGNORECASE))
        return {"match": match, "rule_id": rule_id, "pattern": pattern, "sample": sample_log}
    except re.error as e:
        return {"match": False, "error": f"Invalid regex: {e}"}


def evaluate_log(log_line: str, source: str = "") -> list[dict]:
    """Evaluate a log line against all enabled rules. Returns triggered alerts."""
    triggered = []
    now = datetime.utcnow()

    for rule in _log_rules.values():
        if not rule.get("enabled"):
            continue

        # Source filter
        sf = rule.get("source_filter", "*")
        if sf != "*" and not re.match(sf.replace("*", ".*"), source, re.IGNORECASE):
            continue

        pattern = rule.get("pattern", "")
        try:
            if rule["type"] == "regex":
                matched = bool(re.search(pattern, log_line))
            else:
                matched = bool(re.search(pattern, log_line, re.IGNORECASE))
        except re.error:
            continue

        if not matched:
            continue

        # Record hit
        rid = rule["id"]
        if rid not in _log_rule_hits:
            _log_rule_hits[rid] = []
        _log_rule_hits[rid].append({"ts": now.isoformat(), "log": log_line[:200], "source": source})

        # Trim old hits
        window = timedelta(minutes=rule.get("window_minutes", 5))
        cutoff = now - window
        _log_rule_hits[rid] = [h for h in _log_rule_hits[rid] if h["ts"] >= cutoff.isoformat()]

        # Check threshold
        hit_count = len(_log_rule_hits[rid])
        threshold = rule.get("threshold", 1)

        if rule["type"] in ("keyword", "regex") and hit_count >= threshold:
            rule["last_triggered"] = now.isoformat()
            rule["trigger_count"] = rule.get("trigger_count", 0) + 1
            triggered.append({
                "rule_id": rid,
                "rule_name": rule["name"],
                "severity": rule["severity"],
                "hit_count": hit_count,
                "threshold": threshold,
                "sample_log": log_line[:200],
                "triggered_at": now.isoformat(),
            })
            _log_rule_hits[rid] = []  # Reset after trigger

        elif rule["type"] == "rate" and hit_count >= threshold:
            rule["last_triggered"] = now.isoformat()
            rule["trigger_count"] = rule.get("trigger_count", 0) + 1
            triggered.append({
                "rule_id": rid,
                "rule_name": rule["name"],
                "severity": rule["severity"],
                "hit_count": hit_count,
                "threshold": threshold,
                "window_minutes": rule["window_minutes"],
                "triggered_at": now.isoformat(),
            })
            _log_rule_hits[rid] = []

    if triggered:
        _log_alerts.extend(triggered)
        if len(_log_alerts) > 500:
            _log_alerts[:] = _log_alerts[-500:]

    return triggered


def get_log_alerts(limit: int = 50) -> list[dict]:
    return list(reversed(_log_alerts[-limit:]))


def get_rule_hits(rule_id: str) -> list[dict]:
    return _log_rule_hits.get(rule_id, [])


def get_rule_types() -> list[dict]:
    return RULE_TYPES


def get_summary() -> dict:
    rules = list(_log_rules.values())
    return {
        "total_rules": len(rules),
        "enabled": sum(1 for r in rules if r.get("enabled")),
        "disabled": sum(1 for r in rules if not r.get("enabled")),
        "by_type": {t["id"]: sum(1 for r in rules if r.get("type") == t["id"]) for t in RULE_TYPES},
        "by_severity": {s: sum(1 for r in rules if r.get("severity") == s) for s in SEVERITY_LEVELS},
        "total_alerts_fired": len(_log_alerts),
        "top_triggered": sorted(
            [{"id": r["id"], "name": r["name"], "count": r.get("trigger_count", 0)}
             for r in rules if r.get("trigger_count", 0) > 0],
            key=lambda x: x["count"], reverse=True
        )[:5],
    }
