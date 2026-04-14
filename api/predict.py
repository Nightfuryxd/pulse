"""
Predictive Alerting — Linear regression forecasting for PULSE.

Uses a rolling window of metric samples to predict future values.
If a predicted value will cross a threshold within the forecast horizon,
fires a predictive alert so teams can act before the problem happens.

No external ML libraries needed — pure numpy-free linear regression.

Improvements:
  - Weighted linear regression (recent points weighted higher)
  - Confidence intervals on predictions
  - Minimum 30 data points required before predicting
"""
import asyncio
import math
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

def _linear_regression(points: list[tuple[float, float]], weights: list[float] | None = None) -> tuple[float, float, float]:
    """
    Weighted linear regression.  When *weights* is None, falls back to OLS.
    Returns (slope, intercept, r_squared).
    """
    n = len(points)
    if n < 2:
        return 0.0, 0.0, 0.0

    if weights is None:
        weights = [1.0] * n

    sum_w  = sum(weights)
    sum_wx = sum(w * p[0] for w, p in zip(weights, points))
    sum_wy = sum(w * p[1] for w, p in zip(weights, points))
    sum_wxy = sum(w * p[0] * p[1] for w, p in zip(weights, points))
    sum_wx2 = sum(w * p[0] ** 2 for w, p in zip(weights, points))

    denom = sum_w * sum_wx2 - sum_wx ** 2
    if abs(denom) < 1e-10:
        return 0.0, sum_wy / sum_w, 0.0

    slope = (sum_w * sum_wxy - sum_wx * sum_wy) / denom
    intercept = (sum_wy - slope * sum_wx) / sum_w

    # R-squared (weighted)
    mean_y = sum_wy / sum_w
    ss_res = sum(w * (p[1] - (slope * p[0] + intercept)) ** 2 for w, p in zip(weights, points))
    ss_tot = sum(w * (p[1] - mean_y) ** 2 for w, p in zip(weights, points))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return slope, intercept, r_squared


def _recency_weights(n: int) -> list[float]:
    """Generate linearly increasing weights so recent points matter more."""
    return [i / n for i in range(1, n + 1)]


def _prediction_confidence(points: list[tuple[float, float]], slope: float,
                           intercept: float, future_x: float,
                           z: float = 1.96) -> tuple[float, float]:
    """
    Return (lower, upper) confidence interval for the predicted value
    at *future_x* using the standard error of the regression estimate.
    z=1.96 gives a ~95 % interval.
    """
    n = len(points)
    if n < 3:
        return float("-inf"), float("inf")

    residuals = [p[1] - (slope * p[0] + intercept) for p in points]
    se = math.sqrt(sum(r ** 2 for r in residuals) / (n - 2))

    mean_x = sum(p[0] for p in points) / n
    ss_xx = sum((p[0] - mean_x) ** 2 for p in points)
    if ss_xx < 1e-10:
        return float("-inf"), float("inf")

    margin = z * se * math.sqrt(1 + 1 / n + (future_x - mean_x) ** 2 / ss_xx)
    predicted = slope * future_x + intercept
    return predicted - margin, predicted + margin


def _predict_value(points: list[tuple[float, float]], future_seconds: float) -> tuple[float, float, float, float, float]:
    """
    Predict a future value using weighted linear regression.
    Returns (predicted_value, slope, r_squared, ci_lower, ci_upper).
    """
    weights = _recency_weights(len(points))
    slope, intercept, r_sq = _linear_regression(points, weights)
    last_x = points[-1][0]
    future_x = last_x + future_seconds
    predicted = slope * future_x + intercept
    ci_lo, ci_hi = _prediction_confidence(points, slope, intercept, future_x)
    return predicted, slope, r_sq, ci_lo, ci_hi


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

        # Run prediction (weighted regression)
        points = list(history)
        forecast_seconds = FORECAST_HORIZON_MINUTES * 60
        predicted, slope, r_sq, ci_lo, ci_hi = _predict_value(points, forecast_seconds)

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
                "confidence_interval": {
                    "lower": round(ci_lo, 2),
                    "upper": round(ci_hi, 2),
                },
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
        predicted, slope, r_sq, ci_lo, ci_hi = _predict_value(points, forecast_seconds)
        current = points[-1][1]

        trend = "rising" if slope > 0.001 else ("falling" if slope < -0.001 else "stable")

        forecasts[metric_name] = {
            "current": round(current, 2),
            "predicted_1h": round(predicted, 2),
            "confidence_interval": {"lower": round(ci_lo, 2), "upper": round(ci_hi, 2)},
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
        predicted, slope, r_sq, ci_lo, ci_hi = _predict_value(points, seconds)
        forecast_points.append({
            "minutes_ahead": minutes,
            "predicted_value": round(predicted, 2),
            "ci_lower": round(ci_lo, 2),
            "ci_upper": round(ci_hi, 2),
        })

    weights = _recency_weights(len(points))
    slope, intercept, r_sq = _linear_regression(points, weights)

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
