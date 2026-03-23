"""
Metric Explorer — interactive query builder for metrics.
Select metric, group by node/tag, apply functions, adjustable time range.
"""
import random
import math
from datetime import datetime, timedelta
from typing import Any

# Available metrics
METRICS = [
    {"id": "cpu_percent", "name": "CPU Usage", "unit": "%", "group": "System"},
    {"id": "memory_percent", "name": "Memory Usage", "unit": "%", "group": "System"},
    {"id": "disk_percent", "name": "Disk Usage", "unit": "%", "group": "System"},
    {"id": "load_avg_1m", "name": "Load Average (1m)", "unit": "", "group": "System"},
    {"id": "load_avg_5m", "name": "Load Average (5m)", "unit": "", "group": "System"},
    {"id": "load_avg_15m", "name": "Load Average (15m)", "unit": "", "group": "System"},
    {"id": "network_bytes_sent", "name": "Network Out", "unit": "bytes/s", "group": "Network"},
    {"id": "network_bytes_recv", "name": "Network In", "unit": "bytes/s", "group": "Network"},
    {"id": "disk_read_bytes", "name": "Disk Read", "unit": "bytes/s", "group": "Disk"},
    {"id": "disk_write_bytes", "name": "Disk Write", "unit": "bytes/s", "group": "Disk"},
    {"id": "process_count", "name": "Process Count", "unit": "", "group": "System"},
    {"id": "tcp_connections", "name": "TCP Connections", "unit": "", "group": "Network"},
    {"id": "http_requests_per_sec", "name": "HTTP Requests/sec", "unit": "req/s", "group": "Application"},
    {"id": "http_latency_p50", "name": "HTTP Latency P50", "unit": "ms", "group": "Application"},
    {"id": "http_latency_p95", "name": "HTTP Latency P95", "unit": "ms", "group": "Application"},
    {"id": "http_latency_p99", "name": "HTTP Latency P99", "unit": "ms", "group": "Application"},
    {"id": "http_error_rate", "name": "HTTP Error Rate", "unit": "%", "group": "Application"},
    {"id": "gc_pause_ms", "name": "GC Pause Time", "unit": "ms", "group": "Application"},
    {"id": "container_cpu", "name": "Container CPU", "unit": "%", "group": "Container"},
    {"id": "container_memory", "name": "Container Memory", "unit": "MB", "group": "Container"},
]

FUNCTIONS = [
    {"id": "avg", "name": "Average", "description": "Mean value over the window"},
    {"id": "sum", "name": "Sum", "description": "Total sum over the window"},
    {"id": "max", "name": "Maximum", "description": "Peak value in the window"},
    {"id": "min", "name": "Minimum", "description": "Lowest value in the window"},
    {"id": "rate", "name": "Rate", "description": "Per-second rate of change"},
    {"id": "count", "name": "Count", "description": "Number of data points"},
    {"id": "p95", "name": "P95", "description": "95th percentile"},
    {"id": "p99", "name": "P99", "description": "99th percentile"},
    {"id": "stddev", "name": "Std Dev", "description": "Standard deviation"},
]

TIME_RANGES = [
    {"id": "15m", "name": "Last 15 min", "minutes": 15},
    {"id": "1h", "name": "Last 1 hour", "minutes": 60},
    {"id": "3h", "name": "Last 3 hours", "minutes": 180},
    {"id": "6h", "name": "Last 6 hours", "minutes": 360},
    {"id": "12h", "name": "Last 12 hours", "minutes": 720},
    {"id": "24h", "name": "Last 24 hours", "minutes": 1440},
    {"id": "3d", "name": "Last 3 days", "minutes": 4320},
    {"id": "7d", "name": "Last 7 days", "minutes": 10080},
]

NODES = ["node-1", "node-2", "node-3", "prod-web-1", "prod-web-2", "prod-db-1", "staging-1"]

# Metric baseline profiles for realistic data generation
_PROFILES = {
    "cpu_percent": {"base": 35, "variance": 20, "spike_chance": 0.05, "spike_mag": 40},
    "memory_percent": {"base": 62, "variance": 8, "spike_chance": 0.02, "spike_mag": 20},
    "disk_percent": {"base": 45, "variance": 3, "spike_chance": 0.01, "spike_mag": 10},
    "load_avg_1m": {"base": 1.5, "variance": 0.8, "spike_chance": 0.05, "spike_mag": 4},
    "load_avg_5m": {"base": 1.3, "variance": 0.5, "spike_chance": 0.03, "spike_mag": 3},
    "load_avg_15m": {"base": 1.1, "variance": 0.3, "spike_chance": 0.02, "spike_mag": 2},
    "network_bytes_sent": {"base": 500000, "variance": 200000, "spike_chance": 0.04, "spike_mag": 800000},
    "network_bytes_recv": {"base": 800000, "variance": 300000, "spike_chance": 0.04, "spike_mag": 1200000},
    "disk_read_bytes": {"base": 100000, "variance": 80000, "spike_chance": 0.03, "spike_mag": 500000},
    "disk_write_bytes": {"base": 150000, "variance": 100000, "spike_chance": 0.03, "spike_mag": 600000},
    "process_count": {"base": 180, "variance": 30, "spike_chance": 0.02, "spike_mag": 80},
    "tcp_connections": {"base": 120, "variance": 40, "spike_chance": 0.04, "spike_mag": 200},
    "http_requests_per_sec": {"base": 250, "variance": 100, "spike_chance": 0.05, "spike_mag": 500},
    "http_latency_p50": {"base": 15, "variance": 8, "spike_chance": 0.04, "spike_mag": 50},
    "http_latency_p95": {"base": 45, "variance": 20, "spike_chance": 0.05, "spike_mag": 150},
    "http_latency_p99": {"base": 120, "variance": 50, "spike_chance": 0.06, "spike_mag": 400},
    "http_error_rate": {"base": 0.5, "variance": 0.3, "spike_chance": 0.03, "spike_mag": 8},
    "gc_pause_ms": {"base": 5, "variance": 3, "spike_chance": 0.04, "spike_mag": 50},
    "container_cpu": {"base": 25, "variance": 15, "spike_chance": 0.05, "spike_mag": 50},
    "container_memory": {"base": 512, "variance": 128, "spike_chance": 0.03, "spike_mag": 256},
}


def _generate_series(metric_id: str, node: str, minutes: int, interval_sec: int = 60) -> list[dict]:
    """Generate a realistic time series for a metric."""
    profile = _PROFILES.get(metric_id, {"base": 50, "variance": 15, "spike_chance": 0.03, "spike_mag": 30})
    now = datetime.utcnow()
    points = []
    num_points = minutes * 60 // interval_sec
    # Node-specific offset for variety
    node_offset = hash(node) % 20 - 10

    val = profile["base"] + node_offset
    for i in range(num_points):
        ts = now - timedelta(seconds=(num_points - i) * interval_sec)
        # Random walk with mean reversion
        drift = (profile["base"] + node_offset - val) * 0.05
        noise = random.gauss(0, profile["variance"] * 0.3)
        val += drift + noise
        # Occasional spikes
        if random.random() < profile["spike_chance"]:
            val += random.choice([-1, 1]) * profile["spike_mag"] * random.random()
        # Diurnal pattern for some metrics
        hour = (ts.hour + ts.minute / 60)
        diurnal = math.sin((hour - 6) / 24 * 2 * math.pi) * profile["variance"] * 0.3
        actual = max(0, val + diurnal)

        points.append({"ts": ts.isoformat(), "value": round(actual, 2)})

    return points


def _apply_function(values: list[float], func: str) -> float:
    if not values:
        return 0
    if func == "avg":
        return round(sum(values) / len(values), 2)
    if func == "sum":
        return round(sum(values), 2)
    if func == "max":
        return round(max(values), 2)
    if func == "min":
        return round(min(values), 2)
    if func == "count":
        return len(values)
    if func == "rate":
        if len(values) < 2:
            return 0
        return round((values[-1] - values[0]) / max(len(values), 1), 2)
    if func == "p95":
        s = sorted(values)
        return round(s[int(len(s) * 0.95)], 2)
    if func == "p99":
        s = sorted(values)
        return round(s[int(len(s) * 0.99)], 2)
    if func == "stddev":
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return round(math.sqrt(variance), 2)
    return round(sum(values) / len(values), 2)


def query(metric_id: str, time_range: str = "1h", func: str = "avg",
          group_by: str | None = None, nodes: list[str] | None = None) -> dict:
    """Execute a metric query and return time series data."""
    # Resolve time range
    tr = next((t for t in TIME_RANGES if t["id"] == time_range), TIME_RANGES[1])
    minutes = tr["minutes"]

    # Determine granularity
    if minutes <= 60:
        interval = 15  # 15-second intervals for <=1h
    elif minutes <= 360:
        interval = 60  # 1-min intervals for <=6h
    elif minutes <= 1440:
        interval = 300  # 5-min intervals for <=24h
    else:
        interval = 900  # 15-min intervals for >24h

    target_nodes = nodes if nodes else NODES
    metric = next((m for m in METRICS if m["id"] == metric_id), None)

    if group_by == "node":
        # Return per-node series
        series = {}
        for node in target_nodes:
            raw = _generate_series(metric_id, node, minutes, interval)
            series[node] = raw
        # Compute aggregated stats per node
        node_stats = {}
        for node, pts in series.items():
            vals = [p["value"] for p in pts]
            node_stats[node] = {
                "avg": _apply_function(vals, "avg"),
                "max": _apply_function(vals, "max"),
                "min": _apply_function(vals, "min"),
                "current": vals[-1] if vals else 0,
            }
        return {
            "metric": metric,
            "time_range": tr,
            "function": func,
            "group_by": "node",
            "interval_sec": interval,
            "series": {node: pts for node, pts in series.items()},
            "stats": node_stats,
        }
    else:
        # Aggregate across all nodes
        all_series = {}
        for node in target_nodes:
            for pt in _generate_series(metric_id, node, minutes, interval):
                ts = pt["ts"]
                if ts not in all_series:
                    all_series[ts] = []
                all_series[ts].append(pt["value"])

        aggregated = []
        for ts in sorted(all_series.keys()):
            val = _apply_function(all_series[ts], func)
            aggregated.append({"ts": ts, "value": val})

        all_vals = [p["value"] for p in aggregated]
        return {
            "metric": metric,
            "time_range": tr,
            "function": func,
            "group_by": None,
            "interval_sec": interval,
            "series": {"all": aggregated},
            "stats": {
                "all": {
                    "avg": _apply_function(all_vals, "avg"),
                    "max": _apply_function(all_vals, "max"),
                    "min": _apply_function(all_vals, "min"),
                    "current": all_vals[-1] if all_vals else 0,
                }
            },
        }


def get_available_metrics() -> list[dict]:
    return METRICS


def get_available_functions() -> list[dict]:
    return FUNCTIONS


def get_time_ranges() -> list[dict]:
    return TIME_RANGES


def get_available_nodes() -> list[str]:
    return NODES


def get_explorer_config() -> dict:
    """Return all config needed by the UI query builder."""
    return {
        "metrics": METRICS,
        "functions": FUNCTIONS,
        "time_ranges": TIME_RANGES,
        "nodes": NODES,
        "groups": sorted(set(m["group"] for m in METRICS)),
    }
