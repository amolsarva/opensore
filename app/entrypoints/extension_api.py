"""FastAPI router exposing local endpoints for the OpenSore Chrome extension.

The extension background service worker (background.js) calls these endpoints to:
  - Verify the local server is reachable              GET  /api/extension/ping
  - Fetch OAuth client IDs (no secrets exposed)       GET  /api/extension/config
  - Complete an OAuth code exchange and store token   POST /api/extension/oauth/complete
  - List connected sources (token-free)               GET  /api/extension/connections
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.discovery.connectors.google_workspace import SCOPES as _GOOGLE_SCOPES
from app.discovery.connectors.slack import _TOKEN_URL as _SLACK_TOKEN_URL
from app.discovery.credentials import list_sources, new_source_id, upsert_source, utc_now

router = APIRouter(prefix="/api/extension", tags=["extension"])

_SLACK_USERINFO_URL = "https://slack.com/api/users.info"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


class OAuthCompleteRequest(BaseModel):
    provider: str
    code: str
    redirect_uri: str
    code_verifier: str | None = None   # PKCE verifier — required for Google
    client_id: str | None = None       # extension-supplied override (takes priority over env)
    client_secret: str | None = None   # extension-supplied override


@router.get("/ping")
def extension_ping() -> dict[str, bool]:
    return {"ok": True}


@router.get("/config")
def extension_config() -> dict[str, str]:
    """Return OAuth client IDs so the extension can build auth URLs.

    Client secrets stay server-side and are never sent to the extension.
    """
    return {
        "slack_client_id": os.environ.get("OPENSORE_SLACK_CLIENT_ID", ""),
        "google_client_id": os.environ.get("OPENSORE_GOOGLE_CLIENT_ID", ""),
    }


@router.get("/connections")
def extension_connections() -> dict[str, list[dict[str, str]]]:
    """Return connected discovery sources without any credential or token data."""
    sources = list_sources()
    safe = [
        {
            "id": s.get("id", ""),
            "kind": s.get("kind", ""),
            "label": s.get("label", ""),
            "connected_at": s.get("connected_at", ""),
        }
        for s in sources
        if s.get("kind") in {"slack", "google_workspace"}
    ]
    return {"connections": safe}


@router.post("/oauth/complete")
def extension_oauth_complete(request: OAuthCompleteRequest) -> dict[str, Any]:
    """Exchange an authorization code received by the extension for a stored token."""
    if request.provider == "slack":
        return _complete_slack(request)
    if request.provider == "google":
        return _complete_google(request)
    raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider!r}")


# ── Slack ────────────────────────────────────────────────────────────────────


def _complete_slack(req: OAuthCompleteRequest) -> dict[str, Any]:
    client_id = (req.client_id or os.environ.get("OPENSORE_SLACK_CLIENT_ID", "")).strip()
    client_secret = (req.client_secret or os.environ.get("OPENSORE_SLACK_CLIENT_SECRET", "")).strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Slack OAuth credentials not configured. "
                "Enter your Client ID and Secret in the extension popup setup wizard."
            ),
        )

    with httpx.Client() as client:
        token_resp = client.post(
            _SLACK_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": req.code,
                "redirect_uri": req.redirect_uri,
            },
            timeout=15.0,
        )
    if not token_resp.is_success:
        raise HTTPException(status_code=502, detail="Slack token exchange HTTP error")

    token_data = token_resp.json()
    if not token_data.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"Slack token exchange failed: {token_data.get('error', 'unknown')}",
        )

    authed_user: dict[str, Any] = token_data.get("authed_user", {})
    authed_user_token: str = authed_user.get("access_token", "")
    authed_user_id: str = authed_user.get("id", "")
    team: dict[str, Any] = token_data.get("team", {})
    team_name: str = team.get("name", "")

    user_profile: dict[str, Any] = {}
    with httpx.Client() as client:
        info_resp = client.get(
            _SLACK_USERINFO_URL,
            headers={"Authorization": f"Bearer {authed_user_token}"},
            params={"user": authed_user_id},
            timeout=10.0,
        )
    if info_resp.is_success:
        user_profile = info_resp.json().get("user", {}).get("profile", {})

    display_name = (
        user_profile.get("display_name") or user_profile.get("real_name") or authed_user_id
    )
    label = f"{team_name} ({display_name})" if team_name else display_name

    record: dict[str, Any] = {
        "id": new_source_id("sl"),
        "kind": "slack",
        "label": label,
        "team_id": team.get("id", ""),
        "team_name": team_name,
        "user_id": authed_user_id,
        "authed_user_token": authed_user_token,
        "connected_at": utc_now(),
    }
    upsert_source(record)
    return {"ok": True, "id": record["id"], "label": label}


# ── Google ───────────────────────────────────────────────────────────────────


def _complete_google(req: OAuthCompleteRequest) -> dict[str, Any]:
    client_id = (req.client_id or os.environ.get("OPENSORE_GOOGLE_CLIENT_ID", "")).strip()
    client_secret = (req.client_secret or os.environ.get("OPENSORE_GOOGLE_CLIENT_SECRET", "")).strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth credentials not configured. "
                "Enter your Client ID in the extension popup setup wizard."
            ),
        )

    body: dict[str, str] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": req.code,
        "redirect_uri": req.redirect_uri,
        "grant_type": "authorization_code",
    }
    if req.code_verifier:
        body["code_verifier"] = req.code_verifier

    with httpx.Client() as client:
        token_resp = client.post(_GOOGLE_TOKEN_URL, data=body, timeout=15.0)
    if not token_resp.is_success:
        raise HTTPException(status_code=502, detail="Google token exchange HTTP error")

    token_data = token_resp.json()

    email = ""
    with httpx.Client() as client:
        info_resp = client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data.get('access_token', '')}"},
            timeout=10.0,
        )
    if info_resp.is_success:
        email = info_resp.json().get("email", "")

    expiry: str | None = None
    if "expires_in" in token_data:
        expiry = (
            datetime.now(tz=UTC) + timedelta(seconds=int(token_data["expires_in"]))
        ).isoformat()

    record: dict[str, Any] = {
        "id": new_source_id("gs"),
        "kind": "google_workspace",
        "label": email,
        "email": email,
        "scopes": list(_GOOGLE_SCOPES),
        "token": {
            "token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": client_id,
            "scopes": list(_GOOGLE_SCOPES),
            "expiry": expiry,
        },
        "connected_at": utc_now(),
    }
    upsert_source(record)
    return {"ok": True, "id": record["id"], "label": email}
