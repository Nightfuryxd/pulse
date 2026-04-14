"""
Auth — User authentication system for PULSE.

JWT-based sessions with bcrypt password hashing.
Supports signup, login, token refresh, and user management.
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt, JWTError
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime, Boolean, JSON, Integer, func, select

from db import Base, SessionLocal

# ── Config ───────────────────────────────────────────────────────────────────

JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET or JWT_SECRET == "dev-secret-key":
    raise RuntimeError(
        "SECURITY: JWT_SECRET environment variable is not set or is using the "
        "insecure default 'dev-secret-key'. Set a strong random secret via: "
        "export JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    )
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
ALLOW_SIGNUP = os.getenv("ALLOW_SIGNUP", "true").lower() == "true"

# TODO: Add rate limiting to login/signup endpoints to prevent brute-force attacks.
# Consider using slowapi or fastapi-limiter with a Redis backend.
# Recommended limits: login 5 req/min per IP, signup 3 req/min per IP.

# ── User model ───────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id:             Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    email:          Mapped[str]           = mapped_column(String, unique=True, index=True)
    password_hash:  Mapped[str]           = mapped_column(String, default="")
    name:           Mapped[str]           = mapped_column(String, default="")
    role:           Mapped[str]           = mapped_column(String, default="admin")  # admin, member, viewer
    org_name:       Mapped[str]           = mapped_column(String, default="My Organization")
    avatar_url:     Mapped[str]           = mapped_column(String, default="")
    onboarded:      Mapped[bool]          = mapped_column(Boolean, default=False)
    settings:       Mapped[dict]          = mapped_column(JSON, default=dict)
    oauth_provider: Mapped[str]           = mapped_column(String, default="")
    oauth_id:       Mapped[str]           = mapped_column(String, default="")
    created_at:     Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())
    last_login:     Mapped[datetime|None] = mapped_column(DateTime, nullable=True)


# ── Password hashing ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ── JWT tokens ───────────────────────────────────────────────────────────────

def create_token(user_id: int, email: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ── Auth operations ──────────────────────────────────────────────────────────

async def signup(email: str, password: str, name: str = "", org_name: str = "My Organization") -> dict:
    if not ALLOW_SIGNUP:
        raise ValueError("Signup is disabled")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    async with SessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            raise ValueError("Email already registered")

        user = User(
            email=email,
            password_hash=hash_password(password),
            name=name,
            org_name=org_name,
            role="admin",
            onboarded=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        token = create_token(user.id, user.email, user.role)
        return {
            "token": token,
            "user": _user_dict(user),
        }


async def login(email: str, password: str) -> dict:
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")

        user.last_login = datetime.utcnow()
        await db.commit()

        token = create_token(user.id, user.email, user.role)
        return {
            "token": token,
            "user": _user_dict(user),
        }


async def get_user(user_id: int) -> Optional[dict]:
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            return None
        return _user_dict(user)


async def update_user(user_id: int, updates: dict) -> dict:
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        if "name" in updates:
            user.name = updates["name"]
        if "org_name" in updates:
            user.org_name = updates["org_name"]
        if "onboarded" in updates:
            user.onboarded = updates["onboarded"]
        if "settings" in updates:
            user.settings = {**(user.settings or {}), **updates["settings"]}

        await db.commit()
        await db.refresh(user)
        return _user_dict(user)


async def complete_onboarding(user_id: int) -> dict:
    return await update_user(user_id, {"onboarded": True})


async def oauth_login_or_create(email: str, name: str, avatar_url: str, provider: str, provider_id: str) -> dict:
    """Find or create a user from an OAuth callback, then return a JWT."""
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

        if user:
            # Update OAuth fields + avatar if missing
            user.oauth_provider = provider
            user.oauth_id = provider_id
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            user.last_login = datetime.utcnow()
            await db.commit()
            await db.refresh(user)
        else:
            # Auto-create user from OAuth
            user = User(
                email=email,
                name=name,
                avatar_url=avatar_url,
                oauth_provider=provider,
                oauth_id=provider_id,
                role="admin",
                onboarded=False,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        token = create_token(user.id, user.email, user.role)
        return {"token": token, "user": _user_dict(user)}


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "org_name": user.org_name,
        "avatar_url": user.avatar_url,
        "onboarded": user.onboarded,
        "settings": user.settings or {},
        "oauth_provider": user.oauth_provider or "",
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ── Auth middleware helper ───────────────────────────────────────────────────

def get_current_user_from_request(request: Request) -> Optional[dict]:
    """Extract user from JWT in Authorization header or cookie."""
    token = None

    # Check Authorization header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]

    # Check cookie
    if not token:
        token = request.cookies.get("pulse_token")

    if not token:
        return None

    return decode_token(token)


# Public paths that don't need auth
AUTH_PUBLIC_PATHS = {
    "/", "/health", "/api/stats", "/api/auth/login", "/api/auth/signup",
    "/api/auth/check", "/api/auth/oauth/providers",
    "/login", "/signup", "/onboarding",
    "/agent/collector.py", "/install.sh", "/install.ps1", "/status",
}

AUTH_PUBLIC_PREFIXES_OAUTH = ("/api/auth/oauth/",)

AUTH_PUBLIC_PREFIXES = ("/api/", "/v1/traces", "/v1/metrics", "/v1/logs", "/ws/", "/api/auth/oauth/")


async def auth_middleware(request: Request, call_next):
    """JWT auth middleware — protects all routes except public ones."""
    path = request.url.path

    # Public paths
    if path in AUTH_PUBLIC_PATHS:
        return await call_next(request)

    # Public prefixes (ingest endpoints use API keys, not user auth)
    for prefix in AUTH_PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return await call_next(request)

    # Static assets
    if path.startswith("/assets/") or path.endswith((".js", ".css", ".ico", ".png", ".svg")):
        return await call_next(request)

    # Check auth
    user = get_current_user_from_request(request)
    if not user:
        # For API calls, return 401
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"error": "Not authenticated"})
        # For page loads, redirect to login
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)

    request.state.user = user
    return await call_next(request)
