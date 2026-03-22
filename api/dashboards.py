"""
Custom Dashboard Builder — create, save, and share dashboards with drag-and-drop widgets.
Replaces Datadog's custom dashboard feature at zero cost.
"""
import uuid
from datetime import datetime
from typing import Any

# ── In-memory store ──────────────────────────────────────────────────────────
_dashboards: dict[str, dict] = {}

# Seed a default dashboard
_default_id = "dash-default"
_dashboards[_default_id] = {
    "id": _default_id,
    "name": "Infrastructure Overview",
    "description": "Default system health dashboard",
    "owner": "system",
    "is_default": True,
    "created_at": datetime.utcnow().isoformat(),
    "updated_at": datetime.utcnow().isoformat(),
    "widgets": [
        {"id": "w1", "type": "stat", "x": 0, "y": 0, "w": 2, "h": 1,
         "config": {"metric": "nodes", "label": "Total Nodes", "color": "green"}},
        {"id": "w2", "type": "stat", "x": 2, "y": 0, "w": 2, "h": 1,
         "config": {"metric": "open_alerts", "label": "Open Alerts", "color": "red"}},
        {"id": "w3", "type": "stat", "x": 4, "y": 0, "w": 2, "h": 1,
         "config": {"metric": "open_incidents", "label": "Incidents", "color": "yellow"}},
        {"id": "w4", "type": "chart", "x": 0, "y": 1, "w": 6, "h": 2,
         "config": {"metric": "cpu_percent", "chart_type": "line", "label": "CPU Usage", "color": "#6366f1"}},
        {"id": "w5", "type": "chart", "x": 0, "y": 3, "w": 3, "h": 2,
         "config": {"metric": "memory_percent", "chart_type": "line", "label": "Memory Usage", "color": "#a78bfa"}},
        {"id": "w6", "type": "chart", "x": 3, "y": 3, "w": 3, "h": 2,
         "config": {"metric": "disk_percent", "chart_type": "line", "label": "Disk Usage", "color": "#fbbf24"}},
        {"id": "w7", "type": "alert-feed", "x": 0, "y": 5, "w": 6, "h": 2,
         "config": {"max_items": 10, "label": "Recent Alerts"}},
    ],
}


def list_dashboards(owner: str | None = None) -> list[dict]:
    dashes = list(_dashboards.values())
    if owner:
        dashes = [d for d in dashes if d["owner"] in (owner, "system")]
    return sorted(dashes, key=lambda d: d.get("created_at", ""), reverse=True)


def get_dashboard(dashboard_id: str) -> dict | None:
    return _dashboards.get(dashboard_id)


def create_dashboard(data: dict, owner: str = "anonymous") -> dict:
    dash_id = f"dash-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow().isoformat()
    dashboard = {
        "id": dash_id,
        "name": data.get("name", "Untitled Dashboard"),
        "description": data.get("description", ""),
        "owner": owner,
        "is_default": False,
        "created_at": now,
        "updated_at": now,
        "widgets": data.get("widgets", []),
    }
    _dashboards[dash_id] = dashboard
    return dashboard


def update_dashboard(dashboard_id: str, data: dict) -> dict | None:
    dash = _dashboards.get(dashboard_id)
    if not dash:
        return None
    for key in ("name", "description", "widgets"):
        if key in data:
            dash[key] = data[key]
    dash["updated_at"] = datetime.utcnow().isoformat()
    return dash


def delete_dashboard(dashboard_id: str) -> bool:
    if dashboard_id in _dashboards and not _dashboards[dashboard_id].get("is_default"):
        del _dashboards[dashboard_id]
        return True
    return False


def duplicate_dashboard(dashboard_id: str, owner: str = "anonymous") -> dict | None:
    original = _dashboards.get(dashboard_id)
    if not original:
        return None
    data = {
        "name": f"{original['name']} (Copy)",
        "description": original.get("description", ""),
        "widgets": [
            {**w, "id": f"w-{uuid.uuid4().hex[:6]}"} for w in original.get("widgets", [])
        ],
    }
    return create_dashboard(data, owner)


# ── Widget templates ─────────────────────────────────────────────────────────
WIDGET_TYPES = [
    {
        "type": "stat",
        "label": "Metric Value",
        "description": "Single big number with label",
        "icon": "hash",
        "default_size": {"w": 2, "h": 1},
        "config_fields": [
            {"key": "metric", "label": "Metric", "type": "select",
             "options": ["nodes", "open_alerts", "critical_alerts", "open_incidents",
                        "total_logs", "kb_entries", "synthetic_up", "cpu_percent",
                        "memory_percent", "disk_percent", "process_count"]},
            {"key": "label", "label": "Display Label", "type": "text"},
            {"key": "color", "label": "Color", "type": "select",
             "options": ["green", "red", "yellow", "cyan", "purple", "blue"]},
        ],
    },
    {
        "type": "chart",
        "label": "Time Series Chart",
        "description": "Line or area chart over time",
        "icon": "trending-up",
        "default_size": {"w": 3, "h": 2},
        "config_fields": [
            {"key": "metric", "label": "Metric", "type": "select",
             "options": ["cpu_percent", "memory_percent", "disk_percent",
                        "net_bytes_recv", "net_bytes_sent", "load_avg_1m", "process_count"]},
            {"key": "chart_type", "label": "Chart Type", "type": "select",
             "options": ["line", "area", "bar"]},
            {"key": "label", "label": "Title", "type": "text"},
            {"key": "color", "label": "Color", "type": "color"},
        ],
    },
    {
        "type": "gauge",
        "label": "Gauge",
        "description": "Circular gauge showing percentage",
        "icon": "gauge",
        "default_size": {"w": 2, "h": 2},
        "config_fields": [
            {"key": "metric", "label": "Metric", "type": "select",
             "options": ["cpu_percent", "memory_percent", "disk_percent"]},
            {"key": "label", "label": "Title", "type": "text"},
            {"key": "thresholds", "label": "Warn/Crit %", "type": "text", "placeholder": "70,90"},
        ],
    },
    {
        "type": "alert-feed",
        "label": "Alert Feed",
        "description": "Live scrolling list of recent alerts",
        "icon": "bell",
        "default_size": {"w": 3, "h": 2},
        "config_fields": [
            {"key": "max_items", "label": "Max Items", "type": "number"},
            {"key": "severity_filter", "label": "Severity", "type": "select",
             "options": ["all", "critical", "high", "medium", "low"]},
        ],
    },
    {
        "type": "node-list",
        "label": "Node Status List",
        "description": "Table of nodes with health status",
        "icon": "server",
        "default_size": {"w": 3, "h": 2},
        "config_fields": [
            {"key": "max_items", "label": "Max Items", "type": "number"},
            {"key": "sort_by", "label": "Sort By", "type": "select",
             "options": ["name", "cpu", "memory", "status"]},
        ],
    },
    {
        "type": "text",
        "label": "Text / Markdown",
        "description": "Rich text or markdown note",
        "icon": "file-text",
        "default_size": {"w": 2, "h": 1},
        "config_fields": [
            {"key": "content", "label": "Content", "type": "textarea"},
        ],
    },
    {
        "type": "uptime",
        "label": "Uptime Monitor",
        "description": "Shows synthetic check uptime bars",
        "icon": "activity",
        "default_size": {"w": 6, "h": 1},
        "config_fields": [
            {"key": "label", "label": "Title", "type": "text"},
        ],
    },
]


def get_widget_types() -> list[dict]:
    return WIDGET_TYPES
