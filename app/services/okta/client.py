"""Okta identity and access management client via the Okta API.

Authentication: API token in ``Authorization: SSWS {token}`` header.

Reference: https://developer.okta.com/docs/reference/api/users/
"""

from __future__ import annotations

from typing import Any

import requests


class OktaClient:
    """HTTP client for the Okta API."""

    def __init__(self, domain: str, api_token: str) -> None:
        base = domain.rstrip("/")
        if not base.startswith("https://"):
            base = f"https://{base}"
        self._base = f"{base}/api/v1"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"SSWS {api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def get_user(self, user_id_or_login: str) -> dict[str, Any]:
        """Get a user by ID, login, or email."""
        resp = self._session.get(f"{self._base}/users/{user_id_or_login}", timeout=15)
        resp.raise_for_status()
        return self._parse_user(resp.json())

    def search_users(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        """Search users by name, email, or login."""
        params: dict[str, Any] = {"q": query, "limit": min(limit, 200)}
        resp = self._session.get(f"{self._base}/users", params=params, timeout=15)
        resp.raise_for_status()
        return [self._parse_user(u) for u in resp.json()]

    def get_user_groups(self, user_id: str) -> list[dict[str, Any]]:
        """Return all groups a user belongs to."""
        resp = self._session.get(f"{self._base}/users/{user_id}/groups", timeout=15)
        resp.raise_for_status()
        return [
            {
                "id": g.get("id", ""),
                "name": (g.get("profile") or {}).get("name", ""),
                "description": (g.get("profile") or {}).get("description", ""),
                "type": g.get("type", ""),
            }
            for g in resp.json()
        ]

    def get_user_app_assignments(self, user_id: str) -> list[dict[str, Any]]:
        """Return applications assigned to a user."""
        resp = self._session.get(
            f"{self._base}/users/{user_id}/appLinks", timeout=15
        )
        resp.raise_for_status()
        return [
            {
                "app_name": a.get("appName", ""),
                "label": a.get("label", ""),
                "app_instance_id": a.get("appInstanceId", ""),
                "url": a.get("linkUrl", ""),
            }
            for a in resp.json()
        ]

    def get_user_auth_events(
        self,
        user_id: str,
        since: str | None = None,
        until: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return system log events for a specific user (login, MFA, access)."""
        params: dict[str, Any] = {
            "filter": f'actor.id eq "{user_id}"',
            "limit": min(limit, 1000),
            "sortOrder": "DESCENDING",
        }
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        resp = self._session.get(f"{self._base}/logs", params=params, timeout=20)
        resp.raise_for_status()
        return [self._parse_log_event(e) for e in resp.json()]

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_user(raw: dict[str, Any]) -> dict[str, Any]:
        profile = raw.get("profile") or {}
        return {
            "id": raw.get("id", ""),
            "login": profile.get("login", ""),
            "email": profile.get("email", ""),
            "first_name": profile.get("firstName", ""),
            "last_name": profile.get("lastName", ""),
            "display_name": f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
            "title": profile.get("title", ""),
            "department": profile.get("department", ""),
            "manager": profile.get("manager", ""),
            "status": raw.get("status", ""),
            "created_at": raw.get("created", ""),
            "last_login": raw.get("lastLogin", ""),
            "password_changed": raw.get("passwordChanged", ""),
        }

    @staticmethod
    def _parse_log_event(raw: dict[str, Any]) -> dict[str, Any]:
        actor = raw.get("actor") or {}
        target = raw.get("target") or []
        outcome = raw.get("outcome") or {}
        client_info = raw.get("client") or {}
        return {
            "event_type": raw.get("eventType", ""),
            "published": raw.get("published", ""),
            "actor_id": actor.get("id", ""),
            "actor_login": actor.get("alternateId", ""),
            "actor_display_name": actor.get("displayName", ""),
            "outcome": outcome.get("result", ""),
            "reason": outcome.get("reason", ""),
            "ip_address": client_info.get("ipAddress", ""),
            "user_agent": (client_info.get("userAgent") or {}).get("rawUserAgent", ""),
            "target_ids": [t.get("id", "") for t in target if t.get("type") == "User"],
        }

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> OktaClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def make_okta_client(
    domain: str | None = None,
    api_token: str | None = None,
) -> OktaClient | None:
    """Create an OktaClient, or None if credentials are missing."""
    if not domain or not api_token:
        return None
    return OktaClient(domain=domain, api_token=api_token)
