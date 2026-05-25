"""PagerDuty incidents tool — list and fetch active incidents during investigation."""

from __future__ import annotations

from typing import Any

from app.services.pagerduty import make_pagerduty_client
from app.tools.base import BaseTool


class PagerDutyIncidentsTool(BaseTool):
    """List and retrieve active PagerDuty incidents relevant to the current investigation."""

    name = "pagerduty_incidents"
    source = "pagerduty"
    description = (
        "List active or recent PagerDuty incidents and fetch full details for a specific incident. "
        "Use this to correlate the current alert with any open PagerDuty incidents, check status, "
        "assignees, and affected services."
    )
    use_cases = [
        "Checking if the current alert matches an open PagerDuty incident",
        "Listing triggered or acknowledged incidents for a specific service",
        "Fetching full incident details including body and alert counts",
        "Correlating infrastructure alerts with on-call incident timelines",
    ]
    requires = ["api_token"]
    input_schema = {
        "type": "object",
        "properties": {
            "api_token": {"type": "string", "description": "PagerDuty API token"},
            "from_email": {
                "type": "string",
                "description": "Email address used as From header (required for note writes)",
                "default": "",
            },
            "incident_id": {
                "type": "string",
                "description": "Fetch details for a specific incident ID. Leave empty to list.",
                "default": "",
            },
            "statuses": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by status: triggered, acknowledged, resolved",
                "default": ["triggered", "acknowledged"],
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of incidents to return",
                "default": 20,
            },
        },
        "required": ["api_token"],
    }
    outputs = {
        "incidents": "List of active incidents with id, title, status, urgency, service, assignments",
        "incident": "Full incident details when incident_id is provided",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(sources.get("pagerduty", {}).get("connection_verified"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        pd = sources.get("pagerduty", {})
        return {
            "api_token": pd.get("api_token", ""),
            "from_email": pd.get("from_email", ""),
            "incident_id": "",
            "statuses": ["triggered", "acknowledged"],
            "limit": 20,
        }

    def run(
        self,
        api_token: str,
        from_email: str = "",
        incident_id: str = "",
        statuses: list[str] | None = None,
        limit: int = 20,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        client = make_pagerduty_client(api_token, from_email)
        if client is None:
            return {
                "source": "pagerduty",
                "available": False,
                "error": "PagerDuty is not configured.",
            }

        with client:
            if incident_id:
                result = client.get_incident(incident_id)
                if not result.get("success"):
                    return {
                        "source": "pagerduty",
                        "available": False,
                        "error": result.get("error", "unknown"),
                    }
                return {"source": "pagerduty", "available": True, **result}

            result = client.list_incidents(statuses=statuses, limit=limit)

        if not result.get("success"):
            return {
                "source": "pagerduty",
                "available": False,
                "error": result.get("error", "unknown"),
            }
        return {
            "source": "pagerduty",
            "available": True,
            "incidents": result.get("incidents", []),
            "total": result.get("total", 0),
        }


pagerduty_incidents = PagerDutyIncidentsTool()
