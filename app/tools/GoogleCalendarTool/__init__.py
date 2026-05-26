"""Google Calendar meeting history tool for HR/legal investigation workflows."""

from __future__ import annotations

from typing import Any

from app.services.google_calendar import make_google_calendar_client
from app.tools.base import BaseTool


class GoogleCalendarTool(BaseTool):
    """Search Google Calendar event history to establish meeting patterns and relationships.

    Retrieves calendar events within a date range, searches for meetings with
    specific attendees, and returns event details including participants,
    timing, and location.
    """

    name = "search_google_calendar"
    source = "google_calendar"
    description = (
        "Search Google Calendar for meeting history between specified parties within a date range. "
        "Returns event summaries, attendee lists, timing, and organizer details. Use to establish "
        "meeting patterns, verify whether parties interacted, or identify private/recurring meetings "
        "during an investigation window."
    )
    use_cases = [
        "Confirming whether a complainant and accused had private meetings during an incident window",
        "Identifying the frequency and pattern of one-on-one meetings between parties",
        "Verifying whether an employee was present at a meeting they claim not to have attended",
        "Checking whether a manager scheduled recurring private meetings with a direct report",
        "Establishing a timeline of in-person interactions during a harassment investigation",
        "Finding meetings that were later deleted or that lacked usual attendees",
    ]
    requires = ["access_token"]
    input_schema = {
        "type": "object",
        "properties": {
            "access_token": {
                "type": "string",
                "description": "OAuth2 token with calendar.readonly scope",
            },
            "calendar_id": {
                "type": "string",
                "description": "Calendar ID to search (default: 'primary')",
                "default": "primary",
            },
            "time_min": {
                "type": "string",
                "description": "Start of date range in RFC3339 format (e.g. '2024-01-01T00:00:00Z')",
            },
            "time_max": {
                "type": "string",
                "description": "End of date range in RFC3339 format",
            },
            "query": {
                "type": "string",
                "description": "Keyword search across event titles, descriptions, and locations",
            },
            "attendee_email": {
                "type": "string",
                "description": "Filter to events where this email address appears as an attendee",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum events to return (default: 50)",
                "default": 50,
            },
        },
        "required": ["access_token"],
    }
    outputs = {
        "events": "List of events: summary, start, end, organizer, attendees, location",
        "calendar_id": "The calendar that was searched",
        "returned_count": "Number of events returned",
    }

    def is_available(self, sources: dict) -> bool:
        cfg = sources.get("google_calendar", sources.get("google", {}))
        return bool(cfg.get("access_token"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        cfg = sources.get("google_calendar", sources.get("google", {}))
        return {
            "access_token": cfg.get("access_token", ""),
            "calendar_id": "primary",
            "time_min": "",
            "time_max": "",
            "query": "",
            "attendee_email": "",
            "max_results": 50,
        }

    def run(
        self,
        access_token: str = "",
        calendar_id: str = "primary",
        time_min: str = "",
        time_max: str = "",
        query: str = "",
        attendee_email: str = "",
        max_results: int = 50,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not access_token:
            return {
                "source": "google_calendar",
                "available": False,
                "error": "access_token is required.",
            }

        client = make_google_calendar_client(access_token=access_token)
        if client is None:
            return {
                "source": "google_calendar",
                "available": False,
                "error": "Could not create Google Calendar client.",
            }

        try:
            with client:
                if attendee_email:
                    events = client.find_meetings_between(
                        calendar_id=calendar_id,
                        attendee_email=attendee_email,
                        time_min=time_min or None,
                        time_max=time_max or None,
                        max_results=max_results,
                    )
                    return {
                        "source": "google_calendar",
                        "available": True,
                        "calendar_id": calendar_id,
                        "attendee_filter": attendee_email,
                        "events": events,
                        "returned_count": len(events),
                    }
                else:
                    result = client.list_events(
                        calendar_id=calendar_id,
                        time_min=time_min or None,
                        time_max=time_max or None,
                        query=query or None,
                        max_results=max_results,
                    )
                    return {
                        "source": "google_calendar",
                        "available": True,
                        "calendar_id": result["calendar_id"],
                        "events": result["events"],
                        "returned_count": len(result["events"]),
                    }
        except Exception as exc:
            return {"source": "google_calendar", "available": False, "error": str(exc)}


search_google_calendar = GoogleCalendarTool()
