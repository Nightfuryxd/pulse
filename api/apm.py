"""
APM / Distributed Tracing — trace waterfall visualization.
Stores traces and spans, provides data for the trace waterfall UI.
"""
import uuid
import random
from datetime import datetime, timedelta
from typing import Any

# ── In-memory stores ─────────────────────────────────────────────────────────
_traces: dict[str, dict] = {}
_services: list[str] = ["api-gateway", "auth-service", "user-service", "order-service",
                         "payment-service", "notification-service", "cache-layer", "database"]

STATUS_CODES = [200, 200, 200, 200, 200, 201, 204, 400, 404, 500, 502, 503]
HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]

OPERATIONS = {
    "api-gateway": ["POST /api/login", "GET /api/nodes", "GET /api/alerts", "POST /api/metrics",
                     "GET /api/stats", "GET /api/incidents", "POST /api/events", "GET /api/slos"],
    "auth-service": ["validate_token", "refresh_token", "check_rbac", "hash_password"],
    "user-service": ["get_user", "update_profile", "list_users", "get_preferences"],
    "order-service": ["create_order", "get_order", "list_orders", "cancel_order"],
    "payment-service": ["process_payment", "refund", "check_balance", "verify_card"],
    "notification-service": ["send_slack", "send_email", "send_sms", "push_notification"],
    "cache-layer": ["GET cache", "SET cache", "DEL cache", "SCAN keys"],
    "database": ["SELECT query", "INSERT query", "UPDATE query", "DELETE query", "BEGIN txn", "COMMIT txn"],
}


def _generate_span(trace_id: str, parent_id: str | None, service: str,
                   start_time: datetime, depth: int = 0) -> list[dict]:
    """Generate a span and optional child spans."""
    span_id = uuid.uuid4().hex[:16]
    ops = OPERATIONS.get(service, ["unknown_op"])
    operation = random.choice(ops)

    duration_ms = random.randint(1, 80) if service == "cache-layer" else \
                  random.randint(5, 200) if service == "database" else \
                  random.randint(2, 150)

    status_code = random.choices(STATUS_CODES, weights=[10,10,10,10,10,5,3,1,1,1,1,1])[0]
    has_error = status_code >= 500

    span = {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": parent_id,
        "service": service,
        "operation": operation,
        "start_time": start_time.isoformat(),
        "duration_ms": duration_ms,
        "status_code": status_code,
        "has_error": has_error,
        "tags": {
            "http.method": random.choice(HTTP_METHODS) if "query" not in operation else None,
            "http.status_code": status_code,
            "service.name": service,
        },
        "logs": [],
        "depth": depth,
    }

    if has_error:
        span["logs"].append({
            "ts": (start_time + timedelta(milliseconds=duration_ms - 1)).isoformat(),
            "level": "ERROR",
            "message": f"Internal server error in {service}: {operation}",
        })

    spans = [span]

    # Generate child spans based on service call chain
    if depth < 4 and random.random() > 0.3:
        child_services = {
            "api-gateway": ["auth-service", "user-service", "order-service", "cache-layer"],
            "auth-service": ["database", "cache-layer"],
            "user-service": ["database", "cache-layer"],
            "order-service": ["payment-service", "database", "notification-service"],
            "payment-service": ["database"],
            "notification-service": [],
            "cache-layer": [],
            "database": [],
        }
        possible = child_services.get(service, [])
        num_children = min(random.randint(1, 3), len(possible))
        chosen = random.sample(possible, num_children) if possible else []

        child_offset = random.randint(1, max(1, duration_ms // 4))
        for child_svc in chosen:
            child_start = start_time + timedelta(milliseconds=child_offset)
            child_spans = _generate_span(trace_id, span_id, child_svc, child_start, depth + 1)
            spans.extend(child_spans)
            child_offset += random.randint(5, 30)

        # Adjust parent duration to encompass children
        if len(spans) > 1:
            max_end = max(
                datetime.fromisoformat(s["start_time"]) + timedelta(milliseconds=s["duration_ms"])
                for s in spans
            )
            total = (max_end - start_time).total_seconds() * 1000
            span["duration_ms"] = max(duration_ms, int(total) + random.randint(1, 5))

    return spans


def _generate_trace(age_minutes: int = 0) -> dict:
    """Generate a complete trace with multiple spans."""
    trace_id = uuid.uuid4().hex[:32]
    start = datetime.utcnow() - timedelta(minutes=age_minutes)
    root_service = random.choice(["api-gateway", "api-gateway", "api-gateway", "order-service"])
    spans = _generate_span(trace_id, None, root_service, start)

    root_span = spans[0]
    has_error = any(s["has_error"] for s in spans)
    total_duration = root_span["duration_ms"]

    trace = {
        "trace_id": trace_id,
        "root_service": root_service,
        "root_operation": root_span["operation"],
        "start_time": start.isoformat(),
        "duration_ms": total_duration,
        "span_count": len(spans),
        "service_count": len(set(s["service"] for s in spans)),
        "has_error": has_error,
        "status": "error" if has_error else "ok",
        "spans": spans,
        "services": list(set(s["service"] for s in spans)),
    }
    return trace


# Generate seed traces
for i in range(50):
    t = _generate_trace(age_minutes=random.randint(0, 720))
    _traces[t["trace_id"]] = t


# ── Query functions ──────────────────────────────────────────────────────────

def list_traces(service: str | None = None, status: str | None = None,
                min_duration: int | None = None, limit: int = 30) -> list[dict]:
    result = list(_traces.values())
    if service:
        result = [t for t in result if service in t.get("services", [])]
    if status:
        result = [t for t in result if t.get("status") == status]
    if min_duration:
        result = [t for t in result if t.get("duration_ms", 0) >= min_duration]
    result = sorted(result, key=lambda t: t.get("start_time", ""), reverse=True)
    # Return without full spans for list view
    return [{k: v for k, v in t.items() if k != "spans"} for t in result[:limit]]


def get_trace(trace_id: str) -> dict | None:
    return _traces.get(trace_id)


def get_trace_services() -> list[str]:
    return sorted(_services)


def get_apm_summary() -> dict:
    traces = list(_traces.values())
    now = datetime.utcnow()
    last_hour = [t for t in traces if t.get("start_time", "") >= (now - timedelta(hours=1)).isoformat()]

    durations = [t.get("duration_ms", 0) for t in traces]
    error_traces = [t for t in traces if t.get("has_error")]

    # Service breakdown
    service_stats: dict[str, dict] = {}
    for t in traces:
        for span in t.get("spans", []):
            svc = span.get("service", "unknown")
            if svc not in service_stats:
                service_stats[svc] = {"requests": 0, "errors": 0, "total_duration": 0}
            service_stats[svc]["requests"] += 1
            service_stats[svc]["total_duration"] += span.get("duration_ms", 0)
            if span.get("has_error"):
                service_stats[svc]["errors"] += 1

    for svc in service_stats:
        s = service_stats[svc]
        s["avg_duration_ms"] = round(s["total_duration"] / max(s["requests"], 1), 1)
        s["error_rate"] = round(s["errors"] / max(s["requests"], 1) * 100, 1)

    return {
        "total_traces": len(traces),
        "traces_last_hour": len(last_hour),
        "error_traces": len(error_traces),
        "error_rate": round(len(error_traces) / max(len(traces), 1) * 100, 1),
        "avg_duration_ms": round(sum(durations) / max(len(durations), 1), 1),
        "p50_duration_ms": sorted(durations)[len(durations) // 2] if durations else 0,
        "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)] if durations else 0,
        "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)] if durations else 0,
        "service_stats": service_stats,
        "services": sorted(service_stats.keys()),
    }


def get_service_map() -> dict:
    """Build a service dependency map from trace data."""
    edges: dict[str, int] = {}
    nodes: dict[str, dict] = {}

    for t in _traces.values():
        spans = t.get("spans", [])
        span_map = {s["span_id"]: s for s in spans}

        for s in spans:
            svc = s["service"]
            if svc not in nodes:
                nodes[svc] = {"id": svc, "name": svc, "requests": 0, "errors": 0}
            nodes[svc]["requests"] += 1
            if s.get("has_error"):
                nodes[svc]["errors"] += 1

            parent_id = s.get("parent_span_id")
            if parent_id and parent_id in span_map:
                parent_svc = span_map[parent_id]["service"]
                if parent_svc != svc:
                    edge_key = f"{parent_svc}->{svc}"
                    edges[edge_key] = edges.get(edge_key, 0) + 1

    for n in nodes.values():
        n["error_rate"] = round(n["errors"] / max(n["requests"], 1) * 100, 1)

    return {
        "nodes": list(nodes.values()),
        "edges": [{"from": e.split("->")[0], "to": e.split("->")[1], "count": c}
                  for e, c in edges.items()],
    }
