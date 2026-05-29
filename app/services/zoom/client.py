"""Zoom API client for meeting records and participant data.

Authentication: Server-to-Server OAuth2 (recommended) or JWT.
  - Token endpoint: POST https://zoom.us/oauth/token
  - Grant type: account_credentials
  - Scope: meeting:read:admin, user:read:admin, report:read:admin

Reference: https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/
"""

from __future__ import annotations

from typing import Any

import requests


class ZoomClient:
    """HTTP client for the Zoom API."""

    _BASE = "https://api.zoom.us/v2"

    def __init__(self, access_token: str) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # User meetings
    # ------------------------------------------------------------------

    def list_user_meetings(
        self,
        user_id: str,
        meeting_type: str = "previous_meetings",
        page_size: int = 30,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """List meetings for a specific user.

        Args:
            user_id: Zoom user ID or email
            meeting_type: 'scheduled', 'live', 'upcoming', or 'previous_meetings'
            page_size: Results per page (max 300)
            from_date: YYYY-MM-DD start date (for previous_meetings)
            to_date: YYYY-MM-DD end date (for previous_meetings)
        """
        params: dict[str, Any] = {
            "type": meeting_type,
            "page_size": min(page_size, 300),
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        resp = self._session.get(
            f"{self._BASE}/users/{user_id}/meetings", params=params, timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "meetings": [self._parse_meeting_summary(m) for m in data.get("meetings", [])],
            "user_id": user_id,
            "total_records": data.get("total_records", 0),
        }

    def get_meeting(self, meeting_id: str) -> dict[str, Any]:
        """Get full details for a specific meeting."""
        resp = self._session.get(
            f"{self._BASE}/meetings/{meeting_id}", timeout=15
        )
        resp.raise_for_status()
        return self._parse_meeting_detail(resp.json())

    def get_meeting_participants(self, meeting_id: str, page_size: int = 300) -> dict[str, Any]:
        """Get participant report for a past meeting (requires report:read:admin scope)."""
        resp = self._session.get(
            f"{self._BASE}/report/meetings/{meeting_id}/participants",
            params={"page_size": min(page_size, 300)},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "meeting_id": meeting_id,
            "participants": [self._parse_participant(p) for p in data.get("participants", [])],
            "total_records": data.get("total_records", 0),
        }

    def get_user(self, user_id: str) -> dict[str, Any]:
        """Get Zoom user profile by ID or email."""
        resp = self._session.get(f"{self._BASE}/users/{user_id}", timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        return {
            "id": raw.get("id", ""),
            "email": raw.get("email", ""),
            "first_name": raw.get("first_name", ""),
            "last_name": raw.get("last_name", ""),
            "display_name": f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip(),
            "status": raw.get("status", ""),
            "role_name": raw.get("role_name", ""),
            "dept": raw.get("dept", ""),
            "created_at": raw.get("created_at", ""),
            "last_login_time": raw.get("last_login_time", ""),
        }

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_meeting_summary(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(raw.get("id", "")),
            "uuid": raw.get("uuid", ""),
            "topic": raw.get("topic", ""),
            "host_id": raw.get("host_id", ""),
            "host_email": raw.get("host_email", ""),
            "type": raw.get("type"),
            "start_time": raw.get("start_time", ""),
            "duration_minutes": raw.get("duration"),
            "timezone": raw.get("timezone", ""),
            "join_url": raw.get("join_url", ""),
        }

    @staticmethod
    def _parse_meeting_detail(raw: dict[str, Any]) -> dict[str, Any]:
        settings = raw.get("settings") or {}
        return {
            "id": str(raw.get("id", "")),
            "uuid": raw.get("uuid", ""),
            "topic": raw.get("topic", ""),
            "host_id": raw.get("host_id", ""),
            "host_email": raw.get("host_email", ""),
            "type": raw.get("type"),
            "start_time": raw.get("start_time", ""),
            "duration_minutes": raw.get("duration"),
            "agenda": raw.get("agenda", ""),
            "recording_enabled": settings.get("auto_recording", "none") != "none",
            "waiting_room": settings.get("waiting_room", False),
            "join_url": raw.get("join_url", ""),
            "status": raw.get("status", ""),
        }

    @staticmethod
    def _parse_participant(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": raw.get("id", ""),
            "user_id": raw.get("user_id", ""),
            "name": raw.get("name", ""),
            "email": raw.get("user_email", ""),
            "join_time": raw.get("join_time", ""),
            "leave_time": raw.get("leave_time", ""),
            "duration_seconds": raw.get("duration"),
            "ip_address": raw.get("ip_address", ""),
            "device": raw.get("device", ""),
        }

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> ZoomClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def get_zoom_access_token(
    account_id: str,
    client_id: str,
    client_secret: str,
) -> str:
    """Obtain a Server-to-Server OAuth2 access token."""
    resp = requests.post(
        "https://zoom.us/oauth/token",
        params={"grant_type": "account_credentials", "account_id": account_id},
        auth=(client_id, client_secret),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def make_zoom_client(
    *,
    access_token: str | None = None,
    account_id: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> ZoomClient | None:
    """Create a ZoomClient from credentials.

    Pass either:
    - ``access_token``: a pre-obtained OAuth2 bearer token
    - ``account_id`` + ``client_id`` + ``client_secret``: Server-to-Server OAuth
    """
    if access_token:
        return ZoomClient(access_token=access_token)

    if account_id and client_id and client_secret:
        try:
            token = get_zoom_access_token(account_id, client_id, client_secret)
            return ZoomClient(access_token=token)
        except Exception:
            return None

    return None
