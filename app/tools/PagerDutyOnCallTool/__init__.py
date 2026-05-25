"""PagerDuty on-call tool — who is on-call right now and across schedules."""

from __future__ import annotations

from typing import Any

from app.services.pagerduty import make_pagerduty_client
from app.tools.base import BaseTool


class PagerDutyOnCallTool(BaseTool):
    """Retrieve who is currently on-call from PagerDuty schedules and escalation policies."""

    name = "pagerduty_oncall"
    source = "pagerduty"
    description = (
        "Fetch the current on-call roster from PagerDuty. Useful during incident investigation "
        "to know who should be notified or who is actively managing the alert."
    )
    use_cases = [
        "Finding who is on-call for a specific service or team",
        "Listing all current on-call engineers across schedules",
        "Correlating incident ownership with on-call assignments",
        "Identifying escalation paths during an active investigation",
    ]
    requires = ["api_token"]
    input_schema = {
        "type": "object",
        "properties": {
            "api_token": {"type": "string", "description": "PagerDuty API token"},
            "from_email": {"type": "string", "description": "Email for From header", "default": ""},
            "schedule_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of schedule IDs to filter. Leave empty for all.",
                "default": [],
            },
            "limit": {
                "type": "integer",
                "description": "Max on-call entries to return",
                "default": 20,
            },
        },
        "required": ["api_token"],
    }
    outputs = {
        "oncalls": "List of on-call entries: user, email, schedule, escalation_policy, level, start, end",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(sources.get("pagerduty", {}).get("connection_verified"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        pd = sources.get("pagerduty", {})
        return {
            "api_token": pd.get("api_token", ""),
            "from_email": pd.get("from_email", ""),
            "schedule_ids": [],
            "limit": 20,
        }

    def run(
        self,
        api_token: str,
        from_email: str = "",
        schedule_ids: list[str] | None = None,
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
            result = client.get_oncall(schedule_ids=schedule_ids or [], limit=limit)

        if not result.get("success"):
            return {
                "source": "pagerduty",
                "available": False,
                "error": result.get("error", "unknown"),
            }
        return {"source": "pagerduty", "available": True, "oncalls": result.get("oncalls", [])}


pagerduty_oncall = PagerDutyOnCallTool()
