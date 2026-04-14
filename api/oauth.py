"""
OAuth 2.0 — Google & GitHub provider integration for PULSE.

Handles OAuth authorization URL generation, callback token exchange,
and user profile fetching. Issues the same JWT tokens as email/password auth.
"""
import os
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx

# ── Provider config (set via env vars) ───────────────────────────────────────

GOOGLE_CLIENT_ID = os.getenv("OAUTH_GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("OAUTH_GOOGLE_CLIENT_SECRET", "")

GITHUB_CLIENT_ID = os.getenv("OAUTH_GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("OAUTH_GITHUB_CLIENT_SECRET", "")

# Base URL for callback redirects (e.g. http://localhost:3000)
OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://127.0.0.1:59184")

# ── State tokens (in-memory for now, swap to Redis for multi-instance) ───────

_pending_states: dict[str, str] = {}  # state -> provider


def _generate_state(provider: str) -> str:
    state = secrets.token_urlsafe(32)
    _pending_states[state] = provider
    return state


def _validate_state(state: str) -> Optional[str]:
    return _pending_states.pop(state, None)


# ── Google OAuth 2.0 ────────────────────────────────────────────────────────

def google_auth_url() -> str:
    if not GOOGLE_CLIENT_ID:
        raise ValueError("OAUTH_GOOGLE_CLIENT_ID not configured")
    state = _generate_state("google")
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def google_exchange(code: str, state: str) -> dict:
    provider = _validate_state(state)
    if provider != "google":
        raise ValueError("Invalid or expired OAuth state")

    async with httpx.AsyncClient() as client:
        # Exchange code for tokens
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/google/callback",
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        # Fetch user info
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()

    return {
        "email": info["email"],
        "name": info.get("name", ""),
        "avatar_url": info.get("picture", ""),
        "provider": "google",
        "provider_id": info["id"],
    }


# ── GitHub OAuth 2.0 ────────────────────────────────────────────────────────

def github_auth_url() -> str:
    if not GITHUB_CLIENT_ID:
        raise ValueError("OAUTH_GITHUB_CLIENT_ID not configured")
    state = _generate_state("github")
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": f"{OAUTH_REDIRECT_BASE}/api/auth/oauth/github/callback",
        "scope": "read:user user:email",
        "state": state,
    }
    return f"https://github.com/login/oauth/authorize?{urlencode(params)}"


async def github_exchange(code: str, state: str) -> dict:
    provider = _validate_state(state)
    if provider != "github":
        raise ValueError("Invalid or expired OAuth state")

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()
        access_token = tokens["access_token"]

        # Fetch user profile
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        user = user_resp.json()

        # Fetch primary email (may be private)
        email = user.get("email")
        if not email:
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            emails_resp.raise_for_status()
            for e in emails_resp.json():
                if e.get("primary"):
                    email = e["email"]
                    break

    return {
        "email": email,
        "name": user.get("name") or user.get("login", ""),
        "avatar_url": user.get("avatar_url", ""),
        "provider": "github",
        "provider_id": str(user["id"]),
    }


# ── Provider availability ───────────────────────────────────────────────────

def get_enabled_providers() -> list[str]:
    providers = []
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        providers.append("google")
    if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET:
        providers.append("github")
    return providers
