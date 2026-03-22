"""
Detection Engine — evaluates metrics and events against YAML rules.
Produces Alert objects when thresholds are breached.
"""
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any


_rules_cache: list[dict] | None = None

def _rules_path() -> Path:
    path = Path("config/rules.yaml")
    if not path.exists():
        path = Path("/app/config/rules.yaml")
    return path

def load_rules() -> list[dict]:
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache
    with open(_rules_path()) as f:
        _rules_cache = yaml.safe_load(f).get("rules", [])
    return _rules_cache

def _save_rules():
    try:
        with open(_rules_path(), 'w') as f:
            yaml.dump({"rules": _rules_cache}, f, default_flow_style=False, sort_keys=False)
    except (OSError, PermissionError):
        pass  # ConfigMap is read-only in K8s — changes persist in memory until restart

def get_all_rules() -> list[dict]:
    return load_rules()

def get_rule(rule_id: str) -> dict | None:
    return next((r for r in load_rules() if r["id"] == rule_id), None)

def create_rule(rule: dict) -> dict:
    global _rules_cache
    rules = load_rules()
    if any(r["id"] == rule["id"] for r in rules):
        raise ValueError(f"Rule '{rule['id']}' already exists")
    required = ["id", "name", "condition", "severity"]
    for f in required:
        if f not in rule:
            raise ValueError(f"Missing required field: {f}")
    rule.setdefault("category", "general")
    rule.setdefault("window_seconds", 0)
    rule.setdefault("message", rule["name"])
    rule.setdefault("enabled", True)
    rules.append(rule)
    _rules_cache = rules
    _save_rules()
    return rule

def update_rule(rule_id: str, updates: dict) -> dict | None:
    global _rules_cache
    rules = load_rules()
    rule = next((r for r in rules if r["id"] == rule_id), None)
    if not rule:
        return None
    for k, v in updates.items():
        if k != "id":
            rule[k] = v
    _rules_cache = rules
    _save_rules()
    return rule

def delete_rule(rule_id: str) -> bool:
    global _rules_cache
    rules = load_rules()
    new_rules = [r for r in rules if r["id"] != rule_id]
    if len(new_rules) == len(rules):
        return False
    _rules_cache = new_rules
    _save_rules()
    return True


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
        if not rule.get("enabled", True):
            continue
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
        if not rule.get("enabled", True):
            continue
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
