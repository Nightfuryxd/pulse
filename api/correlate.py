"""
PULSE Correlation Engine

Groups related alerts from multiple nodes into a single incident.
Detects cascading failures, service-wide outages, and infrastructure storms.

Logic:
  1. After each alert, look at all open alerts in the last WINDOW seconds
  2. Score pairs by: time proximity, same category, same infrastructure tier, node proximity
  3. If group score > threshold → merge into one correlated incident
  4. The RCA engine then gets context from ALL correlated nodes, not just one

Optimized: batch-fetches open alerts once per correlation call and groups
them in memory to avoid N+1 query patterns.
"""
import hashlib
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

# ── Correlation config ────────────────────────────────────────────────────────
WINDOW_SECONDS  = 300   # 5-minute correlation window
SCORE_THRESHOLD = 0.45  # minimum score to correlate two alerts
MAX_GROUP_SIZE  = 20    # max alerts in one correlation group

# Known service port → name mapping (used for topology correlation)
PORT_SERVICE = {
    22: "ssh", 80: "http", 443: "https", 3306: "mysql",
    5432: "postgres", 6379: "redis", 27017: "mongodb",
    9200: "elasticsearch", 9092: "kafka", 2181: "zookeeper",
    8080: "app", 8000: "app", 3000: "app", 5000: "app",
    11211: "memcached", 5672: "rabbitmq", 15672: "rabbitmq-mgmt",
}

# Category → infrastructure tier
CATEGORY_TIER = {
    "performance":   "compute",
    "memory":        "compute",
    "cpu":           "compute",
    "disk":          "storage",
    "network":       "network",
    "security":      "security",
    "database":      "data",
    "application":   "app",
    "process":       "compute",
}

# Alert pairs that strongly suggest a causal relationship
CAUSAL_PAIRS = [
    ("cpu",         "application"),   # high CPU → app slowdown
    ("memory",      "process"),       # OOM → process crash
    ("disk",        "application"),   # disk full → app error
    ("network",     "application"),   # network issue → app error
    ("database",    "application"),   # DB down → app error
    ("security",    "network"),       # attack → network anomaly
]

# In-memory recent alerts cache (alert_id → alert_dict)
_recent: dict[int, dict] = {}
_groups: dict[str, list[int]] = {}   # group_id → [alert_ids]


def _severity_weight(sev: str) -> float:
    return {"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}.get(sev, 0.3)


def _time_score(ts1: datetime, ts2: datetime) -> float:
    """Higher score for alerts closer in time."""
    delta = abs((ts1 - ts2).total_seconds())
    if delta <= 30:   return 1.0
    if delta <= 60:   return 0.85
    if delta <= 120:  return 0.65
    if delta <= 300:  return 0.4
    return 0.0


def _category_score(cat1: str, cat2: str) -> float:
    """Score based on category overlap or known causal relationship."""
    if cat1 == cat2:
        return 1.0
    for a, b in CAUSAL_PAIRS:
        if (cat1 == a and cat2 == b) or (cat1 == b and cat2 == a):
            return 0.75
    tier1 = CATEGORY_TIER.get(cat1, "unknown")
    tier2 = CATEGORY_TIER.get(cat2, "unknown")
    if tier1 == tier2:
        return 0.5
    return 0.1


def _node_score(node1: str, node2: str, all_nodes: list[str]) -> float:
    """Same node = 1.0. Different nodes with shared prefix = partial score."""
    if node1 == node2:
        return 0.9   # same node, different rules → likely same problem
    # Heuristic: nodes with same prefix (e.g. web-01, web-02) are related
    prefix1 = node1.rstrip("0123456789-_")
    prefix2 = node2.rstrip("0123456789-_")
    if prefix1 == prefix2 and len(prefix1) > 2:
        return 0.7
    return 0.2


def score_pair(a1: dict, a2: dict) -> float:
    """Score correlation between two alerts. Returns 0.0–1.0."""
    t_score   = _time_score(a1["ts"], a2["ts"])
    if t_score == 0:
        return 0.0   # too far apart in time

    cat_score  = _category_score(a1.get("category",""), a2.get("category",""))
    node_score = _node_score(a1["node_id"], a2["node_id"], [])
    sev_score  = (_severity_weight(a1["severity"]) + _severity_weight(a2["severity"])) / 2

    return round(t_score * 0.35 + cat_score * 0.35 + node_score * 0.2 + sev_score * 0.1, 3)


def _prefilter_open_alerts(open_alerts: list[dict], now: datetime, exclude_id=None) -> list[dict]:
    """
    Batch pre-filter: parse timestamps once, drop alerts outside the
    correlation window, and exclude the new alert itself.  Returns a
    list of alert dicts with a parsed ``_ts`` field attached.
    """
    cutoff = now - timedelta(seconds=WINDOW_SECONDS)
    filtered = []
    for alert in open_alerts:
        if exclude_id is not None and alert.get("id") == exclude_id:
            continue
        ts = alert.get("ts") or datetime.utcnow()
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if ts < cutoff:
            continue
        alert = {**alert, "_ts": ts}
        filtered.append(alert)
    return filtered


def _group_by_category(alerts: list[dict]) -> dict[str, list[dict]]:
    """Group pre-filtered alerts by category for fast lookup."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in alerts:
        groups[a.get("category", "")].append(a)
    return groups


def correlate(new_alert: dict, open_alerts: list[dict]) -> dict:
    """
    Given a new alert and a list of recent open alerts,
    return correlation result:
    {
      group_id: str,          # stable group hash
      correlated_with: [...], # alert ids in the group
      score: float,           # max pairwise score
      pattern: str,           # human-readable pattern name
      affected_nodes: [...],
      is_new_group: bool,
    }
    """
    now = new_alert.get("ts") or datetime.utcnow()
    if isinstance(now, str):
        now = datetime.fromisoformat(now)

    # Batch pre-filter: one pass over open_alerts, drop out-of-window entries
    candidates = _prefilter_open_alerts(open_alerts, now, exclude_id=new_alert.get("id"))

    best_group    = None
    best_score    = 0.0
    best_matches  = []

    new_alert_with_ts = {**new_alert, "ts": now}

    for existing in candidates:
        score = score_pair(
            new_alert_with_ts,
            {**existing, "ts": existing["_ts"]}
        )
        if score >= SCORE_THRESHOLD:
            best_matches.append((score, existing))

    if not best_matches:
        # New standalone group
        group_id = _make_group_id(new_alert)
        return {
            "group_id":       group_id,
            "correlated_with": [],
            "score":          0.0,
            "pattern":        "isolated",
            "affected_nodes": [new_alert["node_id"]],
            "is_new_group":   True,
        }

    # Sort by score desc
    best_matches.sort(key=lambda x: x[0], reverse=True)
    top_score    = best_matches[0][0]
    top_match    = best_matches[0][1]
    correlated   = [m[1] for m in best_matches[:MAX_GROUP_SIZE]]
    all_alert_ids = [m.get("id") for m in correlated if m.get("id")]
    all_nodes    = list({new_alert["node_id"]} | {m["node_id"] for m in correlated})

    # Find or create group
    existing_group = top_match.get("group_id")
    group_id = existing_group or _make_group_id(top_match)

    pattern = _detect_pattern(new_alert, correlated)

    return {
        "group_id":        group_id,
        "correlated_with": all_alert_ids,
        "score":           top_score,
        "pattern":         pattern,
        "affected_nodes":  all_nodes,
        "is_new_group":    existing_group is None,
    }


def _make_group_id(alert: dict) -> str:
    """Stable group ID from alert properties."""
    key = f"{alert.get('category','?')}:{alert.get('node_id','?')}:{int(time.time()//300)}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _detect_pattern(new_alert: dict, correlated: list[dict]) -> str:
    """Name the failure pattern."""
    all_alerts  = [new_alert] + correlated
    nodes       = {a["node_id"] for a in all_alerts}
    categories  = {a.get("category","") for a in all_alerts}
    severities  = {a.get("severity","") for a in all_alerts}

    if len(nodes) > 3 and len(categories) == 1:
        return f"service_wide_{list(categories)[0]}_outage"
    if len(nodes) > 1 and "security" in categories:
        return "multi_node_security_incident"
    if "database" in categories and "application" in categories:
        return "database_induced_app_failure"
    if "network" in categories and len(nodes) > 2:
        return "network_partition"
    if "memory" in categories and "process" in categories:
        return "oom_cascade"
    if "cpu" in categories and "application" in categories:
        return "resource_exhaustion"
    if len(nodes) > 1:
        return "multi_node_incident"
    return "single_node_incident"


def build_correlation_summary(group_id: str, alerts: list[dict], nodes: list[dict]) -> dict:
    """
    Build the correlation context summary for the RCA engine.
    Provides richer cross-node context than a single-alert RCA.
    """
    categories   = list({a.get("category","unknown") for a in alerts})
    severities   = [a.get("severity","info") for a in alerts]
    node_ids     = list({a["node_id"] for a in alerts})
    timeline     = sorted(alerts, key=lambda a: a.get("ts") or "")

    worst_sev = "info"
    for sev in ["critical","high","medium","low","info"]:
        if sev in severities:
            worst_sev = sev
            break

    first_alert = timeline[0]  if timeline else {}
    last_alert  = timeline[-1] if timeline else {}

    return {
        "group_id":         group_id,
        "total_alerts":     len(alerts),
        "affected_nodes":   node_ids,
        "node_count":       len(node_ids),
        "categories":       categories,
        "worst_severity":   worst_sev,
        "first_seen":       first_alert.get("ts",""),
        "last_seen":        last_alert.get("ts",""),
        "trigger_alert":    first_alert.get("rule_name",""),
        "pattern":          _detect_pattern(first_alert, alerts[1:]) if alerts else "unknown",
        "timeline_summary": [
            f"{a.get('ts','')} [{a['node_id']}] {a.get('rule_name','')} ({a.get('severity','')})"
            for a in timeline[:10]
        ],
    }
