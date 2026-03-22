"""
Predictive Alerting — Linear regression forecasting for PULSE.

Uses a rolling window of metric samples to predict future values.
If a predicted value will cross a threshold within the forecast horizon,
fires a predictive alert so teams can act before the problem happens.

No external ML libraries needed — pure numpy-free linear regression.
"""
import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

# ── Configuration ────────────────────────────────────────────────────────────

# Minimum samples before we start predicting
MIN_SAMPLES = 30

# How far ahead to forecast (minutes)
FORECAST_HORIZON_MINUTES = 60

# Rolling window size (samples)
WINDOW_SIZE = 360

# Cooldown between predictions for the same metric (minutes)
PREDICTION_COOLDOWN_MINUTES = 30

# Metrics to forecast and their critical thresholds
FORECAST_TARGETS = {
    "cpu_percent":    {"warn": 80, "crit": 95, "unit": "%"},
    "memory_percent": {"warn": 85, "crit": 95, "unit": "%"},
    "disk_percent":   {"warn": 85, "crit": 95, "unit": "%"},
    "load_avg_1m":    {"warn": 8,  "crit": 16, "unit": ""},
}

# ── State ────────────────────────────────────────────────────────────────────

# {(node_id, metric_name): deque of (timestamp_epoch, value)}
_history: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=WINDOW_SIZE))

# {(node_id, metric_name): last_prediction_time}
_cooldowns: dict[tuple, datetime] = {}

# Recent predictions
_predictions: list[dict] = []
_active_forecasts: dict[str, dict] = {}  # node_id → latest forecast summary


# ── Linear regression (no numpy needed) ─────────────────────────────────────

def _linear_regression(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Simple OLS linear regression. Returns (slope, intercept, r_squared)."""
    n = len(points)
    if n < 2:
        return 0.0, 0.0, 0.0

    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)
    sum_x2 = sum(p[0] ** 2 for p in points)
    sum_y2 = sum(p[1] ** 2 for p in points)

    denom = n * sum_x2 - sum_x ** 2
    if abs(denom) < 1e-10:
        return 0.0, sum_y / n, 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # R-squared
    ss_res = sum((p[1] - (slope * p[0] + intercept)) ** 2 for p in points)
    mean_y = sum_y / n
    ss_tot = sum((p[1] - mean_y) ** 2 for p in points)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return slope, intercept, r_squared


def _predict_value(points: list[tuple[float, float]], future_seconds: float) -> tuple[float, float, float]:
    """Predict a future value. Returns (predicted_value, slope, r_squared)."""
    slope, intercept, r_sq = _linear_regression(points)
    last_x = points[-1][0]
    predicted = slope * (last_x + future_seconds) + intercept
    return predicted, slope, r_sq


# ── Core prediction engine ───────────────────────────────────────────────────

def feed_metric(node_id: str, metric: dict):
    """Feed a new metric sample into the prediction engine."""
    now = datetime.utcnow()
    epoch = now.timestamp()

    for metric_name in FORECAST_TARGETS:
        value = metric.get(metric_name)
        if value is None:
            continue
        key = (node_id, metric_name)
        _history[key].append((epoch, float(value)))


def check_predictions(node_id: str, metric: dict) -> list[dict]:
    """Check if any metrics are predicted to breach thresholds. Returns prediction alerts."""
    now = datetime.utcnow()
    alerts = []

    for metric_name, thresholds in FORECAST_TARGETS.items():
        value = metric.get(metric_name)
        if value is None:
            continue

        key = (node_id, metric_name)
        history = _history[key]

        if len(history) < MIN_SAMPLES:
            continue

        # Check cooldown
        last_pred = _cooldowns.get(key)
        if last_pred and (now - last_pred).total_seconds() < PREDICTION_COOLDOWN_MINUTES * 60:
            continue

        # Run prediction
        points = list(history)
        forecast_seconds = FORECAST_HORIZON_MINUTES * 60
        predicted, slope, r_sq = _predict_value(points, forecast_seconds)

        # Only alert if trend is significant (R² > 0.3) and upward
        if r_sq < 0.3 or slope <= 0:
            continue

        # Check if prediction crosses threshold
        current = float(value)
        severity = None
        threshold = None

        if predicted >= thresholds["crit"] and current < thresholds["crit"]:
            severity = "critical"
            threshold = thresholds["crit"]
        elif predicted >= thresholds["warn"] and current < thresholds["warn"]:
            severity = "high"
            threshold = thresholds["warn"]

        if severity:
            # Estimate time to breach
            if slope > 0:
                time_to_breach_seconds = (threshold - current) / slope
                time_to_breach_minutes = max(0, time_to_breach_seconds / 60)
            else:
                time_to_breach_minutes = FORECAST_HORIZON_MINUTES

            prediction = {
                "node_id": node_id,
                "metric": metric_name,
                "current_value": round(current, 2),
                "predicted_value": round(predicted, 2),
                "threshold": threshold,
                "severity": severity,
                "r_squared": round(r_sq, 3),
                "slope_per_minute": round(slope * 60, 4),
                "time_to_breach_minutes": round(time_to_breach_minutes, 1),
                "forecast_horizon_minutes": FORECAST_HORIZON_MINUTES,
                "ts": now.isoformat(),
                "samples": len(history),
                "unit": thresholds["unit"],
            }

            alerts.append(prediction)
            _predictions.append(prediction)
            _cooldowns[key] = now

            # Keep predictions bounded
            if len(_predictions) > 500:
                _predictions[:] = _predictions[-250:]

    # Update active forecast for this node
    _update_forecast_summary(node_id)

    return alerts


def _update_forecast_summary(node_id: str):
    """Build a summary of all active forecasts for a node."""
    now = datetime.utcnow()
    forecasts = {}

    for metric_name, thresholds in FORECAST_TARGETS.items():
        key = (node_id, metric_name)
        history = _history[key]

        if len(history) < MIN_SAMPLES:
            continue

        points = list(history)
        forecast_seconds = FORECAST_HORIZON_MINUTES * 60
        predicted, slope, r_sq = _predict_value(points, forecast_seconds)
        current = points[-1][1]

        trend = "rising" if slope > 0.001 else ("falling" if slope < -0.001 else "stable")

        forecasts[metric_name] = {
            "current": round(current, 2),
            "predicted_1h": round(predicted, 2),
            "trend": trend,
            "slope_per_min": round(slope * 60, 4),
            "r_squared": round(r_sq, 3),
            "warn_threshold": thresholds["warn"],
            "crit_threshold": thresholds["crit"],
            "unit": thresholds["unit"],
        }

    if forecasts:
        _active_forecasts[node_id] = {
            "node_id": node_id,
            "updated_at": now.isoformat(),
            "metrics": forecasts,
        }


# ── Query functions ──────────────────────────────────────────────────────────

def get_predictions(node_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Get recent prediction alerts."""
    preds = _predictions
    if node_id:
        preds = [p for p in preds if p["node_id"] == node_id]
    return list(preds[-limit:])


def get_forecasts(node_id: Optional[str] = None) -> dict:
    """Get active forecast summaries."""
    if node_id:
        return _active_forecasts.get(node_id, {})
    return dict(_active_forecasts)


def get_forecast_for_metric(node_id: str, metric_name: str, horizon_minutes: int = 60) -> dict:
    """Get detailed forecast for a specific node+metric."""
    key = (node_id, metric_name)
    history = _history[key]

    if len(history) < MIN_SAMPLES:
        return {"error": "insufficient_data", "samples": len(history), "min_required": MIN_SAMPLES}

    points = list(history)
    current = points[-1][1]

    # Generate forecast points at 5-minute intervals
    forecast_points = []
    for minutes in range(5, horizon_minutes + 1, 5):
        seconds = minutes * 60
        predicted, slope, r_sq = _predict_value(points, seconds)
        forecast_points.append({
            "minutes_ahead": minutes,
            "predicted_value": round(predicted, 2),
        })

    slope, intercept, r_sq = _linear_regression(points)

    thresholds = FORECAST_TARGETS.get(metric_name, {})

    return {
        "node_id": node_id,
        "metric": metric_name,
        "current": round(current, 2),
        "samples": len(history),
        "r_squared": round(r_sq, 3),
        "trend": "rising" if slope > 0.001 else ("falling" if slope < -0.001 else "stable"),
        "slope_per_min": round(slope * 60, 4),
        "forecast": forecast_points,
        "warn_threshold": thresholds.get("warn"),
        "crit_threshold": thresholds.get("crit"),
    }
