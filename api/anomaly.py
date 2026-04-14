"""
PULSE Anomaly Detection — learns normal metric baselines and detects deviations.

Uses statistical methods (rolling mean, standard deviation, z-score) instead of
static thresholds. This catches slow degradation that fixed thresholds miss.

Example: CPU normally at 20%. Static rule fires at 95%.
         Anomaly detection notices 60% is unusual → alerts early.
"""
import asyncio
import math
from collections import OrderedDict, defaultdict, deque
from datetime import datetime, timezone
from typing import Optional


# Rolling window per node per metric — stores last N data points
# Key: (node_id, metric_name) → deque of values
# Bounded to MAX_TRACKED_NODES * num_metrics via LRU eviction.
MAX_TRACKED_KEYS = 5000 * 7  # 5000 nodes × 7 metrics
_baselines: OrderedDict[tuple, deque] = OrderedDict()

# Anomaly config
ZSCORE_THRESHOLD = 3.0       # How many standard deviations = anomaly
MIN_SAMPLES = 30             # Need at least 30 data points before detecting
METRICS_TO_WATCH = [
    "cpu_percent", "memory_percent", "disk_percent",
    "load_avg_1m", "net_bytes_sent", "net_bytes_recv",
    "process_count",
]

# Recent anomalies for API queries
_recent_anomalies: list[dict] = []
MAX_ANOMALIES = 500

# Cooldown to avoid spamming the same anomaly
_cooldown: dict[tuple, float] = {}
COOLDOWN_SECONDS = 300  # Don't re-alert same node+metric within 5 min


def _mean_std(values: list[float]) -> tuple[float, float]:
    """Calculate mean and standard deviation."""
    n = len(values)
    if n < 2:
        return 0.0, 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, math.sqrt(variance)


def evaluate_metric(node_id: str, metric: dict) -> list[dict]:
    """
    Feed a metric data point into the baseline and check for anomalies.
    Returns a list of anomaly events (may be empty).
    """
    anomalies = []
    now = datetime.now(timezone.utc).timestamp()

    for metric_name in METRICS_TO_WATCH:
        value = metric.get(metric_name)
        if value is None:
            continue

        try:
            value = float(value)
        except (ValueError, TypeError):
            continue

        key = (node_id, metric_name)

        # LRU: move to end on access; create if missing
        if key in _baselines:
            _baselines.move_to_end(key)
            window = _baselines[key]
        else:
            window = deque(maxlen=360)
            _baselines[key] = window
            # Evict oldest entry if over capacity
            while len(_baselines) > MAX_TRACKED_KEYS:
                _baselines.popitem(last=False)

        # Add to baseline
        window.append(value)

        # Not enough data yet
        if len(window) < MIN_SAMPLES:
            continue

        # Cooldown check FIRST — skip expensive z-score math when in cooldown
        if now - _cooldown.get(key, 0) < COOLDOWN_SECONDS:
            continue

        # Calculate z-score
        values = list(window)
        mean, std = _mean_std(values[:-1])  # Exclude current value from baseline

        if std < 0.001:  # Near-zero variance — skip (constant metric)
            continue

        zscore = (value - mean) / std

        if abs(zscore) >= ZSCORE_THRESHOLD:
            _cooldown[key] = now

            direction = "spike" if zscore > 0 else "drop"
            severity = "critical" if abs(zscore) >= 4.5 else "high" if abs(zscore) >= 3.5 else "medium"

            anomaly = {
                "node_id": node_id,
                "type": f"anomaly_{metric_name}",
                "severity": severity,
                "source": "anomaly_detection",
                "message": (
                    f"Anomaly: {metric_name} {direction} on {node_id} — "
                    f"value={value:.1f} (baseline={mean:.1f} +/- {std:.1f}, z-score={zscore:.1f})"
                ),
                "data": {
                    "metric": metric_name,
                    "value": round(value, 2),
                    "baseline_mean": round(mean, 2),
                    "baseline_std": round(std, 2),
                    "zscore": round(zscore, 2),
                    "direction": direction,
                    "samples": len(window),
                },
            }
            anomalies.append(anomaly)

            # Store for API
            _recent_anomalies.append({
                **anomaly,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            if len(_recent_anomalies) > MAX_ANOMALIES:
                _recent_anomalies.pop(0)

    return anomalies


def get_baselines(node_id: Optional[str] = None) -> dict:
    """Get current baselines for API queries."""
    result = {}
    for (nid, metric_name), window in _baselines.items():
        if node_id and nid != node_id:
            continue
        if len(window) < MIN_SAMPLES:
            continue
        values = list(window)
        mean, std = _mean_std(values)
        result.setdefault(nid, {})[metric_name] = {
            "mean": round(mean, 2),
            "std": round(std, 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "samples": len(values),
            "current": round(values[-1], 2),
        }
    return result


def get_recent_anomalies(node_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Return recent anomalies."""
    results = _recent_anomalies
    if node_id:
        results = [a for a in results if a.get("node_id") == node_id]
    return results[-limit:]
