"""Google Calendar client via the Google Calendar API v3.

Authentication: OAuth2 bearer token or service account with domain-wide delegation.
Scopes required: https://www.googleapis.com/auth/calendar.readonly

Reference: https://developers.google.com/calendar/api/v3/reference
"""

from __future__ import annotations

from typing import Any

import requests


class GoogleCalendarClient:
    """HTTP client for the Google Calendar API."""

    _BASE = "https://www.googleapis.com/calendar/v3"

    def __init__(self, access_token: str) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Event listing and search
    # ------------------------------------------------------------------

    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        query: str | None = None,
        max_results: int = 50,
        single_events: bool = True,
    ) -> dict[str, Any]:
        """List calendar events within an optional date range."""
        params: dict[str, Any] = {
            "maxResults": min(max_results, 2500),
            "singleEvents": str(single_events).lower(),
            "orderBy": "startTime" if single_events else "updated",
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query

        resp = self._session.get(
            f"{self._BASE}/calendars/{calendar_id}/events",
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("items", [])
        return {
            "events": [self._parse_event(e) for e in raw],
            "calendar_id": calendar_id,
            "next_page_token": data.get("nextPageToken"),
        }

    def get_event(self, calendar_id: str, event_id: str) -> dict[str, Any]:
        """Retrieve a single event by ID."""
        resp = self._session.get(
            f"{self._BASE}/calendars/{calendar_id}/events/{event_id}",
            timeout=15,
        )
        resp.raise_for_status()
        return self._parse_event(resp.json())

    def find_meetings_between(
        self,
        calendar_id: str,
        attendee_email: str,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Find events where a specific attendee was invited."""
        result = self.list_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
        )
        target = attendee_email.lower()
        return [
            ev for ev in result["events"]
            if any(target in (a.get("email") or "").lower() for a in ev.get("attendees", []))
        ]

    def list_calendars(self) -> list[dict[str, Any]]:
        """List all calendars accessible to the authenticated user."""
        resp = self._session.get(f"{self._BASE}/users/me/calendarList", timeout=15)
        resp.raise_for_status()
        return [
            {
                "id": c.get("id", ""),
                "summary": c.get("summary", ""),
                "description": c.get("description", ""),
                "access_role": c.get("accessRole", ""),
            }
            for c in resp.json().get("items", [])
        ]

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_event(raw: dict[str, Any]) -> dict[str, Any]:
        start = raw.get("start") or {}
        end = raw.get("end") or {}
        organizer = raw.get("organizer") or {}
        return {
            "id": raw.get("id", ""),
            "summary": raw.get("summary", ""),
            "description": (raw.get("description") or "")[:500],
            "start": start.get("dateTime") or start.get("date", ""),
            "end": end.get("dateTime") or end.get("date", ""),
            "organizer_email": organizer.get("email", ""),
            "organizer_name": organizer.get("displayName", ""),
            "attendees": [
                {
                    "email": a.get("email", ""),
                    "display_name": a.get("displayName", ""),
                    "response": a.get("responseStatus", ""),
                    "optional": a.get("optional", False),
                }
                for a in (raw.get("attendees") or [])
            ],
            "location": raw.get("location", ""),
            "status": raw.get("status", ""),
            "html_link": raw.get("htmlLink", ""),
            "recurring_event_id": raw.get("recurringEventId"),
            "created": raw.get("created", ""),
            "updated": raw.get("updated", ""),
        }

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> GoogleCalendarClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def make_google_calendar_client(
    access_token: str | None = None,
) -> GoogleCalendarClient | None:
    """Create a GoogleCalendarClient, or None if no token provided."""
    if not access_token:
        return None
    return GoogleCalendarClient(access_token=access_token)
