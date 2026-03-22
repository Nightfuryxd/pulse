"""
PULSE OpenTelemetry Receiver — accepts OTLP/HTTP for metrics, traces, and logs.

This makes PULSE compatible with any app instrumented with OpenTelemetry.
Apps send data using the standard OTLP HTTP protocol, and PULSE converts it
to its native format.

Endpoints:
  POST /v1/metrics  — OTLP metrics
  POST /v1/traces   — OTLP traces (spans)
  POST /v1/logs     — OTLP logs
"""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["OpenTelemetry"])


def _ns_to_iso(ns: int) -> str:
    """Convert nanosecond timestamp to ISO format."""
    if not ns:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).isoformat()


def _hex_or(val, default=""):
    """Convert bytes to hex string, or return default."""
    if isinstance(val, (bytes, bytearray)):
        return val.hex()
    if isinstance(val, str):
        return val
    return default


def _attrs_to_dict(attributes: list) -> dict:
    """Convert OTel attribute list to flat dict."""
    result = {}
    for attr in (attributes or []):
        key = attr.get("key", "")
        value = attr.get("value", {})
        # OTel wraps values: {"stringValue": "x"}, {"intValue": 42}, etc.
        for vtype in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if vtype in value:
                result[key] = value[vtype]
                break
        else:
            result[key] = str(value)
    return result


@router.post("/v1/traces")
async def otlp_traces(request: Request):
    """
    Accept OTLP traces (JSON format).
    Converts OTel spans → PULSE spans and forwards to ingest.
    """
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400, content="Invalid JSON")

    spans_ingested = 0
    import httpx

    for resource_spans in body.get("resourceSpans", []):
        resource_attrs = _attrs_to_dict(
            resource_spans.get("resource", {}).get("attributes", [])
        )
        service_name = resource_attrs.get("service.name", "unknown")
        node_id = resource_attrs.get("host.name", resource_attrs.get("service.instance.id", service_name))

        for scope_spans in resource_spans.get("scopeSpans", []):
            for span in scope_spans.get("spans", []):
                trace_id = _hex_or(span.get("traceId"))
                span_id = _hex_or(span.get("spanId"))
                parent_id = _hex_or(span.get("parentSpanId"))

                start_ns = span.get("startTimeUnixNano", 0)
                end_ns = span.get("endTimeUnixNano", 0)
                duration_ms = (end_ns - start_ns) / 1e6 if start_ns and end_ns else 0

                status = span.get("status", {})
                status_code = status.get("code", 0)  # 0=Unset, 1=Ok, 2=Error
                status_str = "error" if status_code == 2 else "ok"

                attrs = _attrs_to_dict(span.get("attributes", []))

                pulse_span = {
                    "node_id": node_id,
                    "service": service_name,
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "parent_id": parent_id or None,
                    "operation": span.get("name", ""),
                    "ts": _ns_to_iso(start_ns),
                    "duration_ms": round(duration_ms, 2),
                    "status": status_str,
                    "tags": attrs,
                    "error": status.get("message") if status_code == 2 else None,
                }

                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "http://localhost:8000/api/ingest/spans",
                            json=pulse_span, timeout=5
                        )
                    spans_ingested += 1
                except Exception:
                    pass

    return {"accepted": spans_ingested}


@router.post("/v1/metrics")
async def otlp_metrics(request: Request):
    """
    Accept OTLP metrics (JSON format).
    Converts OTel metrics → PULSE metrics.
    """
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400, content="Invalid JSON")

    metrics_ingested = 0
    import httpx

    for resource_metrics in body.get("resourceMetrics", []):
        resource_attrs = _attrs_to_dict(
            resource_metrics.get("resource", {}).get("attributes", [])
        )
        node_id = resource_attrs.get("host.name",
                  resource_attrs.get("service.instance.id",
                  resource_attrs.get("service.name", "otel-unknown")))

        extra = {}
        for scope_metrics in resource_metrics.get("scopeMetrics", []):
            for metric in scope_metrics.get("metrics", []):
                name = metric.get("name", "")
                # Extract the latest data point value
                for data_key in ("gauge", "sum", "histogram"):
                    data = metric.get(data_key)
                    if data and data.get("dataPoints"):
                        dp = data["dataPoints"][-1]  # Latest data point
                        val = dp.get("asDouble", dp.get("asInt", 0))
                        extra[name] = val

        # Map known OTel metric names to PULSE fields
        pulse_metric = {
            "node_id": f"otel:{node_id}",
            "hostname": node_id,
            "ip": resource_attrs.get("host.ip", ""),
            "os": resource_attrs.get("os.type", ""),
            "cpu_percent": extra.get("system.cpu.utilization", extra.get("process.cpu.utilization", 0)) * 100
                           if "system.cpu.utilization" in extra or "process.cpu.utilization" in extra else 0,
            "memory_percent": extra.get("system.memory.utilization", 0) * 100
                              if "system.memory.utilization" in extra else 0,
            "memory_used_mb": extra.get("system.memory.usage", 0) / 1024 / 1024
                              if "system.memory.usage" in extra else 0,
            "disk_percent": extra.get("system.disk.utilization", 0) * 100
                            if "system.disk.utilization" in extra else 0,
            "disk_used_gb": 0,
            "net_bytes_sent": extra.get("system.network.io.transmit", 0),
            "net_bytes_recv": extra.get("system.network.io.receive", 0),
            "load_avg_1m": extra.get("system.cpu.load_average.1m", 0),
            "process_count": int(extra.get("system.processes.count", 0)),
            "extra": extra,
        }

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://localhost:8000/api/ingest/metrics",
                    json=pulse_metric, timeout=5
                )
            metrics_ingested += 1
        except Exception:
            pass

    return {"accepted": metrics_ingested}


@router.post("/v1/logs")
async def otlp_logs(request: Request):
    """
    Accept OTLP logs (JSON format).
    Converts OTel logs → PULSE logs.
    """
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400, content="Invalid JSON")

    logs_ingested = 0
    import httpx

    # OTel severity number → PULSE level
    SEV_MAP = {
        range(0, 5): "debug",
        range(5, 9): "info",
        range(9, 13): "warn",
        range(13, 17): "error",
        range(17, 25): "fatal",
    }

    def sev_to_level(sev_num: int) -> str:
        for r, level in SEV_MAP.items():
            if sev_num in r:
                return level
        return "info"

    for resource_logs in body.get("resourceLogs", []):
        resource_attrs = _attrs_to_dict(
            resource_logs.get("resource", {}).get("attributes", [])
        )
        node_id = resource_attrs.get("host.name",
                  resource_attrs.get("service.instance.id",
                  resource_attrs.get("service.name", "otel-unknown")))
        service = resource_attrs.get("service.name", "")

        for scope_logs in resource_logs.get("scopeLogs", []):
            for log_record in scope_logs.get("logRecords", []):
                body_val = log_record.get("body", {})
                message = body_val.get("stringValue", str(body_val))

                sev_num = log_record.get("severityNumber", 0)
                sev_text = log_record.get("severityText", "")

                attrs = _attrs_to_dict(log_record.get("attributes", []))

                pulse_log = {
                    "node_id": f"otel:{node_id}",
                    "service": service,
                    "ts": _ns_to_iso(log_record.get("timeUnixNano", 0)),
                    "level": sev_text.lower() if sev_text else sev_to_level(sev_num),
                    "source": attrs.get("log.file.name", attrs.get("code.filepath", "")),
                    "message": message,
                    "trace_id": _hex_or(log_record.get("traceId")),
                    "span_id": _hex_or(log_record.get("spanId")),
                    "extra": attrs,
                }

                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            "http://localhost:8000/api/ingest/logs",
                            json=pulse_log, timeout=5
                        )
                    logs_ingested += 1
                except Exception:
                    pass

    return {"accepted": logs_ingested}
