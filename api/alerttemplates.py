"""
Alerting Templates Library — pre-built alert rule packs.
One-click import for Kubernetes, PostgreSQL, Redis, Linux, Docker.
"""
import uuid
from datetime import datetime
from typing import Any

# ── Template Packs ───────────────────────────────────────────────────────────

_packs: dict[str, dict] = {}

_pack_defs = [
    {
        "id": "pack-linux",
        "name": "Linux Essentials",
        "description": "Core alerts for Linux servers — CPU, memory, disk, load, OOM",
        "icon": "terminal",
        "color": "#34d399",
        "category": "Infrastructure",
        "rule_count": 6,
        "imported_count": 0,
        "rules": [
            {"name": "CPU Critical", "metric": "cpu_percent", "operator": ">", "value": 95, "duration": 3, "severity": "critical",
             "description": "CPU sustained above 95% for 3 minutes"},
            {"name": "CPU Warning", "metric": "cpu_percent", "operator": ">", "value": 80, "duration": 5, "severity": "high",
             "description": "CPU sustained above 80% for 5 minutes"},
            {"name": "Memory Critical", "metric": "memory_percent", "operator": ">", "value": 95, "duration": 2, "severity": "critical",
             "description": "Memory above 95% — imminent OOM risk"},
            {"name": "Disk Space Critical", "metric": "disk_percent", "operator": ">", "value": 90, "duration": 1, "severity": "critical",
             "description": "Disk usage above 90%"},
            {"name": "High Load Average", "metric": "load_avg_1m", "operator": ">", "value": 8, "duration": 5, "severity": "high",
             "description": "1-min load average above 8 for 5 minutes"},
            {"name": "OOM Killer", "metric": "process_count", "operator": ">", "value": 500, "duration": 1, "severity": "critical",
             "description": "Process count explosion — possible fork bomb"},
        ],
    },
    {
        "id": "pack-kubernetes",
        "name": "Kubernetes Cluster",
        "description": "Alerts for K8s clusters — pod restarts, node pressure, resource limits",
        "icon": "container",
        "color": "#6366f1",
        "category": "Orchestration",
        "rule_count": 7,
        "imported_count": 0,
        "rules": [
            {"name": "Pod CrashLoopBackOff", "metric": "container_restart_count", "operator": ">", "value": 5, "duration": 10, "severity": "critical",
             "description": "Pod restarting repeatedly in crash loop"},
            {"name": "Node Not Ready", "metric": "node_ready", "operator": "==", "value": 0, "duration": 2, "severity": "critical",
             "description": "Kubernetes node in NotReady state"},
            {"name": "Container CPU Throttled", "metric": "container_cpu", "operator": ">", "value": 90, "duration": 5, "severity": "high",
             "description": "Container hitting CPU limit, being throttled"},
            {"name": "Container OOMKilled", "metric": "container_memory", "operator": ">", "value": 95, "duration": 1, "severity": "critical",
             "description": "Container near memory limit — OOMKill imminent"},
            {"name": "Deployment Replicas Unavailable", "metric": "deployment_unavailable", "operator": ">", "value": 0, "duration": 3, "severity": "high",
             "description": "Deployment has unavailable replicas"},
            {"name": "PVC Nearly Full", "metric": "pvc_usage_percent", "operator": ">", "value": 85, "duration": 5, "severity": "high",
             "description": "Persistent volume claim above 85% capacity"},
            {"name": "HPA at Max Replicas", "metric": "hpa_current_replicas", "operator": ">=", "value": 10, "duration": 10, "severity": "medium",
             "description": "HPA scaled to maximum — may need limit increase"},
        ],
    },
    {
        "id": "pack-postgres",
        "name": "PostgreSQL",
        "description": "Database alerts — connections, replication lag, slow queries, deadlocks",
        "icon": "database",
        "color": "#22d3ee",
        "category": "Database",
        "rule_count": 6,
        "imported_count": 0,
        "rules": [
            {"name": "Connection Pool Exhausted", "metric": "pg_connections", "operator": ">", "value": 90, "duration": 2, "severity": "critical",
             "description": "Connection pool above 90% capacity"},
            {"name": "Replication Lag", "metric": "pg_replication_lag_sec", "operator": ">", "value": 30, "duration": 3, "severity": "high",
             "description": "Replication lag exceeding 30 seconds"},
            {"name": "Slow Queries", "metric": "pg_slow_queries_per_min", "operator": ">", "value": 10, "duration": 5, "severity": "medium",
             "description": "More than 10 slow queries per minute"},
            {"name": "Deadlocks Detected", "metric": "pg_deadlocks", "operator": ">", "value": 0, "duration": 1, "severity": "high",
             "description": "Database deadlocks occurring"},
            {"name": "Cache Hit Ratio Low", "metric": "pg_cache_hit_ratio", "operator": "<", "value": 90, "duration": 10, "severity": "medium",
             "description": "Buffer cache hit ratio below 90% — needs more memory"},
            {"name": "Table Bloat", "metric": "pg_dead_tuples_percent", "operator": ">", "value": 20, "duration": 30, "severity": "low",
             "description": "Dead tuples exceeding 20% — needs VACUUM"},
        ],
    },
    {
        "id": "pack-redis",
        "name": "Redis",
        "description": "Cache alerts — memory, evictions, connections, latency",
        "icon": "zap",
        "color": "#f87171",
        "category": "Database",
        "rule_count": 5,
        "imported_count": 0,
        "rules": [
            {"name": "Memory Usage Critical", "metric": "redis_memory_percent", "operator": ">", "value": 90, "duration": 2, "severity": "critical",
             "description": "Redis memory above 90% — evictions imminent"},
            {"name": "High Eviction Rate", "metric": "redis_evictions_per_sec", "operator": ">", "value": 100, "duration": 5, "severity": "high",
             "description": "Redis evicting more than 100 keys/sec"},
            {"name": "Connected Clients Surge", "metric": "redis_connected_clients", "operator": ">", "value": 500, "duration": 3, "severity": "medium",
             "description": "Unusual number of connected Redis clients"},
            {"name": "Slow Commands", "metric": "redis_slowlog_count", "operator": ">", "value": 5, "duration": 5, "severity": "medium",
             "description": "Redis slowlog showing frequent slow commands"},
            {"name": "Replication Broken", "metric": "redis_replication_status", "operator": "==", "value": 0, "duration": 1, "severity": "critical",
             "description": "Redis replication link is down"},
        ],
    },
    {
        "id": "pack-docker",
        "name": "Docker Containers",
        "description": "Container alerts — resource limits, health checks, restart loops",
        "icon": "box",
        "color": "#fbbf24",
        "category": "Container",
        "rule_count": 5,
        "imported_count": 0,
        "rules": [
            {"name": "Container CPU Maxed", "metric": "container_cpu", "operator": ">", "value": 90, "duration": 3, "severity": "high",
             "description": "Container using >90% of allocated CPU"},
            {"name": "Container Memory Limit", "metric": "container_memory", "operator": ">", "value": 85, "duration": 2, "severity": "high",
             "description": "Container approaching memory limit"},
            {"name": "Container Restart Loop", "metric": "container_restart_count", "operator": ">", "value": 3, "duration": 5, "severity": "critical",
             "description": "Container restarting repeatedly"},
            {"name": "Health Check Failing", "metric": "container_health", "operator": "==", "value": 0, "duration": 2, "severity": "high",
             "description": "Container health check failing"},
            {"name": "Container Exited", "metric": "container_running", "operator": "==", "value": 0, "duration": 1, "severity": "critical",
             "description": "Expected container is not running"},
        ],
    },
    {
        "id": "pack-network",
        "name": "Network & HTTP",
        "description": "Network alerts — latency, error rates, bandwidth, connections",
        "icon": "wifi",
        "color": "#a78bfa",
        "category": "Network",
        "rule_count": 5,
        "imported_count": 0,
        "rules": [
            {"name": "HTTP Error Rate Spike", "metric": "http_error_rate", "operator": ">", "value": 5, "duration": 3, "severity": "critical",
             "description": "HTTP 5xx error rate above 5%"},
            {"name": "High P99 Latency", "metric": "http_latency_p99", "operator": ">", "value": 500, "duration": 5, "severity": "high",
             "description": "P99 latency exceeding 500ms"},
            {"name": "Request Rate Drop", "metric": "http_requests_per_sec", "operator": "<", "value": 10, "duration": 5, "severity": "high",
             "description": "Sudden drop in request rate — possible outage"},
            {"name": "Bandwidth Saturated", "metric": "network_bytes_sent", "operator": ">", "value": 100000000, "duration": 5, "severity": "high",
             "description": "Network egress exceeding 100MB/s"},
            {"name": "TCP Connection Surge", "metric": "tcp_connections", "operator": ">", "value": 1000, "duration": 3, "severity": "medium",
             "description": "Unusual surge in TCP connections"},
        ],
    },
]

for p in _pack_defs:
    p["created_at"] = datetime.utcnow().isoformat()
    _packs[p["id"]] = p

# Track imported rules
_imported_rules: list[dict] = []


def list_packs(category: str | None = None) -> list[dict]:
    result = list(_packs.values())
    if category:
        result = [p for p in result if p.get("category") == category]
    # Return without full rules for list view
    return [{k: v for k, v in p.items() if k != "rules"} for p in result]


def get_pack(pack_id: str) -> dict | None:
    return _packs.get(pack_id)


def import_pack(pack_id: str) -> dict:
    """Import all rules from a pack into active alert rules."""
    pack = _packs.get(pack_id)
    if not pack:
        return {"error": "Pack not found"}

    imported = []
    for rule in pack.get("rules", []):
        rid = f"rule-{uuid.uuid4().hex[:8]}"
        ir = {
            "id": rid,
            "name": f"[{pack['name']}] {rule['name']}",
            "description": rule.get("description", ""),
            "metric": rule.get("metric"),
            "operator": rule.get("operator"),
            "value": rule.get("value"),
            "duration_minutes": rule.get("duration", 5),
            "severity": rule.get("severity", "medium"),
            "enabled": True,
            "source_pack": pack_id,
            "imported_at": datetime.utcnow().isoformat(),
        }
        _imported_rules.append(ir)
        imported.append(ir)

    pack["imported_count"] = pack.get("imported_count", 0) + 1
    return {"imported": len(imported), "rules": imported, "pack": pack["name"]}


def get_imported_rules() -> list[dict]:
    return list(reversed(_imported_rules))


def get_categories() -> list[str]:
    return sorted(set(p.get("category", "Other") for p in _packs.values()))


def get_summary() -> dict:
    packs = list(_packs.values())
    total_rules = sum(p.get("rule_count", 0) for p in packs)
    return {
        "total_packs": len(packs),
        "total_rules": total_rules,
        "imported_rules": len(_imported_rules),
        "categories": get_categories(),
        "by_category": {c: sum(1 for p in packs if p.get("category") == c) for c in get_categories()},
    }
