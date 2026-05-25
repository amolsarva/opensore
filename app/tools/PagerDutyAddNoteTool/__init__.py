"""PagerDuty add-note tool — write RCA findings back to an incident."""

from __future__ import annotations

from typing import Any

from app.services.pagerduty import make_pagerduty_client
from app.tools.base import BaseTool


class PagerDutyAddNoteTool(BaseTool):
    """Append a note to a PagerDuty incident — for writing RCA findings back to the incident record."""

    name = "pagerduty_add_note"
    source = "pagerduty"
    description = (
        "Add a note to a PagerDuty incident. Use this as the final step after investigation "
        "to write the root cause analysis and remediation steps directly into the PagerDuty "
        "incident timeline for full audit trail."
    )
    use_cases = [
        "Writing RCA findings directly into a PagerDuty incident",
        "Attaching remediation steps to an ongoing incident record",
        "Creating an audit trail of the investigation within PagerDuty",
        "Updating incident notes with root cause category and confidence score",
    ]
    requires = ["api_token", "incident_id", "content"]
    input_schema = {
        "type": "object",
        "properties": {
            "api_token": {"type": "string", "description": "PagerDuty API token"},
            "from_email": {
                "type": "string",
                "description": "Email of the user adding the note (required by PagerDuty API)",
            },
            "incident_id": {
                "type": "string",
                "description": "PagerDuty incident ID to add the note to",
            },
            "content": {
                "type": "string",
                "description": "Note content — the RCA summary, root cause, and remediation steps",
            },
        },
        "required": ["api_token", "from_email", "incident_id", "content"],
    }
    outputs = {
        "note_id": "ID of the created note",
        "created_at": "Timestamp when the note was created",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(sources.get("pagerduty", {}).get("connection_verified"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        pd = sources.get("pagerduty", {})
        return {
            "api_token": pd.get("api_token", ""),
            "from_email": pd.get("from_email", ""),
            "incident_id": "",
            "content": "",
        }

    def run(
        self,
        api_token: str,
        from_email: str,
        incident_id: str,
        content: str,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not incident_id:
            return {"source": "pagerduty", "available": False, "error": "incident_id is required."}
        if not content:
            return {"source": "pagerduty", "available": False, "error": "content is required."}

        client = make_pagerduty_client(api_token, from_email)
        if client is None:
            return {
                "source": "pagerduty",
                "available": False,
                "error": "PagerDuty is not configured.",
            }

        with client:
            result = client.add_note(incident_id, content)

        if not result.get("success"):
            return {
                "source": "pagerduty",
                "available": False,
                "error": result.get("error", "unknown"),
            }
        return {
            "source": "pagerduty",
            "available": True,
            "note_id": result.get("note_id", ""),
            "created_at": result.get("created_at", ""),
            "incident_id": incident_id,
        }


pagerduty_add_note = PagerDutyAddNoteTool()
