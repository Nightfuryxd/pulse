"""
Detection Engine — evaluates metrics and events against YAML rules.
Produces Alert objects when thresholds are breached.
"""
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any


def load_rules() -> list[dict]:
    path = Path("config/rules.yaml")
    if not path.exists():
        path = Path("/app/config/rules.yaml")
    with open(path) as f:
        return yaml.safe_load(f).get("rules", [])


# Simple in-memory window tracker: rule_id -> list of (ts, value)
_windows: dict[str, list[tuple[datetime, float]]] = {}


def _check_condition(condition: str, context: dict) -> tuple[bool, float]:
    """
    Evaluate a rule condition string against a context dict.
    Returns (triggered, value).
    """
    # Flatten context for eval: metric.cpu_percent -> cpu_percent
    flat = {}
    for ns, obj in context.items():
        if isinstance(obj, dict):
            flat.update(obj)
        else:
            flat[ns] = obj

    try:
        result = eval(condition, {"__builtins__": {}}, flat)
        # Extract the primary numeric value
        value = 0.0
        for key in ["cpu_percent", "memory_percent", "disk_percent", "count", "unique_ports", "value"]:
            if key in flat:
                value = float(flat[key])
                break
        return bool(result), value
    except Exception:
        return False, 0.0


def evaluate_metric(node_id: str, metric: dict) -> list[dict]:
    """
    Run all metric rules against a metric snapshot.
    Returns list of triggered alert dicts.
    """
    rules   = load_rules()
    alerts  = []
    now     = datetime.utcnow()
    context = {"metric": metric}

    for rule in rules:
        if "event." in rule["condition"]:
            continue  # event-only rule

        triggered, value = _check_condition(rule["condition"], context)
        if not triggered:
            _windows.pop(f"{node_id}:{rule['id']}", None)
            continue

        window_s = rule.get("window_seconds", 0)
        key      = f"{node_id}:{rule['id']}"

        if window_s == 0:
            # Instant trigger
            alerts.append(_make_alert(node_id, rule, value, now))
            continue

        # Windowed: must sustain for window_seconds
        _windows.setdefault(key, []).append((now, value))
        # Prune old entries
        _windows[key] = [(t, v) for t, v in _windows[key]
                         if (now - t).total_seconds() <= window_s]

        if len(_windows[key]) >= 2:
            # Condition held for the full window — trigger once
            alerts.append(_make_alert(node_id, rule, value, now))
            _windows[key] = []  # reset so it doesn't spam

    return alerts


def evaluate_event(node_id: str, event: dict) -> list[dict]:
    """
    Run event rules against an incoming event.
    Returns list of triggered alert dicts.
    """
    rules  = load_rules()
    alerts = []
    now    = datetime.utcnow()

    for rule in rules:
        if "metric." in rule["condition"]:
            continue  # metric-only rule

        context = {"event": event}
        triggered, value = _check_condition(rule["condition"], context)
        if triggered:
            alerts.append(_make_alert(node_id, rule, value, now))

    return alerts


def _make_alert(node_id: str, rule: dict, value: float, ts: datetime) -> dict:
    message = rule.get("message", rule["name"])
    try:
        message = message.format(value=value, **{})
    except Exception:
        pass
    return {
        "node_id":   node_id,
        "rule_id":   rule["id"],
        "rule_name": rule["name"],
        "severity":  rule["severity"],
        "category":  rule.get("category", "general"),
        "message":   message,
        "ts":        ts.isoformat(),
    }
