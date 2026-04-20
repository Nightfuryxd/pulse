"""
PULSE API — Unified infrastructure intelligence platform.

Ingests from: local agents, SNMP, SSH agentless, app SDKs, cloud providers
Provides:    real-time monitoring, threat detection, correlation, AI RCA,
             team routing, auto-remediation, knowledge base, service topology
"""
import asyncio
import json
import os
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, BackgroundTasks, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, text
from pathlib import Path

load_dotenv()

from db import init_db, get_db, Node, Metric, Event, Alert, Incident, Log, ServiceEdge, Span, PlaybookRun
from detection import evaluate_metric, evaluate_event, get_all_rules, get_rule, create_rule, update_rule, delete_rule
from rca import analyse_incident
from router import route_incident, bridge_incident
from escalation import escalation_loop, acknowledge_incident, is_in_maintenance, add_maintenance_window, remove_maintenance_window, get_active_maintenance_windows
from correlate import correlate, build_correlation_summary
import topology as topo
from remediate import run_playbooks_for_alert
from knowledge import (
    add_entry, update_entry, delete_entry, get_all, get_entry,
    search, import_markdown, import_bulk, load_from_config
)
from synthetic import synthetic_loop, get_synthetic_results, get_synthetic_targets
from dbmonitor import dbmonitor_loop, get_db_results, get_db_targets
from anomaly import evaluate_metric as anomaly_evaluate, get_baselines, get_recent_anomalies
from otel import router as otel_router
from slo import slo_loop, get_slos, get_slo_status, get_slo_breaches, evaluate_all_slos, feed_metric as slo_feed_metric
from predict import feed_metric as predict_feed, check_predictions, get_predictions, get_forecasts, get_forecast_for_metric
from rbac import rbac_middleware, create_api_key, list_api_keys, revoke_api_key, delete_api_key, is_rbac_enabled, ROLES
from auth import (
    signup, login as auth_login, get_user, update_user, complete_onboarding,
    auth_middleware, get_current_user_from_request, AUTH_PUBLIC_PATHS, AUTH_PUBLIC_PREFIXES,
    oauth_login_or_create,
)
from oauth import (
    google_auth_url, google_exchange,
    github_auth_url, github_exchange,
    get_enabled_providers,
)
from reports import report_loop, generate_report, send_report_email, get_recent_reports, _recent_reports
from nlquery import execute_query as nl_execute_query
import jira_integration
import servicenow
import dashboards as dash_mod
import oncall as oncall_mod
import statuspage as sp_mod
import notifcenter as notif_mod
import servicecatalog as catalog_mod
import workflows as wf_mod
import logalerts as logalert_mod
import apm as apm_mod
import environments as env_mod
import auditlog as audit_mod
import metricexplorer as mexplorer_mod
import alerttemplates as atpl_mod
import warroom as warroom_mod
import usermgmt as usermgmt_mod
import billing as billing_mod

app = FastAPI(title="PULSE", version="6.0.0", description="AI-powered unified infrastructure intelligence")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Rate Limiting middleware (pure ASGI, in-memory, no external deps) ──
import time as _time

class RateLimitMiddleware:
    """
    IP-based rate limiter using a sliding-window counter stored in memory.
    - 100 req/min for general API endpoints
    - 10 req/min for auth endpoints (/api/auth/login, /api/auth/signup)
    - Skips WebSocket upgrades and the health-check endpoint (/health)
    """

    GENERAL_LIMIT = 100
    AUTH_LIMIT = 10
    WINDOW = 60  # seconds
    CLEANUP_INTERVAL = 120  # seconds — sweep stale entries every 2 min
    AUTH_PATHS = ("/api/auth/login", "/api/auth/signup")

    def __init__(self, app: "ASGIApp"):
        self.app = app
        # key → deque of request timestamps
        self._hits: dict[str, deque] = {}
        self._last_cleanup: float = _time.monotonic()

    # --- helpers -----------------------------------------------------------
    def _client_ip(self, scope) -> str:
        # Prefer X-Forwarded-For when behind a proxy
        for header_name, header_val in scope.get("headers", []):
            if header_name == b"x-forwarded-for":
                return header_val.decode().split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _cleanup(self, now: float):
        """Remove buckets whose newest entry is older than the window."""
        stale_keys = [k for k, dq in self._hits.items() if dq and dq[-1] < now - self.WINDOW]
        for k in stale_keys:
            del self._hits[k]
        # also drop empty deques
        empty_keys = [k for k, dq in self._hits.items() if not dq]
        for k in empty_keys:
            del self._hits[k]
        self._last_cleanup = now

    def _is_allowed(self, key: str, limit: int, now: float) -> tuple[bool, int, int]:
        """Returns (allowed, remaining, reset_epoch)."""
        dq = self._hits.get(key)
        if dq is None:
            dq = deque()
            self._hits[key] = dq

        # Trim timestamps outside the current window
        cutoff = now - self.WINDOW
        while dq and dq[0] < cutoff:
            dq.popleft()

        remaining = max(0, limit - len(dq))
        reset_at = int(now + self.WINDOW)

        if len(dq) >= limit:
            return False, 0, reset_at

        dq.append(now)
        remaining = max(0, limit - len(dq))
        return True, remaining, reset_at

    # --- ASGI entrypoint ---------------------------------------------------
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # Skip WebSocket and lifespan
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]

        # Skip health-check
        if path == "/health":
            await self.app(scope, receive, send)
            return

        now = _time.monotonic()

        # Periodic cleanup
        if now - self._last_cleanup > self.CLEANUP_INTERVAL:
            self._cleanup(now)

        ip = self._client_ip(scope)
        is_auth = path in self.AUTH_PATHS
        limit = self.AUTH_LIMIT if is_auth else self.GENERAL_LIMIT
        bucket_key = f"{ip}:auth" if is_auth else f"{ip}:api"

        allowed, remaining, reset_at = self._is_allowed(bucket_key, limit, now)

        rate_headers: list[tuple[bytes, bytes]] = [
            (b"x-ratelimit-limit", str(limit).encode()),
            (b"x-ratelimit-remaining", str(remaining).encode()),
            (b"x-ratelimit-reset", str(reset_at).encode()),
        ]

        if not allowed:
            # 429 Too Many Requests
            body = json.dumps({"detail": "Too many requests. Please try again later."}).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(self.WINDOW).encode()),
                ] + rate_headers,
            })
            await send({"type": "http.response.body", "body": body})
            return

        # Inject rate-limit headers into the downstream response
        async def send_with_rate_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(rate_headers)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_rate_headers)

app.add_middleware(RateLimitMiddleware)


# ── SEO / caching headers middleware (pure ASGI to avoid BaseHTTPMiddleware bugs) ──
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

class SEOHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        extra_headers: list[tuple[bytes, bytes]] = []

        if path == "/status":
            extra_headers.append((b"cache-control", b"public, max-age=60, s-maxage=120"))
        elif path.startswith("/api/status/public") or path.startswith("/api/status/overall"):
            extra_headers.append((b"cache-control", b"public, max-age=30"))
            extra_headers.append((b"x-robots-tag", b"noindex"))
        elif path.startswith("/api/"):
            extra_headers.append((b"x-robots-tag", b"noindex, nofollow"))
            extra_headers.append((b"cache-control", b"no-store, no-cache, must-revalidate"))

        if not extra_headers:
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(extra_headers)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)

app.add_middleware(SEOHeadersMiddleware)

# Wrap middleware in try/except to handle BaseHTTPMiddleware ExceptionGroup bug
# when background tasks raise after response is already sent
import functools

def _safe_middleware(fn):
    @functools.wraps(fn)
    async def wrapper(request: Request, call_next):
        try:
            return await fn(request, call_next)
        except BaseExceptionGroup:
            # Starlette BaseHTTPMiddleware + background tasks race condition — harmless
            pass
    return wrapper

app.middleware("http")(_safe_middleware(rbac_middleware))
app.middleware("http")(_safe_middleware(auth_middleware))
app.include_router(otel_router)


# ── WebSocket manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)

ws_manager = ConnectionManager()

# ── In-memory caches (bounded to prevent unbounded memory growth) ─────────────
_METRICS_MAXLEN = 60
_EVENTS_MAXLEN  = 100
_LOGS_MAXLEN    = 200
_NODE_CACHE_MAX = 10_000
_ALERTS_CACHE_MAX = 500

_recent_metrics: dict[str, deque] = defaultdict(lambda: deque(maxlen=_METRICS_MAXLEN))
_recent_events:  dict[str, deque] = defaultdict(lambda: deque(maxlen=_EVENTS_MAXLEN))
_recent_logs:    dict[str, deque] = defaultdict(lambda: deque(maxlen=_LOGS_MAXLEN))
_node_cache:     dict[str, dict]  = {}
_open_alerts_cache: deque         = deque(maxlen=_ALERTS_CACHE_MAX)


_background_tasks: list[asyncio.Task] = []


@app.on_event("startup")
async def startup():
    # Security: verify JWT_SECRET is properly configured (auth.py enforces this at import)
    from auth import JWT_SECRET
    if not JWT_SECRET or JWT_SECRET == "dev-secret-key":
        raise RuntimeError("JWT_SECRET is not configured. Refusing to start.")

    await init_db()
    load_from_config()
    _background_tasks.extend([
        asyncio.create_task(escalation_loop(), name="escalation_loop"),
        asyncio.create_task(synthetic_loop(), name="synthetic_loop"),
        asyncio.create_task(dbmonitor_loop(), name="dbmonitor_loop"),
        asyncio.create_task(slo_loop(), name="slo_loop"),
        asyncio.create_task(report_loop(), name="report_loop"),
    ])
    rbac_status = "ON" if is_rbac_enabled() else "OFF (set RBAC_ENABLED=true to enable)"
    print(f"[PULSE] API v4.0 ready — Phase 3: RBAC [{rbac_status}], SLO, predict, NL query, Jira, ServiceNow, reports")


@app.on_event("shutdown")
async def shutdown():
    """Gracefully cancel background loops on shutdown."""
    print("[PULSE] Shutting down — cancelling background tasks...")
    for task in _background_tasks:
        task.cancel()
    results = await asyncio.gather(*_background_tasks, return_exceptions=True)
    for task, result in zip(_background_tasks, results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            print(f"[PULSE] Background task {task.get_name()} exited with error: {result}")
    _background_tasks.clear()
    print("[PULSE] Shutdown complete.")


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════════════════

class MetricPayload(BaseModel):
    node_id:         str
    hostname:        Optional[str] = ""
    ip:              Optional[str] = ""
    os:              Optional[str] = ""
    ts:              Optional[str] = None
    cpu_percent:     float = 0
    memory_percent:  float = 0
    memory_used_mb:  float = 0
    disk_percent:    float = 0
    disk_used_gb:    float = 0
    net_bytes_sent:  float = 0
    net_bytes_recv:  float = 0
    load_avg_1m:     float = 0
    process_count:   int   = 0
    connections:     list  = []   # active TCP connections for topology
    extra:           dict  = {}


class EventPayload(BaseModel):
    node_id:  str
    ts:       Optional[str] = None
    type:     str
    severity: str = "info"
    source:   str = ""
    message:  str = ""
    data:     dict = {}


class LogPayload(BaseModel):
    node_id:  str
    service:  Optional[str] = ""
    ts:       Optional[str] = None
    level:    str = "info"
    source:   str = ""
    message:  str
    trace_id: Optional[str] = None
    span_id:  Optional[str] = None
    extra:    dict = {}


class LogBatchPayload(BaseModel):
    node_id: str
    service: Optional[str] = ""
    logs:    list[LogPayload]


class SpanPayload(BaseModel):
    node_id:     str
    service:     str
    trace_id:    str
    span_id:     str
    parent_id:   Optional[str] = None
    operation:   str
    ts:          Optional[str] = None
    duration_ms: float = 0
    status:      str = "ok"
    tags:        dict = {}
    error:       Optional[str] = None


class ResolveRequest(BaseModel):
    alert_ids: list[int]


class KBEntry(BaseModel):
    title:       str
    type:        str = "runbook"
    service:     Optional[str] = ""
    tags:        Optional[str] = ""
    keywords:    list[str] = []
    symptoms:    Optional[str] = ""
    resolution:  Optional[str] = ""
    description: Optional[str] = ""
    playbook_id: Optional[str] = None
    alert_rule_id: Optional[str] = None
    severity:    Optional[str] = None
    active:      bool = True


class KBMarkdownImport(BaseModel):
    content:      str
    default_type: str = "runbook"


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH + DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat(), "version": "3.0"}


DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:3000")

@app.get("/")
async def dashboard():
    return RedirectResponse(url=DASHBOARD_URL)

@app.get("/login")
async def login_page():
    return RedirectResponse(url=f"{DASHBOARD_URL}/login")

@app.get("/onboarding")
async def onboarding_page():
    return RedirectResponse(url=f"{DASHBOARD_URL}/login")


@app.post("/api/auth/login")
async def api_login(body: dict):
    email = body.get("email", "")
    password = body.get("password", "")
    if not email or not password:
        raise HTTPException(400, "Email and password required")
    try:
        result = await auth_login(email, password)
        return result
    except ValueError as e:
        raise HTTPException(401, str(e))


@app.post("/api/auth/signup")
async def api_signup(body: dict):
    email = body.get("email", "")
    password = body.get("password", "")
    name = body.get("name", "")
    org_name = body.get("org_name", "My Organization")
    if not email or not password:
        raise HTTPException(400, "Email and password required")
    try:
        result = await signup(email, password, name, org_name)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/auth/me")
async def api_auth_me(request: Request):
    user_payload = get_current_user_from_request(request)
    if not user_payload:
        raise HTTPException(401, "Not authenticated")
    user = await get_user(int(user_payload["sub"]))
    if not user:
        raise HTTPException(401, "User not found")
    return user


@app.post("/api/auth/onboarding/complete")
async def api_complete_onboarding(request: Request, body: dict):
    user_payload = get_current_user_from_request(request)
    if not user_payload:
        raise HTTPException(401, "Not authenticated")
    user_id = int(user_payload["sub"])
    # Save thresholds and channels as user settings
    updates = {"onboarded": True}
    settings = {}
    if "thresholds" in body:
        settings["thresholds"] = body["thresholds"]
    if "channels" in body:
        settings["channels"] = body["channels"]
    if settings:
        updates["settings"] = settings
    result = await update_user(user_id, updates)
    return result


@app.put("/api/auth/settings")
async def api_update_settings(request: Request, body: dict):
    user_payload = get_current_user_from_request(request)
    if not user_payload:
        raise HTTPException(401, "Not authenticated")
    user_id = int(user_payload["sub"])
    result = await update_user(user_id, body)
    return result


# ── OAuth routes ─────────────────────────────────────────────────────────────

@app.get("/api/auth/oauth/providers")
async def api_oauth_providers():
    """Return which OAuth providers are configured."""
    return {"providers": get_enabled_providers()}


@app.get("/api/auth/oauth/google")
async def api_oauth_google():
    try:
        url = google_auth_url()
        return {"url": url}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/auth/oauth/google/callback")
async def api_oauth_google_callback(code: str = Query(...), state: str = Query(...)):
    try:
        profile = await google_exchange(code, state)
        result = await oauth_login_or_create(
            email=profile["email"],
            name=profile["name"],
            avatar_url=profile["avatar_url"],
            provider=profile["provider"],
            provider_id=profile["provider_id"],
        )
        # Redirect to frontend with token in URL fragment (never sent to server)
        from urllib.parse import urlencode
        frontend_base = os.getenv("FRONTEND_URL", "http://localhost:3000")
        params = urlencode({"token": result["token"]})
        return RedirectResponse(url=f"{frontend_base}/login?oauth=success&{params}")
    except Exception as e:
        frontend_base = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(url=f"{frontend_base}/login?oauth=error&message={str(e)}")


@app.get("/api/auth/oauth/github")
async def api_oauth_github():
    try:
        url = github_auth_url()
        return {"url": url}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/auth/oauth/github/callback")
async def api_oauth_github_callback(code: str = Query(...), state: str = Query(...)):
    try:
        profile = await github_exchange(code, state)
        result = await oauth_login_or_create(
            email=profile["email"],
            name=profile["name"],
            avatar_url=profile["avatar_url"],
            provider=profile["provider"],
            provider_id=profile["provider_id"],
        )
        frontend_base = os.getenv("FRONTEND_URL", "http://localhost:3000")
        params = urlencode({"token": result["token"]})
        return RedirectResponse(url=f"{frontend_base}/login?oauth=success&{params}")
    except Exception as e:
        frontend_base = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(url=f"{frontend_base}/login?oauth=error&message={str(e)}")


@app.get("/agent/collector.py", response_class=PlainTextResponse)
async def serve_collector():
    p = Path(__file__).parent.parent / "agent" / "collector.py"
    if p.exists():
        return PlainTextResponse(p.read_text(), media_type="text/plain")
    raise HTTPException(404, "collector.py not found")


@app.get("/install.sh", response_class=PlainTextResponse)
async def serve_install_sh():
    p = Path(__file__).parent.parent / "install.sh"
    if p.exists():
        return PlainTextResponse(p.read_text(), media_type="text/plain")
    raise HTTPException(404, "install.sh not found")


@app.get("/install.ps1", response_class=PlainTextResponse)
async def serve_install_ps1():
    p = Path(__file__).parent.parent / "install.ps1"
    if p.exists():
        return PlainTextResponse(p.read_text(), media_type="text/plain")
    raise HTTPException(404, "install.ps1 not found")


# ══════════════════════════════════════════════════════════════════════════════
# INGEST: METRICS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/ingest/metrics")
async def ingest_metrics(
    payload: MetricPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    ts = datetime.utcnow()

    # Upsert node
    node = (await db.execute(select(Node).where(Node.id == payload.node_id))).scalar_one_or_none()
    if not node:
        node = Node(id=payload.node_id, hostname=payload.hostname or payload.node_id,
                    ip=payload.ip, os=payload.os)
        db.add(node)
    else:
        node.last_seen = ts
        if payload.hostname: node.hostname = payload.hostname
        if payload.ip:       node.ip       = payload.ip

    metric = Metric(
        node_id=payload.node_id, ts=ts,
        cpu_percent=payload.cpu_percent, memory_percent=payload.memory_percent,
        memory_used_mb=payload.memory_used_mb, disk_percent=payload.disk_percent,
        disk_used_gb=payload.disk_used_gb, net_bytes_sent=payload.net_bytes_sent,
        net_bytes_recv=payload.net_bytes_recv, load_avg_1m=payload.load_avg_1m,
        process_count=payload.process_count, extra=payload.extra,
    )
    db.add(metric)
    await db.commit()

    m_dict = payload.model_dump()
    _recent_metrics[payload.node_id].append(m_dict)
    # Evict oldest node_cache entries if over limit
    if len(_node_cache) >= _NODE_CACHE_MAX and payload.node_id not in _node_cache:
        _node_cache.pop(next(iter(_node_cache)), None)
    _node_cache[payload.node_id] = {"hostname": payload.hostname, "ip": payload.ip, "os": payload.os}

    # Update IP→node map for topology
    if payload.ip:
        topo.update_ip_map(payload.node_id, payload.ip)

    # Process topology connections
    if payload.connections:
        background_tasks.add_task(_process_connections, payload.node_id, payload.connections)

    background_tasks.add_task(_run_metric_detection, payload.node_id, m_dict, db)

    # Anomaly detection — feeds into baseline and checks for deviations
    anomaly_events = anomaly_evaluate(payload.node_id, m_dict)
    for ae in anomaly_events:
        background_tasks.add_task(_run_event_detection, payload.node_id, ae, db)

    # Predictive alerting — feed data and check for threshold breach forecasts
    predict_feed(payload.node_id, m_dict)
    pred_alerts = check_predictions(payload.node_id, m_dict)
    for pa in pred_alerts:
        pred_event = {
            "node_id": payload.node_id, "type": "predictive_alert",
            "severity": pa["severity"], "source": "predictor",
            "message": f"Predicted {pa['metric']} will reach {pa['predicted_value']}{pa['unit']} "
                       f"(threshold {pa['threshold']}{pa['unit']}) in ~{pa['time_to_breach_minutes']:.0f}m",
            "data": pa,
        }
        background_tasks.add_task(_run_event_detection, payload.node_id, pred_event, db)

    # SLO tracking — feed metric data
    slo_feed_metric(payload.node_id, m_dict)

    await ws_manager.broadcast({"type": "metric", "node_id": payload.node_id, "data": m_dict})
    return {"accepted": True}


# ══════════════════════════════════════════════════════════════════════════════
# INGEST: EVENTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/ingest/events")
async def ingest_events(
    payload: EventPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    ts = datetime.fromisoformat(payload.ts) if payload.ts else datetime.utcnow()
    event = Event(
        node_id=payload.node_id, ts=ts, type=payload.type,
        severity=payload.severity, source=payload.source,
        message=payload.message, data=payload.data,
    )
    db.add(event)
    await db.commit()

    e_dict = payload.model_dump()
    _recent_events[payload.node_id].append(e_dict)

    background_tasks.add_task(_run_event_detection, payload.node_id, e_dict, db)
    await ws_manager.broadcast({"type": "event", "node_id": payload.node_id, "data": e_dict})
    return {"accepted": True}


# ══════════════════════════════════════════════════════════════════════════════
# INGEST: LOGS (centralized log aggregation)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/ingest/logs")
async def ingest_log(
    payload: LogPayload,
    db: AsyncSession = Depends(get_db),
):
    ts  = datetime.fromisoformat(payload.ts) if payload.ts else datetime.utcnow()
    log = Log(
        node_id=payload.node_id, service=payload.service or "", ts=ts,
        level=payload.level, source=payload.source, message=payload.message,
        trace_id=payload.trace_id, span_id=payload.span_id, extra=payload.extra,
    )
    db.add(log)
    await db.commit()

    l_dict = payload.model_dump()
    _recent_logs[payload.node_id].append(l_dict)

    if payload.level in ("error", "fatal", "critical"):
        await ws_manager.broadcast({"type": "log_error", "node_id": payload.node_id, "data": l_dict})

    return {"accepted": True}


@app.post("/api/ingest/logs/batch")
async def ingest_log_batch(
    payload: LogBatchPayload,
    db: AsyncSession = Depends(get_db),
):
    """Bulk log ingest — used by agents and SDKs to send many lines at once."""
    count = 0
    for entry in payload.logs:
        ts  = datetime.fromisoformat(entry.ts) if entry.ts else datetime.utcnow()
        log = Log(
            node_id=payload.node_id,
            service=entry.service or payload.service or "",
            ts=ts, level=entry.level, source=entry.source, message=entry.message,
            trace_id=entry.trace_id, span_id=entry.span_id, extra=entry.extra,
        )
        db.add(log)
        count += 1
    await db.commit()
    return {"accepted": count}


# ══════════════════════════════════════════════════════════════════════════════
# INGEST: SPANS (distributed tracing from app SDKs)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/ingest/spans")
async def ingest_span(
    payload: SpanPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    ts   = datetime.fromisoformat(payload.ts) if payload.ts else datetime.utcnow()
    span = Span(
        node_id=payload.node_id, service=payload.service,
        trace_id=payload.trace_id, span_id=payload.span_id, parent_id=payload.parent_id,
        operation=payload.operation, ts=ts, duration_ms=payload.duration_ms,
        status=payload.status, tags=payload.tags, error=payload.error,
    )
    db.add(span)
    await db.commit()

    # Auto-detect slow operations as events
    slow_threshold_ms = int(os.getenv("SLOW_SPAN_MS", "2000"))
    if payload.duration_ms >= slow_threshold_ms or payload.status == "error":
        severity = "high" if payload.status == "error" else "medium"
        ev = EventPayload(
            node_id=payload.node_id,
            type="slow_operation" if payload.duration_ms >= slow_threshold_ms else "app_error",
            severity=severity,
            source=f"sdk:{payload.service}",
            message=f"{payload.operation} took {payload.duration_ms:.0f}ms" + (f" | error: {payload.error}" if payload.error else ""),
            data={"service": payload.service, "operation": payload.operation,
                  "duration_ms": payload.duration_ms, "trace_id": payload.trace_id},
        )
        background_tasks.add_task(ingest_events, ev, BackgroundTasks(), db)

    return {"accepted": True}


# ══════════════════════════════════════════════════════════════════════════════
# TOPOLOGY
# ══════════════════════════════════════════════════════════════════════════════

async def _process_connections(node_id: str, connections: list[dict]):
    """Process reported TCP connections and update topology graph."""
    for conn in connections:
        topo.record_connection(
            src_node=node_id,
            src_port=conn.get("lport", 0),
            dst_ip=conn.get("raddr", ""),
            dst_port=conn.get("rport", 0),
            bytes_sent=conn.get("bytes", 0),
        )


@app.get("/api/topology")
async def get_topology():
    """Full service dependency graph."""
    return topo.get_full_graph()


@app.get("/api/topology/{node_id}/blast-radius")
async def blast_radius(node_id: str):
    return topo.get_blast_radius(node_id)


@app.get("/api/topology/{node_id}/dependencies")
async def get_dependencies(node_id: str):
    return {
        "node_id":     node_id,
        "depends_on":  topo.get_dependencies(node_id),
        "depended_by": topo.get_dependents(node_id),
    }


# ══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/kb")
async def list_kb(q: Optional[str] = None, type: Optional[str] = None):
    if q:
        results = search(q, top_k=20, entry_type=type or "")
    else:
        results = get_all()
        if type:
            results = [e for e in results if e.get("type") == type]
    return {"entries": results, "total": len(results)}


@app.post("/api/kb/entries")
async def create_kb_entry(entry: KBEntry):
    saved = add_entry(entry.model_dump())
    return saved


@app.put("/api/kb/entries/{entry_id}")
async def update_kb_entry(entry_id: str, updates: dict):
    result = update_entry(entry_id, updates)
    if not result:
        raise HTTPException(404, "Entry not found")
    return result


@app.delete("/api/kb/entries/{entry_id}")
async def delete_kb_entry(entry_id: str):
    if not delete_entry(entry_id):
        raise HTTPException(404, "Entry not found")
    return {"deleted": True}


@app.post("/api/kb/import/markdown")
async def import_kb_markdown(payload: KBMarkdownImport):
    entries = import_markdown(payload.content, payload.default_type)
    return {"imported": len(entries), "entries": entries}


@app.post("/api/kb/import/bulk")
async def import_kb_bulk(payload: dict):
    entries_data = payload.get("entries", [])
    entries = import_bulk(entries_data)
    return {"imported": len(entries)}


@app.get("/api/kb/search")
async def search_kb(q: str, type: Optional[str] = None, top_k: int = 10):
    return {"results": search(q, top_k=top_k, entry_type=type or "")}


# ══════════════════════════════════════════════════════════════════════════════
# LOGS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/logs")
async def list_logs(
    node_id:  Optional[str] = None,
    service:  Optional[str] = None,
    level:    Optional[str] = None,
    q:        Optional[str] = None,
    trace_id: Optional[str] = None,
    limit:    int = 200,
    db:       AsyncSession = Depends(get_db),
):
    stmt = select(Log).order_by(Log.ts.desc()).limit(limit)
    if node_id:   stmt = stmt.where(Log.node_id == node_id)
    if service:   stmt = stmt.where(Log.service == service)
    if level:     stmt = stmt.where(Log.level == level)
    if trace_id:  stmt = stmt.where(Log.trace_id == trace_id)
    if q:
        stmt = stmt.where(Log.message.ilike(f"%{q}%"))

    logs = (await db.execute(stmt)).scalars().all()
    return {"logs": [
        {"id": l.id, "node_id": l.node_id, "service": l.service,
         "ts": l.ts.isoformat(), "level": l.level, "source": l.source,
         "message": l.message, "trace_id": l.trace_id, "extra": l.extra}
        for l in logs
    ]}


@app.get("/api/logs/trace/{trace_id}")
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Get all logs and spans for a distributed trace."""
    logs  = (await db.execute(
        select(Log).where(Log.trace_id == trace_id).order_by(Log.ts.asc())
    )).scalars().all()
    spans = (await db.execute(
        select(Span).where(Span.trace_id == trace_id).order_by(Span.ts.asc())
    )).scalars().all()
    return {
        "trace_id": trace_id,
        "logs":  [{"ts": l.ts.isoformat(), "level": l.level, "service": l.service, "message": l.message} for l in logs],
        "spans": [{"ts": s.ts.isoformat(), "service": s.service, "operation": s.operation,
                   "duration_ms": s.duration_ms, "status": s.status, "error": s.error} for s in spans],
    }


# ══════════════════════════════════════════════════════════════════════════════
# DETECTION BACKGROUND TASKS
# ══════════════════════════════════════════════════════════════════════════════

async def _run_metric_detection(node_id: str, metric: dict, db: AsyncSession):
    triggered = evaluate_metric(node_id, metric)
    for a in triggered:
        await _save_and_escalate_alert(node_id, a, db)


async def _run_event_detection(node_id: str, event: dict, db: AsyncSession):
    triggered = evaluate_event(node_id, event)
    for a in triggered:
        await _save_and_escalate_alert(node_id, a, db)


async def _save_and_escalate_alert(node_id: str, alert_data: dict, db: AsyncSession):
    # Correlate with open alerts
    open_alert_dicts = list(_open_alerts_cache[-100:])
    corr = correlate(
        {**alert_data, "id": None, "ts": datetime.utcnow()},
        open_alert_dicts
    )

    alert = Alert(
        node_id=alert_data["node_id"],
        rule_id=alert_data["rule_id"],
        rule_name=alert_data["rule_name"],
        severity=alert_data["severity"],
        category=alert_data["category"],
        message=alert_data["message"],
        group_id=corr.get("group_id"),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    alert_dict = {
        "id": alert.id, "node_id": alert.node_id,
        "rule_id": alert.rule_id, "rule_name": alert.rule_name,
        "severity": alert.severity, "category": alert.category,
        "message": alert.message, "ts": alert.ts.isoformat(),
        "group_id": corr.get("group_id"),
    }
    _open_alerts_cache.append(alert_dict)

    await ws_manager.broadcast({"type": "alert", "node_id": node_id, "data": {
        **alert_dict, "correlation": corr
    }})

    if alert.severity in ("critical", "high"):
        asyncio.create_task(_create_incident(node_id, alert.id, alert_data, corr))

    # Auto-remediation
    node_info = _node_cache.get(node_id, {})
    asyncio.create_task(_run_remediation(alert_data, node_info.get("ip", "")))


async def _run_remediation(alert_data: dict, node_ip: str):
    results = await run_playbooks_for_alert(alert_data, node_ip)
    if results:
        print(f"[Remediate] Ran {len(results)} playbook(s) for {alert_data.get('rule_id','?')}: "
              f"{[r.get('status') for r in results]}")


async def _create_incident(node_id: str, alert_id: int, alert_data: dict, corr: dict):
    async with get_db().__aiter__().__anext__() as db:
        try:
            node_info    = _node_cache.get(node_id, {})
            recent_m     = _recent_metrics.get(node_id, [])[-20:]
            recent_e     = _recent_events.get(node_id, [])[-20:]
            tech_stack   = os.getenv("TECH_STACK", "").split(",") or None

            # Get topology context
            topology_ctx = {
                "dependencies": topo.get_dependencies(node_id),
                "blast_radius": topo.get_blast_radius(node_id),
            }

            # Build correlation summary if multi-node
            correlation_summary = None
            if corr.get("correlated_with"):
                # Fetch correlated alerts from cache
                corr_alert_ids = corr.get("correlated_with", [])
                corr_alerts    = [a for a in _open_alerts_cache if a.get("id") in corr_alert_ids]
                all_alerts     = [alert_data] + corr_alerts
                affected_nodes = corr.get("affected_nodes", [node_id])
                correlation_summary = build_correlation_summary(
                    corr.get("group_id",""), all_alerts,
                    [_node_cache.get(n, {"node_id": n}) for n in affected_nodes]
                )

            print(f"[PULSE] RCA for {node_id}: {alert_data['rule_name']}"
                  + (f" [{corr.get('pattern','')}]" if corr.get("pattern") else ""))

            rca = await analyse_incident(
                node_id, node_info, [alert_data], recent_m, recent_e,
                tech_stack, correlation_summary, topology_ctx
            )

            # Auto-run linked playbook from RCA
            linked_pb = rca.get("linked_playbook")
            remediation_log = {}
            if linked_pb:
                from remediate import load_playbooks, execute_playbook
                playbooks = load_playbooks()
                pb = next((p for p in playbooks if p.get("id") == linked_pb), None)
                if pb:
                    remediation_log = await execute_playbook(pb, alert_data, _node_cache.get(node_id, {}).get("ip",""))

            teams_routing = route_incident([alert_data["category"]], rca)
            affected_nodes = corr.get("affected_nodes", [node_id])

            incident = Incident(
                node_id=node_id,
                title=alert_data["rule_name"],
                severity=alert_data["severity"],
                status="open",
                alert_ids=[alert_id] + (corr.get("correlated_with") or []),
                node_ids=affected_nodes,
                rca=rca,
                routed_teams=[t["id"] for t in teams_routing.get("owners", [])],
                correlation=corr,
                remediation=remediation_log,
            )
            db.add(incident)
            await db.commit()
            await db.refresh(incident)

            inc_dict = {
                "id": incident.id, "node_id": node_id,
                "title": incident.title, "severity": incident.severity,
                "ts": incident.ts.isoformat(),
            }
            bridge = await bridge_incident(inc_dict, teams_routing, rca)
            incident.bridge = bridge
            await db.commit()

            await ws_manager.broadcast({"type": "incident", "node_id": node_id, "data": {
                "id": incident.id, "title": incident.title, "severity": incident.severity,
                "rca": rca, "routed_teams": incident.routed_teams, "bridge": bridge,
                "affected_nodes": affected_nodes, "pattern": corr.get("pattern"),
            }})

            print(f"[PULSE] Incident #{incident.id} | teams={incident.routed_teams} "
                  f"| bridge={bridge.get('bridged')} | nodes={affected_nodes}")

        except Exception as e:
            print(f"[PULSE] Incident creation failed: {e}")
            import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# QUERY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/nodes")
async def list_nodes(db: AsyncSession = Depends(get_db)):
    nodes = (await db.execute(select(Node).order_by(Node.last_seen.desc()))).scalars().all()
    result = []
    for n in nodes:
        latest = _recent_metrics.get(n.id, [{}])[-1]
        result.append({
            "id": n.id, "hostname": n.hostname, "ip": n.ip, "os": n.os,
            "status": n.status, "last_seen": n.last_seen.isoformat(),
            "latest_metric": latest,
            "dependencies": len(topo.get_dependencies(n.id)),
            "dependents":   len(topo.get_dependents(n.id)),
        })
    return {"nodes": result}


@app.get("/api/nodes/{node_id}/metrics")
async def get_metrics(node_id: str, minutes: int = 60, db: AsyncSession = Depends(get_db)):
    since = datetime.utcnow() - timedelta(minutes=minutes)
    rows  = (await db.execute(
        select(Metric).where(Metric.node_id == node_id, Metric.ts >= since).order_by(Metric.ts.asc())
    )).scalars().all()
    return {"node_id": node_id, "metrics": [
        {"ts": r.ts.isoformat(), "cpu": r.cpu_percent, "memory": r.memory_percent,
         "disk": r.disk_percent, "load": r.load_avg_1m,
         "net_sent": r.net_bytes_sent, "net_recv": r.net_bytes_recv}
        for r in rows
    ]}


@app.get("/api/alerts")
async def list_alerts(
    node_id:  Optional[str] = None,
    severity: Optional[str] = None,
    resolved: bool = False,
    group_id: Optional[str] = None,
    limit:    int = 100,
    db:       AsyncSession = Depends(get_db),
):
    q = select(Alert).where(Alert.resolved == resolved).order_by(Alert.ts.desc()).limit(limit)
    if node_id:   q = q.where(Alert.node_id == node_id)
    if severity:  q = q.where(Alert.severity == severity)
    if group_id:  q = q.where(Alert.group_id == group_id)
    alerts = (await db.execute(q)).scalars().all()
    return {"alerts": [
        {"id": a.id, "node_id": a.node_id, "rule_name": a.rule_name,
         "severity": a.severity, "category": a.category, "message": a.message,
         "ts": a.ts.isoformat(), "resolved": a.resolved, "group_id": a.group_id}
        for a in alerts
    ]}


@app.post("/api/alerts/resolve")
async def resolve_alerts(req: ResolveRequest, db: AsyncSession = Depends(get_db)):
    for aid in req.alert_ids:
        alert = (await db.execute(select(Alert).where(Alert.id == aid))).scalar_one_or_none()
        if alert:
            alert.resolved    = True
            alert.resolved_at = datetime.utcnow()
    await db.commit()
    # Remove resolved alerts from cache (filter in-place for bounded deque)
    resolved_ids = set(req.alert_ids)
    remaining = [a for a in _open_alerts_cache if a.get("id") not in resolved_ids]
    _open_alerts_cache.clear()
    _open_alerts_cache.extend(remaining)
    return {"resolved": len(req.alert_ids)}


@app.get("/api/incidents")
async def list_incidents(
    status: Optional[str] = None,
    limit:  int = 50,
    db:     AsyncSession = Depends(get_db),
):
    q = select(Incident).order_by(Incident.ts.desc()).limit(limit)
    if status: q = q.where(Incident.status == status)
    incidents = (await db.execute(q)).scalars().all()
    return {"incidents": [
        {"id": i.id, "node_id": i.node_id, "title": i.title, "severity": i.severity,
         "status": i.status, "ts": i.ts.isoformat(), "rca": i.rca,
         "routed_teams": i.routed_teams, "bridge": i.bridge,
         "node_ids": i.node_ids, "correlation": i.correlation, "remediation": i.remediation}
        for i in incidents
    ]}


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: int, db: AsyncSession = Depends(get_db)):
    i = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not i:
        raise HTTPException(404, "Incident not found")
    return {"id": i.id, "node_id": i.node_id, "title": i.title, "severity": i.severity,
            "status": i.status, "ts": i.ts.isoformat(), "alert_ids": i.alert_ids,
            "rca": i.rca, "routed_teams": i.routed_teams, "bridge": i.bridge,
            "node_ids": i.node_ids, "correlation": i.correlation, "remediation": i.remediation}


@app.post("/api/incidents/{incident_id}/status")
async def update_incident_status(incident_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    i = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not i:
        raise HTTPException(404, "Incident not found")
    i.status = body.get("status", i.status)
    if i.status == "resolved":
        i.resolved_at = datetime.utcnow()
    await db.commit()
    return {"id": i.id, "status": i.status}


@app.post("/api/incidents/{incident_id}/acknowledge")
async def ack_incident(incident_id: int, db: AsyncSession = Depends(get_db)):
    """Acknowledge an incident — stops escalation."""
    i = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not i:
        raise HTTPException(404, "Incident not found")
    i.status = "acknowledged"
    acknowledge_incident(incident_id)
    await db.commit()
    return {"id": i.id, "status": "acknowledged", "escalation_stopped": True}


# ══════════════════════════════════════════════════════════════════════════════
# MAINTENANCE WINDOWS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/maintenance")
async def list_maintenance_windows():
    """List all active maintenance windows."""
    return {"windows": get_active_maintenance_windows()}


@app.post("/api/maintenance")
async def create_maintenance_window(body: dict):
    """Create a runtime maintenance window.
    Body: {id, description, start, end, targets: [...], suppress_categories: [...]}
    """
    required = ["id", "start", "end"]
    for field in required:
        if field not in body:
            raise HTTPException(400, f"Missing required field: {field}")
    add_maintenance_window(body)
    return {"status": "created", "window": body}


@app.delete("/api/maintenance/{window_id}")
async def delete_maintenance_window(window_id: str):
    """Remove a runtime maintenance window."""
    remove_maintenance_window(window_id)
    return {"status": "removed", "id": window_id}


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION PROVIDERS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/notifications/providers")
async def list_notification_providers():
    """List all available notification providers and their config status."""
    import os
    providers = {
        "slack":       {"configured": bool(os.getenv("SLACK_BOT_TOKEN"))},
        "teams":       {"configured": bool(os.getenv("TEAMS_WEBHOOK_URL")), "note": "Per-team webhooks also supported in teams.yaml"},
        "discord":     {"configured": True, "note": "Per-team webhook URLs in teams.yaml"},
        "telegram":    {"configured": bool(os.getenv("TELEGRAM_BOT_TOKEN"))},
        "google_chat": {"configured": True, "note": "Per-team webhook URLs in teams.yaml"},
        "zoom":        {"configured": True, "note": "Per-team webhook URLs in teams.yaml"},
        "pagerduty":   {"configured": bool(os.getenv("PAGERDUTY_API_KEY")), "note": "Per-team routing keys also supported"},
        "opsgenie":    {"configured": bool(os.getenv("OPSGENIE_API_KEY"))},
        "email":       {"configured": bool(os.getenv("SMTP_HOST"))},
        "sms":         {"configured": bool(os.getenv("TWILIO_ACCOUNT_SID"))},
        "webhook":     {"configured": True, "note": "Per-team webhook URLs in teams.yaml"},
        "whatsapp":    {"configured": bool(os.getenv("TWILIO_ACCOUNT_SID")), "note": "Via Twilio — uses same TWILIO_* creds as SMS"},
        "whatsapp_meta": {"configured": bool(os.getenv("WHATSAPP_TOKEN")), "note": "Via Meta Cloud API — needs WHATSAPP_TOKEN + WHATSAPP_PHONE_ID"},
    }
    return {"providers": providers}


@app.post("/api/notifications/test")
async def test_notification(body: dict):
    """Send a test notification. Body: {provider, target, message?}"""
    from notifications import PROVIDER_MAP, format_incident_payload
    provider = body.get("provider")
    target = body.get("target")
    if not provider or provider not in PROVIDER_MAP:
        raise HTTPException(400, f"Unknown provider. Available: {list(PROVIDER_MAP.keys())}")
    if not target and provider not in ("opsgenie",):
        raise HTTPException(400, "Missing 'target' (channel, webhook URL, email, phone, etc.)")

    test_payload = format_incident_payload(
        {"id": 0, "node_id": "test-node", "title": "PULSE Test Notification",
         "severity": "low", "ts": datetime.utcnow().isoformat()},
        {"root_cause": "This is a test notification from PULSE.",
         "confidence": 1.0, "blast_radius": "None",
         "recommended_actions": {"immediate": ["No action needed — this is a test."]},
         "stack_specific_advice": "N/A"},
        {"owners": [{"name": "Test Team"}], "observers": []},
    )
    test_payload["title"] = body.get("message", "PULSE Test Notification")

    result = await PROVIDER_MAP[provider](target, test_payload)
    return result


@app.post("/api/incidents/{incident_id}/bridge")
async def manual_bridge(incident_id: int, db: AsyncSession = Depends(get_db)):
    i = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not i:
        raise HTTPException(404, "Incident not found")
    teams_routing = route_incident([], i.rca)
    inc_dict = {"id": i.id, "node_id": i.node_id, "title": i.title,
                "severity": i.severity, "ts": i.ts.isoformat()}
    bridge = await bridge_incident(inc_dict, teams_routing, i.rca)
    i.bridge = bridge
    await db.commit()
    return bridge


@app.get("/api/events")
async def list_events(
    node_id: Optional[str] = None,
    type:    Optional[str] = None,
    limit:   int = 100,
    db:      AsyncSession = Depends(get_db),
):
    q = select(Event).order_by(Event.ts.desc()).limit(limit)
    if node_id: q = q.where(Event.node_id == node_id)
    if type:    q = q.where(Event.type == type)
    events = (await db.execute(q)).scalars().all()
    return {"events": [
        {"id": e.id, "node_id": e.node_id, "ts": e.ts.isoformat(),
         "type": e.type, "severity": e.severity, "message": e.message, "data": e.data}
        for e in events
    ]}


# ══════════════════════════════════════════════════════════════════════════════
# SYNTHETIC MONITORING
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/synthetic")
async def list_synthetic():
    """Get current synthetic monitoring probe results."""
    return {"targets": get_synthetic_targets(), "results": get_synthetic_results()}


@app.get("/api/synthetic/results")
async def synthetic_results():
    """Latest probe results only."""
    return {"results": get_synthetic_results()}


# ══════════════════════════════════════════════════════════════════════════════
# ALERT RULES (CRUD)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/rules")
async def list_rules():
    """List all alert rules."""
    return {"rules": get_all_rules()}


@app.get("/api/rules/{rule_id}")
async def get_rule_endpoint(rule_id: str):
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    return rule


@app.post("/api/rules")
async def create_rule_endpoint(body: dict):
    """Create a new alert rule."""
    try:
        return create_rule(body)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/rules/{rule_id}")
async def update_rule_endpoint(rule_id: str, body: dict):
    """Update an alert rule."""
    result = update_rule(rule_id, body)
    if not result:
        raise HTTPException(404, "Rule not found")
    return result


@app.delete("/api/rules/{rule_id}")
async def delete_rule_endpoint(rule_id: str):
    """Delete an alert rule."""
    if not delete_rule(rule_id):
        raise HTTPException(404, "Rule not found")
    return {"deleted": True, "id": rule_id}


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE MONITORING
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/databases")
async def list_databases():
    """Get database monitoring results."""
    return {"targets": get_db_targets(), "results": get_db_results()}


@app.get("/api/databases/results")
async def database_results():
    """Latest database metrics only."""
    return {"results": get_db_results()}


# ══════════════════════════════════════════════════════════════════════════════
# ANOMALY DETECTION
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/anomalies")
async def list_anomalies(node_id: Optional[str] = None, limit: int = 50):
    """Get recent anomalies detected by baseline analysis."""
    return {"anomalies": get_recent_anomalies(node_id, limit)}


@app.get("/api/anomalies/baselines")
async def list_baselines(node_id: Optional[str] = None):
    """Get learned metric baselines per node."""
    return {"baselines": get_baselines(node_id)}


# ══════════════════════════════════════════════════════════════════════════════
# SLO / SLA TRACKING
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/slos")
async def list_slos():
    """Get all SLO definitions and their current status."""
    return {"slos": get_slos(), "status": get_slo_status()}


@app.get("/api/slos/status")
async def slo_status():
    """Get current compliance status for all SLOs."""
    return {"status": evaluate_all_slos()}


@app.get("/api/slos/breaches")
async def slo_breaches(limit: int = 50):
    """Get recent SLO breaches."""
    return {"breaches": get_slo_breaches(limit)}


# ══════════════════════════════════════════════════════════════════════════════
# PREDICTIVE ALERTING
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/predictions")
async def list_predictions(node_id: Optional[str] = None, limit: int = 50):
    """Get recent predictive alerts."""
    return {"predictions": get_predictions(node_id, limit)}


@app.get("/api/forecasts")
async def list_forecasts(node_id: Optional[str] = None):
    """Get current metric forecasts per node."""
    return {"forecasts": get_forecasts(node_id)}


@app.get("/api/forecasts/{node_id}/{metric_name}")
async def get_forecast_detail(node_id: str, metric_name: str, horizon: int = 60):
    """Get detailed forecast for a specific node+metric."""
    return get_forecast_for_metric(node_id, metric_name, horizon)


# ══════════════════════════════════════════════════════════════════════════════
# NATURAL LANGUAGE QUERYING
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/query")
async def natural_language_query(body: dict, db: AsyncSession = Depends(get_db)):
    """Ask PULSE a question in natural language."""
    question = body.get("question", body.get("q", ""))
    if not question:
        raise HTTPException(400, "Missing 'question' field")
    return await nl_execute_query(question, db)


# ══════════════════════════════════════════════════════════════════════════════
# RBAC — API KEY MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/admin/rbac")
async def rbac_status_endpoint():
    """Check RBAC status and list roles."""
    return {"enabled": is_rbac_enabled(), "roles": ROLES}


@app.post("/api/admin/keys")
async def create_key(body: dict):
    """Create a new API key. Requires admin role when RBAC is enabled."""
    name = body.get("name", "")
    role = body.get("role", "viewer")
    if not name:
        raise HTTPException(400, "Missing 'name' field")
    try:
        result = await create_api_key(name, role)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/keys")
async def list_keys():
    """List all API keys (without secrets)."""
    return {"keys": await list_api_keys()}


@app.post("/api/admin/keys/{key_id}/revoke")
async def revoke_key(key_id: int):
    """Revoke an API key."""
    if await revoke_api_key(key_id):
        return {"revoked": True, "id": key_id}
    raise HTTPException(404, "Key not found")


@app.delete("/api/admin/keys/{key_id}")
async def delete_key(key_id: int):
    """Permanently delete an API key."""
    if await delete_api_key(key_id):
        return {"deleted": True, "id": key_id}
    raise HTTPException(404, "Key not found")


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/reports")
async def list_reports_endpoint(limit: int = 10):
    """List recent generated reports."""
    return {"reports": get_recent_reports(limit)}


@app.post("/api/reports/generate")
async def generate_report_endpoint(body: dict, db: AsyncSession = Depends(get_db)):
    """Generate a report on demand. Body: {period: "daily"|"weekly"|"monthly"}"""
    period = body.get("period", "daily")
    report = await generate_report(period, db)
    return report


@app.get("/api/reports/{index}/html", response_class=HTMLResponse)
async def get_report_html(index: int):
    """Get a report's HTML content by index."""
    reports = get_recent_reports(100)
    if index < 0 or index >= len(_recent_reports):
        raise HTTPException(404, "Report not found")
    return HTMLResponse(_recent_reports[index].get("html", "<h1>No HTML</h1>"))


@app.post("/api/reports/email")
async def email_report(body: dict, db: AsyncSession = Depends(get_db)):
    """Generate and email a report. Body: {period, recipients?: [...]}"""
    period = body.get("period", "daily")
    recipients = body.get("recipients", [])
    report = await generate_report(period, db)
    result = send_report_email(report, recipients if recipients else None)
    return result


@app.get("/api/export/dashboard", response_class=HTMLResponse)
async def export_dashboard(db: AsyncSession = Depends(get_db)):
    """Export current dashboard state as a printable HTML report for PDF generation."""
    # Query current stats
    node_count = await db.scalar(select(func.count()).select_from(Node))
    alert_count = await db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "open"))
    incident_count = await db.scalar(select(func.count()).select_from(Incident).where(Incident.status == "open"))

    # Recent alerts
    recent_alerts_q = await db.execute(
        select(Alert).where(Alert.status == "open").order_by(desc(Alert.created_at)).limit(20)
    )
    recent_alerts = recent_alerts_q.scalars().all()

    # Build HTML report
    alert_rows = ""
    for a in recent_alerts:
        alert_rows += f"<tr><td>{a.severity}</td><td>{a.rule_name}</td><td>{a.node}</td><td>{a.message}</td><td>{a.created_at}</td></tr>"

    html = f"""<!DOCTYPE html>
<html><head><title>PULSE Dashboard Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; color: #1a1a2e; }}
h1 {{ color: #6366f1; border-bottom: 2px solid #6366f1; padding-bottom: 8px; }}
h2 {{ color: #334155; margin-top: 32px; }}
.stats {{ display: flex; gap: 24px; margin: 24px 0; }}
.stat {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; flex: 1; text-align: center; }}
.stat .value {{ font-size: 32px; font-weight: 800; color: #6366f1; }}
.stat .label {{ font-size: 13px; color: #64748b; margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }}
th {{ background: #f1f5f9; padding: 10px 12px; text-align: left; font-weight: 600; border-bottom: 2px solid #e2e8f0; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #f1f5f9; }}
tr:hover {{ background: #f8fafc; }}
.footer {{ margin-top: 48px; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
@media print {{ body {{ margin: 20px; }} }}
</style></head><body>
<h1>PULSE Dashboard Report</h1>
<p style="color:#64748b">Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
<div class="stats">
<div class="stat"><div class="value">{node_count}</div><div class="label">Nodes</div></div>
<div class="stat"><div class="value">{alert_count}</div><div class="label">Open Alerts</div></div>
<div class="stat"><div class="value">{incident_count}</div><div class="label">Open Incidents</div></div>
</div>
<h2>Open Alerts</h2>
<table><tr><th>Severity</th><th>Rule</th><th>Node</th><th>Message</th><th>Created</th></tr>
{alert_rows}
</table>
<div class="footer">PULSE Infrastructure Intelligence Platform — Exported Report</div>
</body></html>"""
    return HTMLResponse(content=html)


# ══════════════════════════════════════════════════════════════════════════════
# JIRA INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/integrations/jira/status")
async def jira_status():
    """Check Jira integration status."""
    return {"configured": jira_integration.is_configured(), "url": jira_integration.JIRA_URL or None}


@app.post("/api/integrations/jira/tickets")
async def create_jira_ticket(body: dict):
    """Create a Jira ticket from an incident. Body: {incident: {...}, rca?: {...}}"""
    return await jira_integration.create_ticket(body.get("incident", body), body.get("rca"))


@app.post("/api/integrations/jira/webhook")
async def jira_webhook(payload: dict):
    """Receive Jira webhook events for bidirectional sync."""
    return await jira_integration.handle_jira_webhook(payload)


@app.get("/api/integrations/jira/tickets/{jira_key}")
async def get_jira_ticket(jira_key: str):
    """Fetch a Jira ticket."""
    return await jira_integration.get_ticket(jira_key)


@app.get("/api/integrations/jira/search")
async def search_jira(jql: Optional[str] = None):
    """Search Jira tickets. Uses default JQL if none provided."""
    return await jira_integration.search_tickets(jql or f"project = {jira_integration.JIRA_PROJECT} AND labels = pulse ORDER BY created DESC")


# ══════════════════════════════════════════════════════════════════════════════
# SERVICENOW INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/integrations/servicenow/status")
async def servicenow_status():
    """Check ServiceNow integration status."""
    return {"configured": servicenow.is_configured(), "instance": servicenow.SNOW_INSTANCE or None}


@app.post("/api/integrations/servicenow/incidents")
async def create_snow_incident(body: dict):
    """Create a ServiceNow incident. Body: {incident: {...}, rca?: {...}}"""
    return await servicenow.create_incident(body.get("incident", body), body.get("rca"))


@app.post("/api/integrations/servicenow/webhook")
async def servicenow_webhook(payload: dict):
    """Receive ServiceNow webhook events."""
    return await servicenow.handle_webhook(payload)


@app.get("/api/integrations/servicenow/incidents/{sys_id}")
async def get_snow_incident(sys_id: str):
    """Fetch a ServiceNow incident."""
    return await servicenow.get_incident_by_sysid(sys_id)


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATIONS OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/integrations")
async def list_integrations():
    """List all available integrations and their status."""
    return {
        "integrations": {
            "jira":       {"configured": jira_integration.is_configured(), "type": "ITSM"},
            "servicenow": {"configured": servicenow.is_configured(), "type": "ITSM"},
            "rbac":       {"enabled": is_rbac_enabled(), "type": "Security"},
        }
    }


@app.get("/api/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    nodes_count      = (await db.execute(select(func.count(Node.id)))).scalar()
    open_alerts      = (await db.execute(select(func.count(Alert.id)).where(Alert.resolved == False))).scalar()
    critical_alerts  = (await db.execute(select(func.count(Alert.id)).where(Alert.severity == "critical", Alert.resolved == False))).scalar()
    open_incidents   = (await db.execute(select(func.count(Incident.id)).where(Incident.status == "open"))).scalar()
    total_logs       = (await db.execute(select(func.count(Log.id)))).scalar()
    kb_entries       = len(get_all())

    synthetic_up = sum(1 for r in get_synthetic_results() if r.get("status") == "up")
    synthetic_total = len(get_synthetic_results())
    anomaly_count = len(get_recent_anomalies(limit=100))

    slo_status_all = get_slo_status()
    slos_met = sum(1 for v in slo_status_all.values() if v.get("status") == "met")
    slos_total = len(slo_status_all)
    predictions_count = len(get_predictions(limit=100))

    return {
        "nodes":             nodes_count,
        "open_alerts":       open_alerts,
        "critical_alerts":   critical_alerts,
        "open_incidents":    open_incidents,
        "total_logs":        total_logs,
        "kb_entries":        kb_entries,
        "connected_clients": len(ws_manager.connections),
        "topology_edges":    len(topo.get_full_graph().get("edges", [])),
        "synthetic_up":      synthetic_up,
        "synthetic_total":   synthetic_total,
        "monitored_dbs":     len(get_db_results()),
        "anomalies_24h":     anomaly_count,
        "slos_met":          slos_met,
        "slos_total":        slos_total,
        "predictions_24h":   predictions_count,
        "rbac_enabled":      is_rbac_enabled(),
        "jira_connected":    jira_integration.is_configured(),
        "servicenow_connected": servicenow.is_configured(),
        "version":           "4.0.0",
    }


# ══════════════════════════════════════════════════════════════════════════════
# PLAYBOOK RUNS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/playbooks")
async def list_playbooks():
    from remediate import load_playbooks
    return {"playbooks": load_playbooks()}


@app.post("/api/playbooks/{playbook_id}/run")
async def run_playbook(playbook_id: str, body: dict):
    from remediate import load_playbooks, execute_playbook
    playbooks = load_playbooks()
    pb = next((p for p in playbooks if p.get("id") == playbook_id), None)
    if not pb:
        raise HTTPException(404, "Playbook not found")
    alert_data = body.get("alert", {"node_id": body.get("node_id",""), "rule_id":"manual", "rule_name":"Manual Run", "severity":"info", "message":""})
    node_ip    = body.get("node_ip", "")
    result     = await execute_playbook(pb, alert_data, node_ip)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM DASHBOARDS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/dashboards")
async def api_list_dashboards():
    return dash_mod.list_dashboards()

@app.get("/api/dashboards/widget-types")
async def api_widget_types():
    return dash_mod.get_widget_types()

@app.get("/api/dashboards/{dashboard_id}")
async def api_get_dashboard(dashboard_id: str):
    d = dash_mod.get_dashboard(dashboard_id)
    if not d:
        raise HTTPException(404, "Dashboard not found")
    return d

@app.post("/api/dashboards")
async def api_create_dashboard(body: dict):
    return dash_mod.create_dashboard(body, body.get("owner", "anonymous"))

@app.put("/api/dashboards/{dashboard_id}")
async def api_update_dashboard(dashboard_id: str, body: dict):
    d = dash_mod.update_dashboard(dashboard_id, body)
    if not d:
        raise HTTPException(404, "Dashboard not found")
    return d

@app.delete("/api/dashboards/{dashboard_id}")
async def api_delete_dashboard(dashboard_id: str):
    if not dash_mod.delete_dashboard(dashboard_id):
        raise HTTPException(400, "Cannot delete (not found or is default)")
    return {"ok": True}

@app.post("/api/dashboards/{dashboard_id}/duplicate")
async def api_duplicate_dashboard(dashboard_id: str):
    d = dash_mod.duplicate_dashboard(dashboard_id)
    if not d:
        raise HTTPException(404, "Dashboard not found")
    return d


# ══════════════════════════════════════════════════════════════════════════════
# ON-CALL SCHEDULING
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/oncall/current")
async def api_oncall_current(schedule_id: str | None = None):
    return oncall_mod.get_current_oncall(schedule_id) or {}

@app.get("/api/oncall/summary")
async def api_oncall_summary():
    return oncall_mod.get_oncall_summary()

@app.get("/api/oncall/schedules")
async def api_oncall_schedules():
    return oncall_mod.list_schedules()

@app.get("/api/oncall/schedules/{schedule_id}")
async def api_oncall_schedule(schedule_id: str):
    s = oncall_mod.get_schedule(schedule_id)
    if not s:
        raise HTTPException(404, "Schedule not found")
    return s

@app.post("/api/oncall/schedules")
async def api_create_schedule(body: dict):
    return oncall_mod.create_schedule(body)

@app.put("/api/oncall/schedules/{schedule_id}")
async def api_update_schedule(schedule_id: str, body: dict):
    s = oncall_mod.update_schedule(schedule_id, body)
    if not s:
        raise HTTPException(404, "Schedule not found")
    return s

@app.delete("/api/oncall/schedules/{schedule_id}")
async def api_delete_schedule(schedule_id: str):
    if not oncall_mod.delete_schedule(schedule_id):
        raise HTTPException(404, "Schedule not found")
    return {"ok": True}

@app.get("/api/oncall/overrides")
async def api_oncall_overrides(schedule_id: str | None = None):
    return oncall_mod.list_overrides(schedule_id)

@app.post("/api/oncall/overrides")
async def api_create_override(body: dict):
    return oncall_mod.create_override(body)

@app.delete("/api/oncall/overrides/{override_id}")
async def api_delete_override(override_id: str):
    if not oncall_mod.delete_override(override_id):
        raise HTTPException(404, "Override not found")
    return {"ok": True}

@app.get("/api/oncall/policies")
async def api_oncall_policies():
    return oncall_mod.list_policies()

@app.post("/api/oncall/policies")
async def api_create_policy(body: dict):
    return oncall_mod.create_policy(body)

@app.put("/api/oncall/policies/{policy_id}")
async def api_update_policy(policy_id: str, body: dict):
    p = oncall_mod.update_policy(policy_id, body)
    if not p:
        raise HTTPException(404, "Policy not found")
    return p

@app.get("/api/oncall/events")
async def api_oncall_events(limit: int = 50):
    return oncall_mod.get_oncall_events(limit)


# ══════════════════════════════════════════════════════════════════════════════
# STATUS PAGE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/status/services")
async def api_status_services():
    return sp_mod.list_services()

@app.get("/api/status/services/{service_id}")
async def api_status_service(service_id: str):
    s = sp_mod.get_service(service_id)
    if not s:
        raise HTTPException(404, "Service not found")
    return s

@app.post("/api/status/services")
async def api_create_service(body: dict):
    return sp_mod.create_service(body)

@app.put("/api/status/services/{service_id}")
async def api_update_service(service_id: str, body: dict):
    s = sp_mod.update_service(service_id, body)
    if not s:
        raise HTTPException(404, "Service not found")
    return s

@app.delete("/api/status/services/{service_id}")
async def api_delete_service(service_id: str):
    if not sp_mod.delete_service(service_id):
        raise HTTPException(404, "Service not found")
    return {"ok": True}

@app.get("/api/status/incidents")
async def api_status_incidents():
    return sp_mod.list_status_incidents()

@app.post("/api/status/incidents")
async def api_create_status_incident(body: dict):
    return sp_mod.create_status_incident(body)

@app.put("/api/status/incidents/{incident_id}")
async def api_update_status_incident(incident_id: str, body: dict):
    i = sp_mod.update_status_incident(incident_id, body)
    if not i:
        raise HTTPException(404, "Incident not found")
    return i

@app.get("/api/status/public")
async def api_public_status():
    return sp_mod.get_public_status_data()

@app.get("/api/status/overall")
async def api_status_overall():
    return sp_mod.get_overall_status()

@app.get("/status", response_class=HTMLResponse)
async def public_status_page():
    """Public-facing status page — no auth required."""
    data = sp_mod.get_public_status_data()
    status_colors = {
        "operational": "#34d399", "degraded": "#fbbf24",
        "partial_outage": "#fb923c", "major_outage": "#f87171",
        "maintenance": "#6366f1",
    }
    overall = data["overall"]
    color = status_colors.get(overall["status"], "#34d399")

    services_html = ""
    for group_name, svcs in data["groups"].items():
        services_html += f'<div class="sp-group"><div class="sp-group-name">{group_name}</div>'
        for svc in svcs:
            sc = status_colors.get(svc["status"], "#34d399")
            label = svc["status"].replace("_", " ").title()
            uptime = svc.get("uptime_90d", 100)
            services_html += f'''<div class="sp-svc">
              <div class="sp-svc-left"><span class="sp-dot" style="background:{sc};box-shadow:0 0 8px {sc}"></span>{svc["name"]}</div>
              <div class="sp-svc-right"><span class="sp-uptime">{uptime}%</span><span class="sp-status" style="color:{sc}">{label}</span></div>
            </div>'''
        services_html += '</div>'

    incidents_html = ""
    for inc in data["incidents"][:5]:
        inc_status = inc["status"].replace("_", " ").title()
        incidents_html += f'<div class="sp-inc"><div class="sp-inc-title">{inc["title"]}<span class="sp-inc-badge">{inc_status}</span></div>'
        for upd in inc.get("updates", [])[-3:]:
            incidents_html += f'<div class="sp-inc-update"><span class="sp-inc-ts">{upd["ts"][:16]}</span> {upd["message"]}</div>'
        incidents_html += '</div>'

    seo_meta = sp_mod.build_seo_meta_tags(overall)
    all_services = [svc for svcs in data["groups"].values() for svc in svcs]
    structured_data = sp_mod.build_structured_data(overall, all_services)

    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
{seo_meta}
{structured_data}
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#09090b;color:#fafafa;font-family:'Inter',system-ui,sans-serif;min-height:100vh}}
.sp-wrap{{max-width:720px;margin:0 auto;padding:40px 20px}}
.sp-header{{text-align:center;margin-bottom:40px}}
.sp-logo{{font-size:24px;font-weight:900;letter-spacing:6px;margin-bottom:20px;background:linear-gradient(135deg,#fafafa,#a1a1aa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sp-overall{{display:inline-flex;align-items:center;gap:12px;padding:14px 28px;border-radius:14px;font-size:16px;font-weight:700;border:1px solid rgba(255,255,255,0.06)}}
.sp-overall-dot{{width:12px;height:12px;border-radius:50%}}
.sp-group{{margin-bottom:24px}}
.sp-group-name{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#52525b;margin-bottom:10px;padding:0 4px}}
.sp-svc{{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;background:#111113;border:1px solid rgba(255,255,255,0.06);border-radius:10px;margin-bottom:6px;font-size:14px;font-weight:500}}
.sp-svc-left{{display:flex;align-items:center;gap:12px}}
.sp-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.sp-svc-right{{display:flex;align-items:center;gap:16px}}
.sp-uptime{{font-size:12px;color:#a1a1aa;font-weight:600}}
.sp-status{{font-size:12px;font-weight:700;text-transform:capitalize}}
.sp-section-title{{font-size:18px;font-weight:800;margin:40px 0 16px;padding-top:24px;border-top:1px solid rgba(255,255,255,0.06)}}
.sp-inc{{background:#111113;border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:18px;margin-bottom:10px}}
.sp-inc-title{{font-size:14px;font-weight:700;display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.sp-inc-badge{{font-size:10px;font-weight:700;text-transform:uppercase;padding:3px 8px;border-radius:6px;background:rgba(255,255,255,0.05);color:#a1a1aa}}
.sp-inc-update{{font-size:12px;color:#a1a1aa;padding:6px 0;border-top:1px solid rgba(255,255,255,0.04);line-height:1.5}}
.sp-inc-ts{{color:#52525b;font-family:monospace;font-size:11px;margin-right:8px}}
.sp-footer{{text-align:center;margin-top:48px;font-size:11px;color:#52525b}}
.sp-footer a{{color:#6366f1;text-decoration:none}}
</style></head><body>
<div class="sp-wrap">
  <div class="sp-header">
    <div class="sp-logo">PULSE</div>
    <div class="sp-overall" style="background:rgba({",".join(str(int(color[i:i+2],16)) for i in (1,3,5))},0.08)">
      <div class="sp-overall-dot" style="background:{color};box-shadow:0 0 12px {color}"></div>
      {overall["message"]}
    </div>
  </div>
  {services_html}
  <div class="sp-section-title">Recent Incidents</div>
  {incidents_html if incidents_html else '<div style="color:#52525b;padding:20px;text-align:center">No recent incidents</div>'}
  <div class="sp-footer">Powered by <a href="/">PULSE</a> &mdash; Updated {data["generated_at"][:16]} UTC</div>
</div></body></html>'''


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION CENTER
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/notifications")
async def api_notifications(limit: int = 50, ntype: str | None = None, unread_only: bool = False):
    return notif_mod.list_notifications(limit, ntype, unread_only)

@app.get("/api/notifications/summary")
async def api_notif_summary():
    return notif_mod.get_summary()

@app.put("/api/notifications/{notif_id}/read")
async def api_notif_read(notif_id: str):
    notif_mod.mark_read(notif_id)
    return {"ok": True}

@app.post("/api/notifications/read-all")
async def api_notif_read_all():
    count = notif_mod.mark_all_read()
    return {"ok": True, "marked": count}

@app.delete("/api/notifications/{notif_id}")
async def api_notif_delete(notif_id: str):
    notif_mod.delete_notification(notif_id)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# SERVICE CATALOG
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/catalog/services")
async def api_catalog_services(tier: str | None = None, team: str | None = None, tag: str | None = None):
    return catalog_mod.list_services(tier, team, tag)

@app.get("/api/catalog/services/{service_id}")
async def api_catalog_service(service_id: str):
    s = catalog_mod.get_service(service_id)
    if not s:
        raise HTTPException(404, "Service not found")
    return s

@app.post("/api/catalog/services")
async def api_catalog_create_service(body: dict):
    return catalog_mod.create_service(body)

@app.put("/api/catalog/services/{service_id}")
async def api_catalog_update_service(service_id: str, body: dict):
    s = catalog_mod.update_service(service_id, body)
    if not s:
        raise HTTPException(404, "Service not found")
    return s

@app.delete("/api/catalog/services/{service_id}")
async def api_catalog_delete_service(service_id: str):
    if not catalog_mod.delete_service(service_id):
        raise HTTPException(404, "Service not found")
    return {"ok": True}

@app.get("/api/catalog/teams")
async def api_catalog_teams():
    return catalog_mod.list_teams()

@app.get("/api/catalog/teams/{team_id}")
async def api_catalog_team(team_id: str):
    t = catalog_mod.get_team(team_id)
    if not t:
        raise HTTPException(404, "Team not found")
    return t

@app.post("/api/catalog/teams")
async def api_catalog_create_team(body: dict):
    return catalog_mod.create_team(body)

@app.get("/api/catalog/graph")
async def api_catalog_graph():
    return catalog_mod.get_dependency_graph()

@app.get("/api/catalog/summary")
async def api_catalog_summary():
    return catalog_mod.get_catalog_summary()


# ══════════════════════════════════════════════════════════════════════════════
# ALERTING WORKFLOWS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/workflows")
async def api_workflows():
    return wf_mod.list_workflows()

@app.get("/api/workflows/components")
async def api_workflow_components():
    return wf_mod.get_components()

@app.get("/api/workflows/{wf_id}")
async def api_workflow(wf_id: str):
    w = wf_mod.get_workflow(wf_id)
    if not w:
        raise HTTPException(404, "Workflow not found")
    return w

@app.post("/api/workflows")
async def api_create_workflow(body: dict):
    return wf_mod.create_workflow(body)

@app.put("/api/workflows/{wf_id}")
async def api_update_workflow(wf_id: str, body: dict):
    w = wf_mod.update_workflow(wf_id, body)
    if not w:
        raise HTTPException(404, "Workflow not found")
    return w

@app.delete("/api/workflows/{wf_id}")
async def api_delete_workflow(wf_id: str):
    if not wf_mod.delete_workflow(wf_id):
        raise HTTPException(404, "Workflow not found")
    return {"ok": True}

@app.post("/api/workflows/{wf_id}/toggle")
async def api_toggle_workflow(wf_id: str):
    w = wf_mod.toggle_workflow(wf_id)
    if not w:
        raise HTTPException(404, "Workflow not found")
    return w

@app.get("/api/workflows/{wf_id}/runs")
async def api_workflow_runs(wf_id: str, limit: int = 20):
    return wf_mod.get_workflow_runs(wf_id, limit)


# ══════════════════════════════════════════════════════════════════════════════
# LOG-BASED ALERTING
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/log-alerts/rules")
async def api_log_alert_rules(rule_type: str | None = None, severity: str | None = None):
    return logalert_mod.list_rules(rule_type, severity)

@app.get("/api/log-alerts/rules/types")
async def api_log_alert_rule_types():
    return logalert_mod.get_rule_types()

@app.get("/api/log-alerts/summary")
async def api_log_alert_summary():
    return logalert_mod.get_summary()

@app.get("/api/log-alerts/alerts")
async def api_log_alerts_fired(limit: int = 50):
    return logalert_mod.get_log_alerts(limit)

@app.get("/api/log-alerts/rules/{rule_id}")
async def api_get_log_rule(rule_id: str):
    r = logalert_mod.get_rule(rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    return r

@app.post("/api/log-alerts/rules")
async def api_create_log_rule(request: Request):
    body = await request.json()
    return logalert_mod.create_rule(body)

@app.put("/api/log-alerts/rules/{rule_id}")
async def api_update_log_rule(rule_id: str, request: Request):
    body = await request.json()
    r = logalert_mod.update_rule(rule_id, body)
    if not r:
        raise HTTPException(404, "Rule not found")
    return r

@app.delete("/api/log-alerts/rules/{rule_id}")
async def api_delete_log_rule(rule_id: str):
    if not logalert_mod.delete_rule(rule_id):
        raise HTTPException(404, "Rule not found")
    return {"ok": True}

@app.post("/api/log-alerts/rules/{rule_id}/toggle")
async def api_toggle_log_rule(rule_id: str):
    r = logalert_mod.toggle_rule(rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    return r

@app.post("/api/log-alerts/rules/{rule_id}/test")
async def api_test_log_rule(rule_id: str, request: Request):
    body = await request.json()
    return logalert_mod.test_rule(rule_id, body.get("sample", ""))

@app.get("/api/log-alerts/rules/{rule_id}/hits")
async def api_log_rule_hits(rule_id: str):
    return logalert_mod.get_rule_hits(rule_id)


# ══════════════════════════════════════════════════════════════════════════════
# APM / DISTRIBUTED TRACING
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/apm/traces")
async def api_list_traces(service: str | None = None, status: str | None = None,
                          min_duration: int | None = None, limit: int = 30):
    return apm_mod.list_traces(service, status, min_duration, limit)

@app.get("/api/apm/traces/{trace_id}")
async def api_get_trace(trace_id: str):
    t = apm_mod.get_trace(trace_id)
    if not t:
        raise HTTPException(404, "Trace not found")
    return t

@app.get("/api/apm/summary")
async def api_apm_summary():
    return apm_mod.get_apm_summary()

@app.get("/api/apm/services")
async def api_apm_services():
    return apm_mod.get_trace_services()

@app.get("/api/apm/service-map")
async def api_apm_service_map():
    return apm_mod.get_service_map()


# ══════════════════════════════════════════════════════════════════════════════
# MULTI-ENVIRONMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/environments")
async def api_list_environments():
    return env_mod.list_environments()

@app.get("/api/environments/summary")
async def api_env_summary():
    return env_mod.get_summary()

@app.get("/api/environments/default")
async def api_default_env():
    e = env_mod.get_default_environment()
    if not e:
        raise HTTPException(404, "No default environment")
    return e

@app.get("/api/environments/{env_id}")
async def api_get_environment(env_id: str):
    e = env_mod.get_environment(env_id)
    if not e:
        raise HTTPException(404, "Environment not found")
    return e

@app.post("/api/environments")
async def api_create_environment(request: Request):
    body = await request.json()
    return env_mod.create_environment(body)

@app.put("/api/environments/{env_id}")
async def api_update_environment(env_id: str, request: Request):
    body = await request.json()
    e = env_mod.update_environment(env_id, body)
    if not e:
        raise HTTPException(404, "Environment not found")
    return e

@app.delete("/api/environments/{env_id}")
async def api_delete_environment(env_id: str):
    if not env_mod.delete_environment(env_id):
        raise HTTPException(400, "Cannot delete (default or not found)")
    return {"ok": True}

@app.post("/api/environments/{env_id}/set-default")
async def api_set_default_env(env_id: str):
    e = env_mod.set_default(env_id)
    if not e:
        raise HTTPException(404, "Environment not found")
    return e


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/audit")
async def api_audit_list(category: str | None = None, action: str | None = None,
                         actor: str | None = None, limit: int = 50, offset: int = 0):
    return audit_mod.list_entries(category, action, actor, limit, offset)

@app.get("/api/audit/summary")
async def api_audit_summary():
    return audit_mod.get_summary()

@app.get("/api/audit/{entry_id}")
async def api_audit_entry(entry_id: str):
    e = audit_mod.get_entry(entry_id)
    if not e:
        raise HTTPException(404, "Entry not found")
    return e


# ══════════════════════════════════════════════════════════════════════════════
# METRIC EXPLORER
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/explorer/config")
async def api_explorer_config():
    return mexplorer_mod.get_explorer_config()

@app.get("/api/explorer/query")
async def api_explorer_query(metric: str, time_range: str = "1h", func: str = "avg",
                              group_by: str | None = None):
    return mexplorer_mod.query(metric, time_range, func, group_by)

@app.get("/api/explorer/metrics")
async def api_explorer_metrics():
    return mexplorer_mod.get_available_metrics()

@app.get("/api/explorer/functions")
async def api_explorer_functions():
    return mexplorer_mod.get_available_functions()


# ══════════════════════════════════════════════════════════════════════════════
# ALERT TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/alert-templates")
async def api_list_alert_templates(category: str | None = None):
    return atpl_mod.list_packs(category)

@app.get("/api/alert-templates/summary")
async def api_alert_templates_summary():
    return atpl_mod.get_summary()

@app.get("/api/alert-templates/{pack_id}")
async def api_get_alert_template(pack_id: str):
    p = atpl_mod.get_pack(pack_id)
    if not p:
        raise HTTPException(404, "Pack not found")
    return p

@app.post("/api/alert-templates/{pack_id}/import")
async def api_import_alert_template(pack_id: str):
    result = atpl_mod.import_pack(pack_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.get("/api/alert-templates/imported/rules")
async def api_imported_rules():
    return atpl_mod.get_imported_rules()


# ══════════════════════════════════════════════════════════════════════════════
# WAR ROOM / INCIDENT TIMELINE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/warroom")
async def api_list_war_rooms(status: str | None = None):
    return warroom_mod.list_war_rooms(status)

@app.get("/api/warroom/summary")
async def api_warroom_summary():
    return warroom_mod.get_summary()

@app.get("/api/warroom/{room_id}")
async def api_get_war_room(room_id: str):
    r = warroom_mod.get_war_room(room_id)
    if not r:
        raise HTTPException(404, "War room not found")
    return r

@app.post("/api/warroom")
async def api_create_war_room(request: Request):
    body = await request.json()
    return warroom_mod.create_war_room(body)

@app.post("/api/warroom/{room_id}/events")
async def api_add_warroom_event(room_id: str, request: Request):
    body = await request.json()
    evt = warroom_mod.add_timeline_event(room_id, body)
    if not evt:
        raise HTTPException(404, "War room not found")
    return evt

@app.post("/api/warroom/{room_id}/resolve")
async def api_resolve_warroom(room_id: str, request: Request):
    body = await request.json()
    r = warroom_mod.resolve_war_room(room_id, body.get("notes", ""))
    if not r:
        raise HTTPException(404, "War room not found")
    return r

@app.post("/api/warroom/{room_id}/responders")
async def api_add_warroom_responder(room_id: str, request: Request):
    body = await request.json()
    resp = warroom_mod.add_responder(room_id, body)
    if not resp:
        raise HTTPException(404, "War room not found")
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# USER & TEAM MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/users")
async def api_list_users(role: str | None = None, status: str | None = None):
    return usermgmt_mod.list_users(role, status)

@app.get("/api/users/summary")
async def api_users_summary():
    return usermgmt_mod.get_summary()

@app.get("/api/users/roles")
async def api_user_roles():
    return usermgmt_mod.get_roles()

@app.get("/api/users/invites")
async def api_user_invites():
    return usermgmt_mod.get_invites()

@app.get("/api/users/{user_id}")
async def api_get_managed_user(user_id: str):
    u = usermgmt_mod.get_user(user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return u

@app.post("/api/users/invite")
async def api_invite_user(request: Request):
    body = await request.json()
    return usermgmt_mod.invite_user(body)

@app.put("/api/users/{user_id}")
async def api_update_managed_user(user_id: str, request: Request):
    body = await request.json()
    u = usermgmt_mod.update_user(user_id, body)
    if not u:
        raise HTTPException(404, "User not found")
    return u

@app.post("/api/users/{user_id}/deactivate")
async def api_deactivate_user(user_id: str):
    u = usermgmt_mod.deactivate_user(user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return u

@app.post("/api/users/{user_id}/reactivate")
async def api_reactivate_user(user_id: str):
    u = usermgmt_mod.reactivate_user(user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return u

@app.post("/api/users/{user_id}/role")
async def api_change_user_role(user_id: str, request: Request):
    body = await request.json()
    u = usermgmt_mod.change_role(user_id, body.get("role", "viewer"))
    if not u:
        raise HTTPException(404, "User not found or invalid role")
    return u


# ══════════════════════════════════════════════════════════════════════════════
# BILLING & USAGE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/billing/plan")
async def api_current_plan():
    return billing_mod.get_current_plan()

@app.get("/api/billing/plans")
async def api_all_plans():
    return billing_mod.get_plans()

@app.get("/api/billing/usage")
async def api_usage_summary():
    return billing_mod.get_usage_summary()

@app.get("/api/billing/usage/daily")
async def api_daily_usage(days: int = 30):
    return billing_mod.get_daily_usage(days)

@app.get("/api/billing/usage/breakdown")
async def api_usage_breakdown():
    return billing_mod.get_usage_breakdown()

@app.post("/api/billing/change-plan")
async def api_change_plan(request: Request):
    body = await request.json()
    result = billing_mod.change_plan(body.get("plan_id", ""))
    if not result:
        raise HTTPException(400, "Invalid plan")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET
# ══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({"type": "connected", "ts": datetime.utcnow().isoformat()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
