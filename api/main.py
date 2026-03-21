"""
PULSE API — Core ingestion, detection, RCA, and incident management.
"""
import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pathlib import Path

load_dotenv()

from db import init_db, get_db, Node, Metric, Event, Alert, Incident
from detection import evaluate_metric, evaluate_event
from rca import analyse_incident
from router import route_incident, bridge_incident

app = FastAPI(title="PULSE", version="1.0.0", description="AI-powered incident intelligence platform")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── WebSocket connection manager ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
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

# ── In-memory recent data cache (reduces DB reads for real-time) ──────────────
_recent_metrics: dict[str, list] = defaultdict(list)  # node_id -> last 60 readings
_recent_events:  dict[str, list] = defaultdict(list)
_node_cache:     dict[str, dict] = {}


@app.on_event("startup")
async def startup():
    await init_db()
    print("[PULSE] API ready")


# ── Models ────────────────────────────────────────────────────────────────────
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
    extra:           dict  = {}


class EventPayload(BaseModel):
    node_id:  str
    ts:       Optional[str] = None
    type:     str
    severity: str = "info"
    source:   str = ""
    message:  str = ""
    data:     dict = {}


class ResolveRequest(BaseModel):
    alert_ids: list[int]


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    p = Path(__file__).parent.parent / "dashboard" / "index.html"
    if p.exists():
        return p.read_text()
    return HTMLResponse("<h1>PULSE running — dashboard not found</h1>")


# ── Agent download (used by install.sh / install.ps1) ─────────────────────────
@app.get("/agent/collector.py", response_class=HTMLResponse)
async def serve_collector():
    from fastapi.responses import PlainTextResponse
    p = Path(__file__).parent.parent / "agent" / "collector.py"
    if p.exists():
        return PlainTextResponse(p.read_text(), media_type="text/plain")
    raise HTTPException(404, "collector.py not found")


# ── Ingest: Metrics ───────────────────────────────────────────────────────────
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
        node = Node(
            id=payload.node_id, hostname=payload.hostname or payload.node_id,
            ip=payload.ip, os=payload.os
        )
        db.add(node)
    else:
        node.last_seen = ts
        if payload.hostname: node.hostname = payload.hostname
        if payload.ip:       node.ip       = payload.ip

    # Store metric
    metric = Metric(
        node_id=payload.node_id, ts=ts,
        cpu_percent=payload.cpu_percent,
        memory_percent=payload.memory_percent,
        memory_used_mb=payload.memory_used_mb,
        disk_percent=payload.disk_percent,
        disk_used_gb=payload.disk_used_gb,
        net_bytes_sent=payload.net_bytes_sent,
        net_bytes_recv=payload.net_bytes_recv,
        load_avg_1m=payload.load_avg_1m,
        process_count=payload.process_count,
        extra=payload.extra,
    )
    db.add(metric)
    await db.commit()

    # Update cache
    m_dict = payload.model_dump()
    _recent_metrics[payload.node_id].append(m_dict)
    _recent_metrics[payload.node_id] = _recent_metrics[payload.node_id][-60:]
    _node_cache[payload.node_id] = {"hostname": payload.hostname, "ip": payload.ip, "os": payload.os}

    # Run detection in background
    background_tasks.add_task(_run_metric_detection, payload.node_id, m_dict, db)

    # Broadcast to dashboard
    await ws_manager.broadcast({
        "type":    "metric",
        "node_id": payload.node_id,
        "data":    m_dict,
    })

    return {"accepted": True}


# ── Ingest: Events ────────────────────────────────────────────────────────────
@app.post("/api/ingest/events")
async def ingest_events(
    payload: EventPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    ts = datetime.fromisoformat(payload.ts) if payload.ts else datetime.utcnow()

    event = Event(
        node_id=payload.node_id, ts=ts,
        type=payload.type, severity=payload.severity,
        source=payload.source, message=payload.message,
        data=payload.data,
    )
    db.add(event)
    await db.commit()

    e_dict = payload.model_dump()
    _recent_events[payload.node_id].append(e_dict)
    _recent_events[payload.node_id] = _recent_events[payload.node_id][-100:]

    background_tasks.add_task(_run_event_detection, payload.node_id, e_dict, db)

    await ws_manager.broadcast({"type": "event", "node_id": payload.node_id, "data": e_dict})
    return {"accepted": True}


# ── Detection background tasks ────────────────────────────────────────────────
async def _run_metric_detection(node_id: str, metric: dict, db: AsyncSession):
    triggered = evaluate_metric(node_id, metric)
    for a in triggered:
        await _save_and_escalate_alert(node_id, a, db)


async def _run_event_detection(node_id: str, event: dict, db: AsyncSession):
    triggered = evaluate_event(node_id, event)
    for a in triggered:
        await _save_and_escalate_alert(node_id, a, db)


async def _save_and_escalate_alert(node_id: str, alert_data: dict, db: AsyncSession):
    alert = Alert(
        node_id=alert_data["node_id"],
        rule_id=alert_data["rule_id"],
        rule_name=alert_data["rule_name"],
        severity=alert_data["severity"],
        category=alert_data["category"],
        message=alert_data["message"],
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    await ws_manager.broadcast({"type": "alert", "node_id": node_id, "data": {
        "id": alert.id, **alert_data
    }})

    # Auto-create incident for critical/high alerts
    if alert.severity in ("critical", "high"):
        asyncio.create_task(_create_incident(node_id, alert.id, alert_data))


async def _create_incident(node_id: str, alert_id: int, alert_data: dict):
    """Create an incident, run RCA, route to teams, bridge call."""
    async with get_db().__aiter__().__anext__() as db:
        try:
            node_info     = _node_cache.get(node_id, {})
            recent_m      = _recent_metrics.get(node_id, [])[-20:]
            recent_e      = _recent_events.get(node_id, [])[-20:]
            tech_stack    = os.getenv("TECH_STACK", "").split(",") or None

            print(f"[PULSE] Running RCA for {node_id}: {alert_data['rule_name']}")
            rca = await analyse_incident(
                node_id, node_info, [alert_data], recent_m, recent_e, tech_stack
            )

            teams_routing = route_incident([alert_data["category"]], rca)

            incident = Incident(
                node_id=node_id,
                title=alert_data["rule_name"],
                severity=alert_data["severity"],
                status="open",
                alert_ids=[alert_id],
                rca=rca,
                routed_teams=[t["id"] for t in teams_routing.get("owners", [])],
            )
            db.add(incident)
            await db.commit()
            await db.refresh(incident)

            # Bridge call
            inc_dict = {
                "id": incident.id, "node_id": node_id,
                "title": incident.title, "severity": incident.severity,
                "ts": incident.ts.isoformat(),
            }
            bridge = await bridge_incident(inc_dict, teams_routing, rca)
            incident.bridge = bridge
            await db.commit()

            await ws_manager.broadcast({"type": "incident", "node_id": node_id, "data": {
                "id": incident.id, "title": incident.title,
                "severity": incident.severity, "rca": rca,
                "routed_teams": incident.routed_teams, "bridge": bridge,
            }})

            print(f"[PULSE] Incident #{incident.id} created | teams: {incident.routed_teams} | bridge: {bridge.get('bridged')}")

        except Exception as e:
            print(f"[PULSE] Incident creation failed: {e}")
            import traceback; traceback.print_exc()


# ── Query endpoints ───────────────────────────────────────────────────────────
@app.get("/api/nodes")
async def list_nodes(db: AsyncSession = Depends(get_db)):
    nodes = (await db.execute(select(Node).order_by(Node.last_seen.desc()))).scalars().all()
    # Attach latest metric to each node
    result = []
    for n in nodes:
        latest = _recent_metrics.get(n.id, [{}])[-1]
        result.append({
            "id": n.id, "hostname": n.hostname, "ip": n.ip, "os": n.os,
            "status": n.status, "last_seen": n.last_seen.isoformat(),
            "latest_metric": latest,
        })
    return {"nodes": result}


@app.get("/api/nodes/{node_id}/metrics")
async def get_metrics(node_id: str, minutes: int = 60, db: AsyncSession = Depends(get_db)):
    since = datetime.utcnow() - timedelta(minutes=minutes)
    rows  = (await db.execute(
        select(Metric).where(Metric.node_id == node_id, Metric.ts >= since)
        .order_by(Metric.ts.asc())
    )).scalars().all()
    return {"node_id": node_id, "metrics": [
        {
            "ts": r.ts.isoformat(), "cpu": r.cpu_percent, "memory": r.memory_percent,
            "disk": r.disk_percent, "load": r.load_avg_1m,
            "net_sent": r.net_bytes_sent, "net_recv": r.net_bytes_recv,
        }
        for r in rows
    ]}


@app.get("/api/alerts")
async def list_alerts(
    node_id: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: bool = False,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    q = select(Alert).where(Alert.resolved == resolved).order_by(Alert.ts.desc()).limit(limit)
    if node_id:   q = q.where(Alert.node_id == node_id)
    if severity:  q = q.where(Alert.severity == severity)
    alerts = (await db.execute(q)).scalars().all()
    return {"alerts": [
        {"id": a.id, "node_id": a.node_id, "rule_name": a.rule_name,
         "severity": a.severity, "category": a.category,
         "message": a.message, "ts": a.ts.isoformat(), "resolved": a.resolved}
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
    return {"resolved": len(req.alert_ids)}


@app.get("/api/incidents")
async def list_incidents(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    q = select(Incident).order_by(Incident.ts.desc()).limit(limit)
    if status:
        q = q.where(Incident.status == status)
    incidents = (await db.execute(q)).scalars().all()
    return {"incidents": [
        {
            "id": i.id, "node_id": i.node_id, "title": i.title,
            "severity": i.severity, "status": i.status,
            "ts": i.ts.isoformat(), "rca": i.rca,
            "routed_teams": i.routed_teams, "bridge": i.bridge,
        }
        for i in incidents
    ]}


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: int, db: AsyncSession = Depends(get_db)):
    i = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not i:
        raise HTTPException(404, "Incident not found")
    return {
        "id": i.id, "node_id": i.node_id, "title": i.title,
        "severity": i.severity, "status": i.status, "ts": i.ts.isoformat(),
        "alert_ids": i.alert_ids, "rca": i.rca,
        "routed_teams": i.routed_teams, "bridge": i.bridge,
    }


@app.post("/api/incidents/{incident_id}/bridge")
async def manual_bridge(incident_id: int, db: AsyncSession = Depends(get_db)):
    """Manually trigger team bridge call for an existing incident."""
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


@app.get("/api/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    nodes_count    = (await db.execute(select(func.count(Node.id)))).scalar()
    open_alerts    = (await db.execute(select(func.count(Alert.id)).where(Alert.resolved == False))).scalar()
    critical_alerts = (await db.execute(select(func.count(Alert.id)).where(Alert.severity == "critical", Alert.resolved == False))).scalar()
    open_incidents = (await db.execute(select(func.count(Incident.id)).where(Incident.status == "open"))).scalar()

    return {
        "nodes":            nodes_count,
        "open_alerts":      open_alerts,
        "critical_alerts":  critical_alerts,
        "open_incidents":   open_incidents,
        "connected_clients": len(ws_manager.connections),
    }


@app.get("/api/events")
async def list_events(node_id: Optional[str] = None, limit: int = 100, db: AsyncSession = Depends(get_db)):
    q = select(Event).order_by(Event.ts.desc()).limit(limit)
    if node_id:
        q = q.where(Event.node_id == node_id)
    events = (await db.execute(q)).scalars().all()
    return {"events": [
        {"id": e.id, "node_id": e.node_id, "ts": e.ts.isoformat(),
         "type": e.type, "severity": e.severity, "message": e.message}
        for e in events
    ]}


# ── WebSocket: real-time feed ──────────────────────────────────────────────────
@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send current state on connect
        await websocket.send_json({"type": "connected", "ts": datetime.utcnow().isoformat()})
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
