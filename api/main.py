"""
PULSE API — Unified infrastructure intelligence platform.

Ingests from: local agents, SNMP, SSH agentless, app SDKs, cloud providers
Provides:    real-time monitoring, threat detection, correlation, AI RCA,
             team routing, auto-remediation, knowledge base, service topology
"""
import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, text
from pathlib import Path

load_dotenv()

from db import init_db, get_db, Node, Metric, Event, Alert, Incident, Log, ServiceEdge, Span, PlaybookRun
from detection import evaluate_metric, evaluate_event
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

app = FastAPI(title="PULSE", version="2.0.0", description="AI-powered unified infrastructure intelligence")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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

# ── In-memory caches ──────────────────────────────────────────────────────────
_recent_metrics: dict[str, list] = defaultdict(list)
_recent_events:  dict[str, list] = defaultdict(list)
_recent_logs:    dict[str, list] = defaultdict(list)
_node_cache:     dict[str, dict] = {}
_open_alerts_cache: list[dict]   = []   # for correlation


@app.on_event("startup")
async def startup():
    await init_db()
    load_from_config()
    asyncio.create_task(escalation_loop())
    print("[PULSE] API v2.0 ready — notification engine loaded")


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
    return {"status": "ok", "ts": datetime.utcnow().isoformat(), "version": "2.0"}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    p = Path(__file__).parent.parent / "dashboard" / "index.html"
    if p.exists():
        return p.read_text()
    return HTMLResponse("<h1>PULSE running — dashboard not found</h1>")


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
    _recent_metrics[payload.node_id] = _recent_metrics[payload.node_id][-60:]
    _node_cache[payload.node_id] = {"hostname": payload.hostname, "ip": payload.ip, "os": payload.os}

    # Update IP→node map for topology
    if payload.ip:
        topo.update_ip_map(payload.node_id, payload.ip)

    # Process topology connections
    if payload.connections:
        background_tasks.add_task(_process_connections, payload.node_id, payload.connections)

    background_tasks.add_task(_run_metric_detection, payload.node_id, m_dict, db)

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
    _recent_events[payload.node_id] = _recent_events[payload.node_id][-100:]

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
    _recent_logs[payload.node_id] = _recent_logs[payload.node_id][-200:]

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
    # Remove from cache
    global _open_alerts_cache
    _open_alerts_cache = [a for a in _open_alerts_cache if a.get("id") not in req.alert_ids]
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


@app.get("/api/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    nodes_count      = (await db.execute(select(func.count(Node.id)))).scalar()
    open_alerts      = (await db.execute(select(func.count(Alert.id)).where(Alert.resolved == False))).scalar()
    critical_alerts  = (await db.execute(select(func.count(Alert.id)).where(Alert.severity == "critical", Alert.resolved == False))).scalar()
    open_incidents   = (await db.execute(select(func.count(Incident.id)).where(Incident.status == "open"))).scalar()
    total_logs       = (await db.execute(select(func.count(Log.id)))).scalar()
    kb_entries       = len(get_all())

    return {
        "nodes":             nodes_count,
        "open_alerts":       open_alerts,
        "critical_alerts":   critical_alerts,
        "open_incidents":    open_incidents,
        "total_logs":        total_logs,
        "kb_entries":        kb_entries,
        "connected_clients": len(ws_manager.connections),
        "topology_edges":    len(topo.get_full_graph().get("edges", [])),
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
