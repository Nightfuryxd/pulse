"""
Billing & Usage Dashboard — track metric volume, log ingestion, API calls.
Essential for SaaS pricing model.
"""
import random
from datetime import datetime, timedelta
from typing import Any

# ── Plans ────────────────────────────────────────────────────────────────────
PLANS = [
    {
        "id": "free", "name": "Free", "price": 0,
        "limits": {"nodes": 5, "metrics_per_month": 100000, "logs_per_month": 50000,
                   "api_calls_per_month": 10000, "retention_days": 7, "users": 3,
                   "alerts": 10, "dashboards": 2},
        "features": ["Basic monitoring", "Email alerts", "7-day retention"],
    },
    {
        "id": "pro", "name": "Pro", "price": 29,
        "limits": {"nodes": 50, "metrics_per_month": 5000000, "logs_per_month": 2000000,
                   "api_calls_per_month": 500000, "retention_days": 30, "users": 20,
                   "alerts": 100, "dashboards": 20},
        "features": ["All monitoring", "13 notification channels", "30-day retention",
                     "Custom dashboards", "On-call scheduling", "AI RCA"],
    },
    {
        "id": "enterprise", "name": "Enterprise", "price": 99,
        "limits": {"nodes": 500, "metrics_per_month": 50000000, "logs_per_month": 20000000,
                   "api_calls_per_month": 5000000, "retention_days": 365, "users": -1,
                   "alerts": -1, "dashboards": -1},
        "features": ["Unlimited users", "365-day retention", "SSO/SAML", "Audit log",
                     "SLA compliance", "Dedicated support", "Custom integrations"],
    },
]

# Current plan (demo)
_current_plan = "pro"

# ── Usage data generation ────────────────────────────────────────────────────

def _gen_daily_usage(days: int = 30) -> list[dict]:
    now = datetime.utcnow()
    usage = []
    for i in range(days):
        d = now - timedelta(days=days - 1 - i)
        # Weekday/weekend variation
        is_weekend = d.weekday() >= 5
        base_mult = 0.6 if is_weekend else 1.0
        usage.append({
            "date": d.strftime("%Y-%m-%d"),
            "metrics": int(random.gauss(150000, 30000) * base_mult),
            "logs": int(random.gauss(60000, 15000) * base_mult),
            "api_calls": int(random.gauss(15000, 4000) * base_mult),
            "nodes_active": random.randint(5, 7),
            "storage_mb": round(random.gauss(450, 50), 1),
        })
    return usage


_cached_usage = _gen_daily_usage(30)


def get_current_plan() -> dict:
    plan = next((p for p in PLANS if p["id"] == _current_plan), PLANS[1])
    return {**plan, "is_current": True}


def get_plans() -> list[dict]:
    return [{**p, "is_current": p["id"] == _current_plan} for p in PLANS]


def get_usage_summary() -> dict:
    plan = next((p for p in PLANS if p["id"] == _current_plan), PLANS[1])
    limits = plan["limits"]
    usage = _cached_usage

    # Current month totals
    total_metrics = sum(d["metrics"] for d in usage)
    total_logs = sum(d["logs"] for d in usage)
    total_api_calls = sum(d["api_calls"] for d in usage)
    current_nodes = usage[-1]["nodes_active"] if usage else 0
    current_storage = usage[-1]["storage_mb"] if usage else 0

    def pct(used, limit):
        if limit <= 0:
            return 0
        return round(used / limit * 100, 1)

    return {
        "plan": plan["name"],
        "plan_id": plan["id"],
        "price": plan["price"],
        "billing_period": "monthly",
        "period_start": (datetime.utcnow().replace(day=1)).strftime("%Y-%m-%d"),
        "period_end": ((datetime.utcnow().replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d"),
        "usage": {
            "metrics": {
                "used": total_metrics,
                "limit": limits["metrics_per_month"],
                "percent": pct(total_metrics, limits["metrics_per_month"]),
                "unit": "metrics/month",
            },
            "logs": {
                "used": total_logs,
                "limit": limits["logs_per_month"],
                "percent": pct(total_logs, limits["logs_per_month"]),
                "unit": "logs/month",
            },
            "api_calls": {
                "used": total_api_calls,
                "limit": limits["api_calls_per_month"],
                "percent": pct(total_api_calls, limits["api_calls_per_month"]),
                "unit": "calls/month",
            },
            "nodes": {
                "used": current_nodes,
                "limit": limits["nodes"],
                "percent": pct(current_nodes, limits["nodes"]),
                "unit": "nodes",
            },
            "storage": {
                "used": round(current_storage, 1),
                "limit": 5000,  # 5GB for Pro
                "percent": pct(current_storage, 5000),
                "unit": "MB",
            },
        },
        "alerts_used": 8,
        "alerts_limit": limits["alerts"],
        "dashboards_used": 3,
        "dashboards_limit": limits["dashboards"],
        "users_used": 7,
        "users_limit": limits["users"],
        "retention_days": limits["retention_days"],
    }


def get_daily_usage(days: int = 30) -> list[dict]:
    return _cached_usage[-days:]


def get_usage_breakdown() -> dict:
    """Break down usage by category for the pie/bar charts."""
    return {
        "by_metric_type": {
            "System (CPU, Memory, Disk)": 45,
            "Network": 20,
            "Application (HTTP)": 25,
            "Container": 10,
        },
        "by_node": {
            "prod-web-1": 22,
            "prod-web-2": 20,
            "prod-db-1": 18,
            "node-1": 15,
            "node-2": 12,
            "node-3": 8,
            "staging-1": 5,
        },
        "by_log_source": {
            "api-gateway": 35,
            "auth-service": 20,
            "database": 15,
            "agent": 15,
            "system": 15,
        },
    }


def change_plan(plan_id: str) -> dict | None:
    global _current_plan
    if not any(p["id"] == plan_id for p in PLANS):
        return None
    _current_plan = plan_id
    return get_current_plan()
