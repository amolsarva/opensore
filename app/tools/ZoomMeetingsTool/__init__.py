"""Zoom meeting records tool for HR/legal investigation workflows."""

from __future__ import annotations

from typing import Any

from app.services.zoom import make_zoom_client
from app.tools.base import BaseTool


class ZoomMeetingsTool(BaseTool):
    """Retrieve Zoom meeting records and participant lists for HR/legal investigations.

    Supports listing past meetings for a user, fetching full meeting details,
    and retrieving participant reports showing who attended a specific meeting.
    """

    name = "search_zoom_meetings"
    source = "zoom"
    description = (
        "Search Zoom meeting history and participant records for HR/legal investigations. "
        "Lists past meetings for a user, retrieves attendee lists for specific meetings, "
        "and returns meeting metadata including host, timing, and join details. "
        "Use to establish who attended a meeting or identify undisclosed private meetings."
    )
    use_cases = [
        "Verifying whether a complainant and accused were in a private Zoom meeting",
        "Retrieving the participant list for a meeting where an incident allegedly occurred",
        "Identifying recurring private meetings between a manager and a direct report",
        "Confirming a subject's meeting history during a specific incident window",
        "Determining whether a meeting was recorded and whether recordings may exist",
        "Checking whether an employee attended a mandatory training or all-hands meeting",
    ]
    requires = ["access_token|account_id+client_id+client_secret"]
    input_schema = {
        "type": "object",
        "properties": {
            "access_token": {
                "type": "string",
                "description": "OAuth2 bearer token for Zoom API",
            },
            "account_id": {
                "type": "string",
                "description": "Zoom account ID (for Server-to-Server OAuth)",
            },
            "client_id": {
                "type": "string",
                "description": "Zoom OAuth app client ID",
            },
            "client_secret": {
                "type": "string",
                "description": "Zoom OAuth app client secret",
            },
            "user_id": {
                "type": "string",
                "description": "Zoom user ID or email to look up meetings for",
            },
            "meeting_id": {
                "type": "string",
                "description": "Specific meeting ID to retrieve details and participants for",
            },
            "from_date": {
                "type": "string",
                "description": "Start date for meeting history (YYYY-MM-DD)",
            },
            "to_date": {
                "type": "string",
                "description": "End date for meeting history (YYYY-MM-DD)",
            },
            "include_participants": {
                "type": "boolean",
                "description": "Fetch participant list for each meeting (requires report:read:admin)",
                "default": False,
            },
            "page_size": {
                "type": "integer",
                "description": "Number of meetings to return (default: 30)",
                "default": 30,
            },
        },
        "required": [],
    }
    outputs = {
        "meetings": "List of meeting summaries: id, topic, host, start_time, duration",
        "participants": "Participant list when include_participants=true or meeting_id is used",
        "meeting_detail": "Full meeting details when meeting_id is specified",
        "returned_count": "Number of meetings returned",
    }

    def is_available(self, sources: dict) -> bool:
        cfg = sources.get("zoom", {})
        has_token = bool(cfg.get("access_token"))
        has_creds = bool(
            cfg.get("account_id") and cfg.get("client_id") and cfg.get("client_secret")
        )
        return has_token or has_creds

    def extract_params(self, sources: dict) -> dict[str, Any]:
        cfg = sources.get("zoom", {})
        return {
            "access_token": cfg.get("access_token", ""),
            "account_id": cfg.get("account_id", ""),
            "client_id": cfg.get("client_id", ""),
            "client_secret": cfg.get("client_secret", ""),
            "user_id": "",
            "meeting_id": "",
            "from_date": "",
            "to_date": "",
            "include_participants": False,
            "page_size": 30,
        }

    def run(
        self,
        access_token: str = "",
        account_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        user_id: str = "",
        meeting_id: str = "",
        from_date: str = "",
        to_date: str = "",
        include_participants: bool = False,
        page_size: int = 30,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not user_id and not meeting_id:
            return {
                "source": "zoom",
                "available": False,
                "error": "Provide user_id to list meetings or meeting_id to get meeting details.",
            }

        zoom = make_zoom_client(
            access_token=access_token or None,
            account_id=account_id or None,
            client_id=client_id or None,
            client_secret=client_secret or None,
        )
        if zoom is None:
            return {
                "source": "zoom",
                "available": False,
                "error": "Zoom credentials not configured. Provide access_token or account_id + client_id + client_secret.",
            }

        try:
            with zoom:
                if meeting_id and not user_id:
                    detail = zoom.get_meeting(meeting_id)
                    participants = zoom.get_meeting_participants(meeting_id)
                    return {
                        "source": "zoom",
                        "available": True,
                        "meeting_id": meeting_id,
                        "meeting_detail": detail,
                        "participants": participants["participants"],
                        "participant_count": participants["total_records"],
                    }

                result = zoom.list_user_meetings(
                    user_id=user_id,
                    page_size=page_size,
                    from_date=from_date or None,
                    to_date=to_date or None,
                )
                meetings = result["meetings"]

                if include_participants and meetings:
                    for meeting in meetings:
                        try:
                            p = zoom.get_meeting_participants(meeting["id"])
                            meeting["participants"] = p["participants"]
                        except Exception:
                            meeting["participants"] = []

                return {
                    "source": "zoom",
                    "available": True,
                    "user_id": user_id,
                    "meetings": meetings,
                    "returned_count": len(meetings),
                    "total_records": result["total_records"],
                }
        except Exception as exc:
            return {"source": "zoom", "available": False, "error": str(exc)}


search_zoom_meetings = ZoomMeetingsTool()
