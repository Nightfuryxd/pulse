"""
PULSE Python SDK

Drop-in observability for any Python application.
Ships errors, slow queries, traces, and custom events to PULSE automatically.

Quick start:
    import pulse_sdk
    pulse_sdk.init("http://pulse-server:8000", service="my-api")

That's it. Exceptions, slow DB queries, and HTTP errors are captured automatically.

Manual:
    pulse_sdk.capture_exception(e)
    pulse_sdk.capture_event("user_signup", {"user_id": 123})
    with pulse_sdk.trace("process_order"):
        ...
"""
import os
import sys
import time
import uuid
import queue
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Any

try:
    import httpx as _httpx
    _HTTP_LIB = "httpx"
except ImportError:
    import urllib.request as _urllib
    import json as _json
    _HTTP_LIB = "urllib"

__version__ = "1.0.0"

# ── Global state ──────────────────────────────────────────────────────────────
_api_url:    str  = ""
_service:    str  = "unknown"
_node_id:    str  = os.getenv("NODE_ID", os.uname().nodename if hasattr(os, "uname") else "unknown")
_enabled:    bool = False
_log_queue:  queue.Queue = queue.Queue(maxsize=10000)
_span_queue: queue.Queue = queue.Queue(maxsize=10000)
_worker:     Optional[threading.Thread] = None
_log_batch:  list = []
_flush_interval: float = 5.0  # seconds


def init(
    api_url: str,
    service: str = "app",
    node_id: Optional[str] = None,
    flush_interval: float = 5.0,
    capture_unhandled: bool = True,
    auto_instrument: bool = True,
):
    """
    Initialize the PULSE SDK.

    Args:
        api_url:            URL of your PULSE server e.g. http://pulse:8000
        service:            Name of this service (shows in PULSE dashboard)
        node_id:            Override the node ID (default: hostname)
        flush_interval:     How often to batch-send logs (seconds)
        capture_unhandled:  Auto-capture uncaught exceptions
        auto_instrument:    Auto-patch SQLAlchemy, requests, httpx if present
    """
    global _api_url, _service, _node_id, _enabled, _flush_interval, _worker

    _api_url        = api_url.rstrip("/")
    _service        = service
    _flush_interval = flush_interval
    _enabled        = True

    if node_id:
        _node_id = node_id

    if capture_unhandled:
        _install_exception_hook()

    if auto_instrument:
        _auto_instrument()

    # Start background flush worker
    _worker = threading.Thread(target=_flush_worker, daemon=True)
    _worker.start()

    print(f"[PULSE SDK] Initialized — service={service} node={_node_id} api={_api_url}")


# ── Core capture functions ────────────────────────────────────────────────────

def capture_exception(
    exc: Optional[BaseException] = None,
    extra: dict = None,
    trace_id: Optional[str] = None,
):
    """Capture an exception and send it to PULSE."""
    if not _enabled:
        return
    if exc is None:
        exc_type, exc, tb = sys.exc_info()
        if exc is None:
            return

    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log({
        "level":    "error",
        "message":  f"{type(exc).__name__}: {exc}",
        "source":   "exception",
        "trace_id": trace_id,
        "extra":    {"traceback": tb_str[:3000], **(extra or {})},
    })

    # Also fire as an event
    _send_event({
        "node_id":  _node_id,
        "type":     "app_exception",
        "severity": "high",
        "source":   f"sdk:{_service}",
        "message":  f"[{_service}] {type(exc).__name__}: {str(exc)[:300]}",
        "data":     {"service": _service, "exception": type(exc).__name__,
                     "traceback": tb_str[:2000], **(extra or {})},
    })


def capture_event(name: str, data: dict = None, severity: str = "info"):
    """Capture a custom business or system event."""
    if not _enabled:
        return
    _send_event({
        "node_id":  _node_id,
        "type":     name,
        "severity": severity,
        "source":   f"sdk:{_service}",
        "message":  name,
        "data":     data or {},
    })


def log(entry: dict):
    """Send a structured log entry."""
    if not _enabled:
        return
    entry.setdefault("node_id", _node_id)
    entry.setdefault("service", _service)
    entry.setdefault("ts",      datetime.now(timezone.utc).isoformat())
    entry.setdefault("level",   "info")
    try:
        _log_queue.put_nowait(entry)
    except queue.Full:
        pass


def info(message: str, **kwargs):
    log({"level": "info",  "message": message, "extra": kwargs})

def warn(message: str, **kwargs):
    log({"level": "warn",  "message": message, "extra": kwargs})

def error(message: str, **kwargs):
    log({"level": "error", "message": message, "extra": kwargs})

def debug(message: str, **kwargs):
    log({"level": "debug", "message": message, "extra": kwargs})


# ── Distributed tracing ───────────────────────────────────────────────────────

class Span:
    def __init__(self, operation: str, service: str = None, parent_id: str = None, trace_id: str = None):
        self.operation  = operation
        self.service    = service or _service
        self.trace_id   = trace_id or str(uuid.uuid4())
        self.span_id    = str(uuid.uuid4())[:8]
        self.parent_id  = parent_id
        self.started_at = time.time()
        self.tags:  dict = {}
        self.error: Optional[str] = None

    def set_tag(self, key: str, value: Any):
        self.tags[key] = str(value)
        return self

    def set_error(self, exc: BaseException):
        self.error  = f"{type(exc).__name__}: {exc}"
        return self

    def finish(self, status: str = "ok"):
        duration_ms = (time.time() - self.started_at) * 1000
        try:
            _span_queue.put_nowait({
                "node_id":     _node_id,
                "service":     self.service,
                "trace_id":    self.trace_id,
                "span_id":     self.span_id,
                "parent_id":   self.parent_id,
                "operation":   self.operation,
                "ts":          datetime.now(timezone.utc).isoformat(),
                "duration_ms": round(duration_ms, 2),
                "status":      "error" if self.error else status,
                "tags":        self.tags,
                "error":       self.error,
            })
        except queue.Full:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.set_error(exc_val)
        self.finish("error" if exc_val else "ok")
        return False


@contextmanager
def trace(operation: str, service: str = None, parent_id: str = None, trace_id: str = None):
    """Context manager for creating a trace span."""
    span = Span(operation, service, parent_id, trace_id)
    try:
        yield span
        span.finish("ok")
    except Exception as e:
        span.set_error(e)
        span.finish("error")
        raise


def start_span(operation: str, **kwargs) -> Span:
    """Create a span manually (call span.finish() when done)."""
    return Span(operation, **kwargs)


# ── Auto-instrumentation ──────────────────────────────────────────────────────

def _auto_instrument():
    _patch_sqlalchemy()
    _patch_requests()
    _patch_httpx()
    _patch_logging()


def _patch_sqlalchemy():
    try:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        @event.listens_for(Engine, "before_cursor_execute")
        def before_exec(conn, cursor, statement, parameters, context, executemany):
            conn.info.setdefault("query_start_time", []).append(time.time())

        @event.listens_for(Engine, "after_cursor_execute")
        def after_exec(conn, cursor, statement, parameters, context, executemany):
            total = time.time() - conn.info["query_start_time"].pop(-1)
            duration_ms = total * 1000
            threshold   = float(os.getenv("PULSE_SLOW_QUERY_MS", "500"))
            if duration_ms >= threshold:
                with trace(f"db.query.slow", service=_service) as span:
                    span.set_tag("db.statement", statement[:200])
                    span.set_tag("db.duration_ms", f"{duration_ms:.1f}")
                    span.tags["db.slow"] = "true"
    except ImportError:
        pass
    except Exception:
        pass


def _patch_requests():
    try:
        import requests
        original_send = requests.Session.send

        def patched_send(session_self, request, **kwargs):
            start = time.time()
            resp  = original_send(session_self, request, **kwargs)
            ms    = (time.time() - start) * 1000
            if resp.status_code >= 500 or ms >= float(os.getenv("PULSE_SLOW_HTTP_MS", "2000")):
                with trace(f"http.{request.method.lower()}", service=_service) as span:
                    span.set_tag("http.url",    request.url)
                    span.set_tag("http.status", str(resp.status_code))
                    span.set_tag("http.ms",     f"{ms:.1f}")
                    if resp.status_code >= 500:
                        span.error = f"HTTP {resp.status_code}"
            return resp

        requests.Session.send = patched_send
    except ImportError:
        pass


def _patch_httpx():
    try:
        import httpx
        original_send = httpx.Client.send

        def patched_send(client_self, request, **kwargs):
            start = time.time()
            resp  = original_send(client_self, request, **kwargs)
            ms    = (time.time() - start) * 1000
            if resp.status_code >= 500 or ms >= float(os.getenv("PULSE_SLOW_HTTP_MS", "2000")):
                with trace(f"http.{request.method.lower()}", service=_service) as span:
                    span.set_tag("http.url",    str(request.url))
                    span.set_tag("http.status", str(resp.status_code))
                    span.set_tag("http.ms",     f"{ms:.1f}")
                    if resp.status_code >= 500:
                        span.error = f"HTTP {resp.status_code}"
            return resp

        httpx.Client.send = patched_send
    except ImportError:
        pass


def _patch_logging():
    """Bridge Python logging to PULSE."""
    import logging

    class PulseHandler(logging.Handler):
        def emit(self, record: logging.LogRecord):
            if not _enabled:
                return
            level_map = {
                logging.DEBUG:    "debug",
                logging.INFO:     "info",
                logging.WARNING:  "warn",
                logging.ERROR:    "error",
                logging.CRITICAL: "fatal",
            }
            log_entry = {
                "level":   level_map.get(record.levelno, "info"),
                "message": self.format(record),
                "source":  record.name,
                "extra":   {
                    "logger":   record.name,
                    "filename": record.filename,
                    "lineno":   record.lineno,
                },
            }
            if record.exc_info:
                log_entry["extra"]["traceback"] = self.formatException(record.exc_info)[:2000]
            log(log_entry)

    handler = PulseHandler()
    handler.setLevel(logging.WARNING)  # capture warnings and above
    logging.root.addHandler(handler)


def _install_exception_hook():
    original_hook = sys.excepthook

    def pulse_excepthook(exc_type, exc_value, exc_tb):
        if not issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            capture_exception(exc_value)
        original_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = pulse_excepthook


# ── Background flush worker ───────────────────────────────────────────────────

def _flush_worker():
    while True:
        time.sleep(_flush_interval)
        _flush_logs()
        _flush_spans()


def _flush_logs():
    batch = []
    try:
        while True:
            batch.append(_log_queue.get_nowait())
    except queue.Empty:
        pass
    if not batch:
        return
    try:
        _post(f"{_api_url}/api/ingest/logs/batch", {
            "node_id": _node_id,
            "service": _service,
            "logs":    batch,
        })
    except Exception:
        pass


def _flush_spans():
    batch = []
    try:
        while True:
            batch.append(_span_queue.get_nowait())
    except queue.Empty:
        pass
    for span in batch:
        try:
            _post(f"{_api_url}/api/ingest/spans", span)
        except Exception:
            pass


def _send_event(event: dict):
    try:
        t = threading.Thread(target=_post, args=(f"{_api_url}/api/ingest/events", event), daemon=True)
        t.start()
    except Exception:
        pass


def _post(url: str, data: dict):
    import json
    body = json.dumps(data).encode()
    if _HTTP_LIB == "httpx":
        _httpx.post(url, content=body, headers={"Content-Type": "application/json"}, timeout=5)
    else:
        req = _urllib.Request(url, data=body, headers={"Content-Type": "application/json"})
        _urllib.urlopen(req, timeout=5)
