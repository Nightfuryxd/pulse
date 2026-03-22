"""
SLO/SLA Tracking — Service Level Objectives & Agreements for PULSE.

Defines objectives like:
  - "API latency p99 < 500ms" (99.9% of the time)
  - "Uptime >= 99.95%"
  - "Error rate < 0.1%"

Tracks compliance over rolling windows (7d, 30d, 90d) and alerts on breaches.
SLOs are defined in config/slos.yaml and computed from real metrics.
"""
import asyncio
import os
import yaml
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ── SLO definitions ──────────────────────────────────────────────────────────

_slos: list[dict] = []
_slo_data: dict[str, deque] = defaultdict(lambda: deque(maxlen=86400))  # 24h at 1s granularity
_slo_status: dict[str, dict] = {}  # current compliance per SLO
_slo_breaches: list[dict] = []


def load_slos() -> list[dict]:
    """Load SLO definitions from config/slos.yaml."""
    global _slos
    paths = [
        Path(__file__).parent / "config" / "slos.yaml",
        Path("/app/config/slos.yaml"),
    ]
    for p in paths:
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f) or {}
                _slos = data.get("slos", [])
                print(f"[SLO] Loaded {len(_slos)} SLO definitions from {p}")
                return _slos
    _slos = []
    return _slos


def get_slos() -> list[dict]:
    return _slos


def get_slo_status() -> dict:
    return dict(_slo_status)


def get_slo_breaches(limit: int = 50) -> list[dict]:
    return list(_slo_breaches[-limit:])


# ── SLO types ────────────────────────────────────────────────────────────────

def _evaluate_availability_slo(slo: dict) -> dict:
    """Evaluate an availability/uptime SLO from synthetic monitoring data."""
    from synthetic import get_synthetic_results
    target_id = slo.get("target_id", "")
    results = get_synthetic_results()

    target_result = next((r for r in results if r.get("id") == target_id), None)
    if not target_result:
        return {"status": "no_data", "compliance": None}

    # Calculate from historical data
    data_key = f"avail:{slo['id']}"
    history = _slo_data[data_key]
    is_up = 1 if target_result.get("status") == "up" else 0
    history.append({"ts": datetime.utcnow(), "value": is_up})

    if len(history) < 2:
        return {"status": "insufficient_data", "compliance": None, "samples": len(history)}

    # Calculate compliance over window
    window_seconds = slo.get("window_days", 30) * 86400
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    in_window = [d for d in history if d["ts"] >= cutoff]

    if not in_window:
        return {"status": "no_data_in_window", "compliance": None}

    uptime_pct = (sum(d["value"] for d in in_window) / len(in_window)) * 100
    target_pct = slo.get("target", 99.9)

    return {
        "status": "met" if uptime_pct >= target_pct else "breached",
        "compliance": round(uptime_pct, 4),
        "target": target_pct,
        "samples": len(in_window),
        "window_days": slo.get("window_days", 30),
        "error_budget_remaining": round(uptime_pct - target_pct, 4),
    }


def _evaluate_latency_slo(slo: dict) -> dict:
    """Evaluate a latency SLO (e.g., p99 < 500ms)."""
    from synthetic import get_synthetic_results
    target_id = slo.get("target_id", "")
    results = get_synthetic_results()

    target_result = next((r for r in results if r.get("id") == target_id), None)
    if not target_result:
        return {"status": "no_data", "compliance": None}

    data_key = f"latency:{slo['id']}"
    history = _slo_data[data_key]
    latency_ms = target_result.get("response_time_ms", 0)
    history.append({"ts": datetime.utcnow(), "value": latency_ms})

    if len(history) < 10:
        return {"status": "insufficient_data", "compliance": None, "samples": len(history)}

    window_seconds = slo.get("window_days", 30) * 86400
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    in_window = [d for d in history if d["ts"] >= cutoff]

    if not in_window:
        return {"status": "no_data_in_window", "compliance": None}

    threshold_ms = slo.get("threshold_ms", 500)
    percentile = slo.get("percentile", 99)

    values = sorted([d["value"] for d in in_window])
    p_index = int(len(values) * percentile / 100)
    p_value = values[min(p_index, len(values) - 1)]

    within_slo = sum(1 for d in in_window if d["value"] <= threshold_ms)
    compliance_pct = (within_slo / len(in_window)) * 100

    target_pct = slo.get("target", 99.0)

    return {
        "status": "met" if compliance_pct >= target_pct else "breached",
        "compliance": round(compliance_pct, 4),
        "target": target_pct,
        "current_p_value": round(p_value, 2),
        "percentile": percentile,
        "threshold_ms": threshold_ms,
        "samples": len(in_window),
        "window_days": slo.get("window_days", 30),
        "error_budget_remaining": round(compliance_pct - target_pct, 4),
    }


def _evaluate_error_rate_slo(slo: dict) -> dict:
    """Evaluate an error rate SLO from metric data."""
    data_key = f"errrate:{slo['id']}"
    history = _slo_data[data_key]

    if len(history) < 10:
        return {"status": "insufficient_data", "compliance": None, "samples": len(history)}

    window_seconds = slo.get("window_days", 30) * 86400
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    in_window = [d for d in history if d["ts"] >= cutoff]

    if not in_window:
        return {"status": "no_data_in_window", "compliance": None}

    max_error_rate = slo.get("max_error_rate", 0.1)
    within_slo = sum(1 for d in in_window if d["value"] <= max_error_rate)
    compliance_pct = (within_slo / len(in_window)) * 100
    target_pct = slo.get("target", 99.9)

    current_rate = in_window[-1]["value"] if in_window else 0

    return {
        "status": "met" if compliance_pct >= target_pct else "breached",
        "compliance": round(compliance_pct, 4),
        "target": target_pct,
        "current_error_rate": round(current_rate, 4),
        "max_error_rate": max_error_rate,
        "samples": len(in_window),
        "window_days": slo.get("window_days", 30),
        "error_budget_remaining": round(compliance_pct - target_pct, 4),
    }


def _evaluate_metric_slo(slo: dict) -> dict:
    """Evaluate a generic metric threshold SLO (e.g., CPU < 80%)."""
    data_key = f"metric:{slo['id']}"
    history = _slo_data[data_key]

    if len(history) < 10:
        return {"status": "insufficient_data", "compliance": None, "samples": len(history)}

    window_seconds = slo.get("window_days", 30) * 86400
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    in_window = [d for d in history if d["ts"] >= cutoff]

    if not in_window:
        return {"status": "no_data_in_window", "compliance": None}

    threshold = slo.get("threshold", 80)
    operator = slo.get("operator", "lt")  # lt, lte, gt, gte

    if operator == "lt":
        within = sum(1 for d in in_window if d["value"] < threshold)
    elif operator == "lte":
        within = sum(1 for d in in_window if d["value"] <= threshold)
    elif operator == "gt":
        within = sum(1 for d in in_window if d["value"] > threshold)
    else:
        within = sum(1 for d in in_window if d["value"] >= threshold)

    compliance_pct = (within / len(in_window)) * 100
    target_pct = slo.get("target", 99.0)

    return {
        "status": "met" if compliance_pct >= target_pct else "breached",
        "compliance": round(compliance_pct, 4),
        "target": target_pct,
        "current_value": round(in_window[-1]["value"], 2),
        "threshold": threshold,
        "operator": operator,
        "samples": len(in_window),
        "window_days": slo.get("window_days", 30),
        "error_budget_remaining": round(compliance_pct - target_pct, 4),
    }


# ── Feed data into SLOs ─────────────────────────────────────────────────────

def feed_metric(node_id: str, metric: dict):
    """Called from metric ingest to feed data into metric-based SLOs."""
    for slo in _slos:
        if slo.get("type") != "metric":
            continue
        if slo.get("node_id") and slo["node_id"] != node_id:
            continue
        metric_name = slo.get("metric_name", "")
        if metric_name and metric_name in metric:
            data_key = f"metric:{slo['id']}"
            _slo_data[data_key].append({"ts": datetime.utcnow(), "value": metric[metric_name]})


def feed_error(node_id: str, is_error: bool):
    """Called when processing requests to track error rates."""
    for slo in _slos:
        if slo.get("type") != "error_rate":
            continue
        if slo.get("node_id") and slo["node_id"] != node_id:
            continue
        data_key = f"errrate:{slo['id']}"
        _slo_data[data_key].append({"ts": datetime.utcnow(), "value": 1.0 if is_error else 0.0})


# ── Evaluation loop ──────────────────────────────────────────────────────────

EVALUATORS = {
    "availability": _evaluate_availability_slo,
    "latency":      _evaluate_latency_slo,
    "error_rate":   _evaluate_error_rate_slo,
    "metric":       _evaluate_metric_slo,
}


def evaluate_all_slos() -> dict[str, dict]:
    """Evaluate all SLOs and return status map."""
    results = {}
    for slo in _slos:
        slo_type = slo.get("type", "metric")
        evaluator = EVALUATORS.get(slo_type)
        if not evaluator:
            results[slo["id"]] = {"status": "unknown_type", "type": slo_type}
            continue
        result = evaluator(slo)
        result["id"] = slo["id"]
        result["name"] = slo.get("name", slo["id"])
        result["type"] = slo_type
        result["description"] = slo.get("description", "")
        results[slo["id"]] = result

        # Track breaches
        if result.get("status") == "breached":
            prev = _slo_status.get(slo["id"], {})
            if prev.get("status") != "breached":
                breach = {
                    "slo_id": slo["id"],
                    "slo_name": slo.get("name", slo["id"]),
                    "type": slo_type,
                    "ts": datetime.utcnow().isoformat(),
                    "compliance": result.get("compliance"),
                    "target": result.get("target"),
                    "error_budget_remaining": result.get("error_budget_remaining"),
                }
                _slo_breaches.append(breach)

    _slo_status.update(results)
    return results


async def slo_loop():
    """Background loop evaluating SLOs every 30 seconds."""
    load_slos()
    if not _slos:
        print("[SLO] No SLOs defined in config/slos.yaml — loop idle")
    while True:
        try:
            if _slos:
                evaluate_all_slos()
        except Exception as e:
            print(f"[SLO] Evaluation error: {e}")
        await asyncio.sleep(30)
