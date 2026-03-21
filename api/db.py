"""Database setup — PostgreSQL via SQLAlchemy async."""
import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, DateTime, Text, JSON, func

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://pulse:pulse_secret@localhost:5432/pulse")
# sqlalchemy needs +asyncpg driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Node(Base):
    __tablename__ = "nodes"
    id:         Mapped[str]      = mapped_column(String, primary_key=True)
    hostname:   Mapped[str]      = mapped_column(String)
    ip:         Mapped[str]      = mapped_column(String, default="")
    os:         Mapped[str]      = mapped_column(String, default="")
    tags:       Mapped[dict]     = mapped_column(JSON, default=dict)
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
    type:      Mapped[str]      = mapped_column(String, index=True)   # auth_failure, process_exit, etc.
    severity:  Mapped[str]      = mapped_column(String, default="info")
    source:    Mapped[str]      = mapped_column(String, default="")    # log file or subsystem
    message:   Mapped[str]      = mapped_column(Text, default="")
    data:      Mapped[dict]     = mapped_column(JSON, default=dict)    # raw event data


class Alert(Base):
    __tablename__ = "alerts"
    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id:    Mapped[str]      = mapped_column(String, index=True)
    rule_id:    Mapped[str]      = mapped_column(String)
    rule_name:  Mapped[str]      = mapped_column(String)
    severity:   Mapped[str]      = mapped_column(String)
    category:   Mapped[str]      = mapped_column(String)
    message:    Mapped[str]      = mapped_column(Text)
    ts:         Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved:   Mapped[bool]     = mapped_column(default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Incident(Base):
    __tablename__ = "incidents"
    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id:       Mapped[str]      = mapped_column(String, index=True)
    title:         Mapped[str]      = mapped_column(String)
    severity:      Mapped[str]      = mapped_column(String)
    status:        Mapped[str]      = mapped_column(String, default="open")   # open | investigating | resolved
    ts:            Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    alert_ids:     Mapped[list]     = mapped_column(JSON, default=list)
    rca:           Mapped[dict]     = mapped_column(JSON, default=dict)        # AI root cause analysis
    routed_teams:  Mapped[list]     = mapped_column(JSON, default=list)
    bridge:        Mapped[dict]     = mapped_column(JSON, default=dict)        # call bridge details
    resolved_at:   Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Tables ready")


async def get_db():
    async with SessionLocal() as session:
        yield session
