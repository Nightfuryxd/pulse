"""Database setup — PostgreSQL via SQLAlchemy async."""
import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, DateTime, Text, JSON, Boolean, func

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://pulse:pulse_secret@localhost:5432/pulse")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine       = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ── Core monitoring models ────────────────────────────────────────────────────

class Node(Base):
    __tablename__ = "nodes"
    id:         Mapped[str]      = mapped_column(String, primary_key=True)
    hostname:   Mapped[str]      = mapped_column(String)
    ip:         Mapped[str]      = mapped_column(String, default="")
    os:         Mapped[str]      = mapped_column(String, default="")
    tags:       Mapped[dict]     = mapped_column(JSON, default=dict)
    meta:       Mapped[dict]     = mapped_column(JSON, default=dict)   # SDK info, version, etc.
    first_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen:  Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    status:     Mapped[str]      = mapped_column(String, default="active")


class Metric(Base):
    __tablename__ = "metrics"
    id:              Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id:         Mapped[str]      = mapped_column(String, index=True)
    ts:              Mapped[datetime] = mapped_column(DateTime, index=True)
    cpu_percent:     Mapped[float]    = mapped_column(Float, default=0)
    memory_percent:  Mapped[float]    = mapped_column(Float, default=0)
    memory_used_mb:  Mapped[float]    = mapped_column(Float, default=0)
    disk_percent:    Mapped[float]    = mapped_column(Float, default=0)
    disk_used_gb:    Mapped[float]    = mapped_column(Float, default=0)
    net_bytes_sent:  Mapped[float]    = mapped_column(Float, default=0)
    net_bytes_recv:  Mapped[float]    = mapped_column(Float, default=0)
    load_avg_1m:     Mapped[float]    = mapped_column(Float, default=0)
    process_count:   Mapped[int]      = mapped_column(Integer, default=0)
    extra:           Mapped[dict]     = mapped_column(JSON, default=dict)


class Event(Base):
    __tablename__ = "events"
    id:        Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id:   Mapped[str]      = mapped_column(String, index=True)
    ts:        Mapped[datetime] = mapped_column(DateTime, index=True)
    type:      Mapped[str]      = mapped_column(String, index=True)
    severity:  Mapped[str]      = mapped_column(String, default="info")
    source:    Mapped[str]      = mapped_column(String, default="")
    message:   Mapped[str]      = mapped_column(Text, default="")
    data:      Mapped[dict]     = mapped_column(JSON, default=dict)


class Alert(Base):
    __tablename__ = "alerts"
    id:          Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id:     Mapped[str]           = mapped_column(String, index=True)
    rule_id:     Mapped[str]           = mapped_column(String)
    rule_name:   Mapped[str]           = mapped_column(String)
    severity:    Mapped[str]           = mapped_column(String)
    category:    Mapped[str]           = mapped_column(String)
    message:     Mapped[str]           = mapped_column(Text)
    ts:          Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())
    resolved:    Mapped[bool]          = mapped_column(default=False)
    resolved_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    group_id:    Mapped[str|None]      = mapped_column(String, nullable=True, index=True)  # correlation group


class Incident(Base):
    __tablename__ = "incidents"
    id:            Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id:       Mapped[str]           = mapped_column(String, index=True)
    title:         Mapped[str]           = mapped_column(String)
    severity:      Mapped[str]           = mapped_column(String)
    status:        Mapped[str]           = mapped_column(String, default="open")
    ts:            Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())
    alert_ids:     Mapped[list]          = mapped_column(JSON, default=list)
    node_ids:      Mapped[list]          = mapped_column(JSON, default=list)   # all affected nodes
    rca:           Mapped[dict]          = mapped_column(JSON, default=dict)
    routed_teams:  Mapped[list]          = mapped_column(JSON, default=list)
    bridge:        Mapped[dict]          = mapped_column(JSON, default=dict)
    correlation:   Mapped[dict]          = mapped_column(JSON, default=dict)   # correlation details
    remediation:   Mapped[dict]          = mapped_column(JSON, default=dict)   # playbook execution log
    resolved_at:   Mapped[datetime|None] = mapped_column(DateTime, nullable=True)


# ── Log aggregation ───────────────────────────────────────────────────────────

class Log(Base):
    """Centralised log store — receives from all agents and app SDKs."""
    __tablename__ = "logs"
    id:        Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id:   Mapped[str]      = mapped_column(String, index=True)
    service:   Mapped[str]      = mapped_column(String, default="", index=True)   # app service name
    ts:        Mapped[datetime] = mapped_column(DateTime, index=True)
    level:     Mapped[str]      = mapped_column(String, default="info", index=True)  # debug/info/warn/error/fatal
    source:    Mapped[str]      = mapped_column(String, default="")   # file or logger name
    message:   Mapped[str]      = mapped_column(Text, default="")
    trace_id:  Mapped[str|None] = mapped_column(String, nullable=True, index=True)  # distributed trace
    span_id:   Mapped[str|None] = mapped_column(String, nullable=True)
    extra:     Mapped[dict]     = mapped_column(JSON, default=dict)


# ── Service topology ──────────────────────────────────────────────────────────

class ServiceEdge(Base):
    """Observed connection between two services — builds the dependency graph."""
    __tablename__ = "service_edges"
    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    src_node:     Mapped[str]      = mapped_column(String, index=True)
    src_service:  Mapped[str]      = mapped_column(String, default="")
    src_port:     Mapped[int]      = mapped_column(Integer, default=0)
    dst_ip:       Mapped[str]      = mapped_column(String)
    dst_node:     Mapped[str]      = mapped_column(String, default="")  # resolved if known
    dst_service:  Mapped[str]      = mapped_column(String, default="")
    dst_port:     Mapped[int]      = mapped_column(Integer, default=0)
    protocol:     Mapped[str]      = mapped_column(String, default="tcp")
    bytes_sent:   Mapped[int]      = mapped_column(Integer, default=0)
    conn_count:   Mapped[int]      = mapped_column(Integer, default=1)
    first_seen:   Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── App SDK spans (traces) ────────────────────────────────────────────────────

class Span(Base):
    """Application-level trace span — from the SDK."""
    __tablename__ = "spans"
    id:         Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id:    Mapped[str]           = mapped_column(String, index=True)
    service:    Mapped[str]           = mapped_column(String, index=True)
    trace_id:   Mapped[str]           = mapped_column(String, index=True)
    span_id:    Mapped[str]           = mapped_column(String)
    parent_id:  Mapped[str|None]      = mapped_column(String, nullable=True)
    operation:  Mapped[str]           = mapped_column(String)  # http.request, db.query, cache.get
    ts:         Mapped[datetime]      = mapped_column(DateTime, index=True)
    duration_ms: Mapped[float]        = mapped_column(Float, default=0)
    status:     Mapped[str]           = mapped_column(String, default="ok")  # ok | error | timeout
    tags:       Mapped[dict]          = mapped_column(JSON, default=dict)
    error:      Mapped[str|None]      = mapped_column(Text, nullable=True)


# ── Playbook execution log ────────────────────────────────────────────────────

class PlaybookRun(Base):
    __tablename__ = "playbook_runs"
    id:          Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    playbook_id: Mapped[str]      = mapped_column(String)
    incident_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    alert_id:    Mapped[int|None] = mapped_column(Integer, nullable=True)
    node_id:     Mapped[str]      = mapped_column(String)
    ts:          Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status:      Mapped[str]      = mapped_column(String, default="running")  # running|success|failed
    steps:       Mapped[list]     = mapped_column(JSON, default=list)   # step results
    output:      Mapped[str]      = mapped_column(Text, default="")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Tables ready")


async def get_db():
    async with SessionLocal() as session:
        yield session
