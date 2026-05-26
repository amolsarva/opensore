"""Google Calendar API client for meeting history and participant lookup."""

from __future__ import annotations

from app.services.google_calendar.client import GoogleCalendarClient, make_google_calendar_client

__all__ = ["GoogleCalendarClient", "make_google_calendar_client"]
