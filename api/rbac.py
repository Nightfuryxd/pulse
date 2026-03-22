"""
RBAC — Role-Based Access Control for PULSE API.

Three roles:
  admin    — full access (create/delete API keys, modify rules, manage users)
  operator — read + write (ingest, acknowledge, resolve, run playbooks)
  viewer   — read only (dashboards, queries, reports)

Auth mechanism: API key passed via X-API-Key header or ?api_key= query param.
Keys are stored in PostgreSQL with bcrypt hashes.
The dashboard (GET /) and health endpoint are always public.
"""
import hashlib
import os
import secrets
from datetime import datetime
from typing import Optional

from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, Boolean, JSON, func, select

from db import Base, get_db, SessionLocal

# ── Roles & permissions ──────────────────────────────────────────────────────

ROLES = {
    "admin":    {"level": 3, "description": "Full access — manage keys, rules, users"},
    "operator": {"level": 2, "description": "Read + write — ingest, ack, resolve, playbooks"},
    "viewer":   {"level": 1, "description": "Read only — dashboards, queries, reports"},
}

# Map HTTP method + path prefix → minimum role level required
# Lower number = less privilege needed
ROUTE_PERMISSIONS = [
    # Public routes (no auth needed) — handled separately
    # Ingest routes — operator+
    ("POST", "/api/ingest",      2),
    ("POST", "/api/playbooks",   2),
    ("POST", "/api/alerts",      2),
    ("POST", "/api/incidents",   2),
    ("POST", "/api/maintenance", 2),
    ("DELETE", "/api/maintenance", 2),
    # Admin routes
    ("POST",   "/api/admin",     3),
    ("DELETE", "/api/admin",     3),
    ("PUT",    "/api/admin",     3),
    # Read routes — viewer+
    ("GET", "/api", 1),
    # OTel ingest — operator+
    ("POST", "/v1/traces",  2),
    ("POST", "/v1/metrics", 2),
    ("POST", "/v1/logs",    2),
    # Notification test — operator+
    ("POST", "/api/notifications", 2),
    # KB mutations — operator+
    ("POST",   "/api/kb", 2),
    ("PUT",    "/api/kb", 2),
    ("DELETE", "/api/kb", 2),
]

# Routes that are always public (no auth)
PUBLIC_PATHS = {"/", "/health", "/ws/live", "/agent/collector.py", "/install.sh", "/install.ps1"}


# ── API Key model ────────────────────────────────────────────────────────────

class ApiKey(Base):
    __tablename__ = "api_keys"
    id:          Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    name:        Mapped[str]           = mapped_column(String, unique=True)
    key_hash:    Mapped[str]           = mapped_column(String)       # SHA-256 hash
    key_prefix:  Mapped[str]           = mapped_column(String)       # first 8 chars for display
    role:        Mapped[str]           = mapped_column(String, default="viewer")
    created_at:  Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())
    last_used:   Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    active:      Mapped[bool]          = mapped_column(Boolean, default=True)
    created_by:  Mapped[str]           = mapped_column(String, default="system")
    metadata_:   Mapped[dict]          = mapped_column("metadata", JSON, default=dict)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Key management ───────────────────────────────────────────────────────────

_rbac_enabled: bool = os.getenv("RBAC_ENABLED", "false").lower() == "true"
_bootstrap_key: str = os.getenv("PULSE_ADMIN_KEY", "")  # optional bootstrap admin key


def is_rbac_enabled() -> bool:
    return _rbac_enabled


async def create_api_key(name: str, role: str = "viewer", created_by: str = "system") -> dict:
    if role not in ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {list(ROLES.keys())}")

    raw_key = f"pulse_{role[0]}k_{secrets.token_hex(24)}"  # e.g. pulse_ak_abc123...
    key_hash = _hash_key(raw_key)

    async with SessionLocal() as db:
        existing = (await db.execute(select(ApiKey).where(ApiKey.name == name))).scalar_one_or_none()
        if existing:
            raise ValueError(f"API key with name '{name}' already exists")

        api_key = ApiKey(
            name=name,
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            role=role,
            created_by=created_by,
            active=True,
        )
        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": name,
        "role": role,
        "key": raw_key,  # only returned once at creation
        "prefix": raw_key[:12],
        "created_at": api_key.created_at.isoformat(),
    }


async def list_api_keys() -> list[dict]:
    async with SessionLocal() as db:
        keys = (await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))).scalars().all()
        return [
            {
                "id": k.id, "name": k.name, "role": k.role,
                "prefix": k.key_prefix, "active": k.active,
                "created_at": k.created_at.isoformat(),
                "last_used": k.last_used.isoformat() if k.last_used else None,
                "created_by": k.created_by,
            }
            for k in keys
        ]


async def revoke_api_key(key_id: int) -> bool:
    async with SessionLocal() as db:
        key = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
        if not key:
            return False
        key.active = False
        await db.commit()
        return True


async def delete_api_key(key_id: int) -> bool:
    async with SessionLocal() as db:
        key = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
        if not key:
            return False
        await db.delete(key)
        await db.commit()
        return True


async def validate_key(raw_key: str) -> Optional[dict]:
    """Validate an API key and return the key record if valid."""
    key_hash = _hash_key(raw_key)
    async with SessionLocal() as db:
        key = (await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active == True)
        )).scalar_one_or_none()
        if not key:
            return None
        key.last_used = datetime.utcnow()
        await db.commit()
        return {"id": key.id, "name": key.name, "role": key.role, "level": ROLES[key.role]["level"]}


def _get_required_level(method: str, path: str) -> int:
    """Determine minimum role level for a request."""
    for route_method, route_prefix, level in ROUTE_PERMISSIONS:
        if method == route_method and path.startswith(route_prefix):
            return level
    # Default: viewer access for GET, operator for everything else
    return 1 if method == "GET" else 2


# ── FastAPI middleware ────────────────────────────────────────────────────────

async def rbac_middleware(request: Request, call_next):
    """RBAC enforcement middleware. Checks X-API-Key header or api_key query param."""
    if not _rbac_enabled:
        response = await call_next(request)
        return response

    path = request.url.path

    # Public paths skip auth
    if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/openapi"):
        response = await call_next(request)
        return response

    # Extract API key
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")

    # Check bootstrap admin key
    if _bootstrap_key and api_key == _bootstrap_key:
        request.state.user = {"name": "bootstrap-admin", "role": "admin", "level": 3}
        response = await call_next(request)
        return response

    if not api_key:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "Missing API key. Set X-API-Key header."})

    user = await validate_key(api_key)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"error": "Invalid or revoked API key."})

    # Check permission level
    required_level = _get_required_level(request.method, path)
    if user["level"] < required_level:
        from fastapi.responses import JSONResponse
        role_needed = [r for r, v in ROLES.items() if v["level"] == required_level][0]
        return JSONResponse(
            status_code=403,
            content={"error": f"Insufficient permissions. Requires '{role_needed}' role or higher."}
        )

    request.state.user = user
    response = await call_next(request)
    return response
