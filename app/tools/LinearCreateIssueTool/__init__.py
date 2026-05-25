"""Linear create-issue tool — file an incident ticket from RCA findings."""

from __future__ import annotations

from typing import Any

from app.services.linear import make_linear_client
from app.tools.base import BaseTool

_PRIORITY_MAP = {"urgent": 1, "high": 2, "medium": 3, "low": 4, "none": 0}


class LinearCreateIssueTool(BaseTool):
    """Create a Linear issue from RCA findings — for full incident documentation and tracking."""

    name = "linear_create_issue"
    source = "linear"
    description = (
        "Create a new Linear issue from the investigation findings. Use this as the final "
        "step to file an incident ticket with the root cause, causal chain, and remediation "
        "steps, so the engineering team can track the fix and prevent recurrence."
    )
    use_cases = [
        "Filing a Linear incident ticket after diagnosing the root cause",
        "Creating a follow-up engineering issue from the remediation steps",
        "Ensuring the on-call finding is tracked as a formal engineering issue",
        "Linking the production incident to a team's backlog for follow-up",
    ]
    requires = ["api_key", "team_id", "title"]
    input_schema = {
        "type": "object",
        "properties": {
            "api_key": {"type": "string", "description": "Linear API key"},
            "team_id": {
                "type": "string",
                "description": "Linear team ID. Use linear_search_issues and check issue.team or call list_teams first.",
            },
            "title": {
                "type": "string",
                "description": "Issue title (concise summary of the incident)",
            },
            "description": {
                "type": "string",
                "description": "Full issue description in Markdown — paste root cause and remediation steps here",
                "default": "",
            },
            "priority": {
                "type": "string",
                "description": "Priority: urgent, high, medium, low, none",
                "enum": ["urgent", "high", "medium", "low", "none"],
                "default": "high",
            },
        },
        "required": ["api_key", "team_id", "title"],
    }
    outputs = {
        "identifier": "Linear issue identifier (e.g. ENG-123)",
        "url": "URL to the created issue",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(sources.get("linear", {}).get("connection_verified"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        linear = sources.get("linear", {})
        return {
            "api_key": linear.get("api_key", ""),
            "team_id": linear.get("default_team_id", ""),
            "title": "",
            "description": "",
            "priority": "high",
        }

    def run(
        self,
        api_key: str,
        team_id: str,
        title: str,
        description: str = "",
        priority: str = "high",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not team_id:
            return {"source": "linear", "available": False, "error": "team_id is required."}
        if not title:
            return {"source": "linear", "available": False, "error": "title is required."}

        client = make_linear_client(api_key)
        if client is None:
            return {"source": "linear", "available": False, "error": "Linear is not configured."}

        priority_int = _PRIORITY_MAP.get(priority.lower(), 2)
        with client:
            result = client.create_issue(
                title=title,
                description=description,
                team_id=team_id,
                priority=priority_int,
            )

        if not result.get("success"):
            return {"source": "linear", "available": False, "error": result.get("error", "unknown")}
        return {
            "source": "linear",
            "available": True,
            "identifier": result.get("identifier", ""),
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "id": result.get("id", ""),
        }


linear_create_issue = LinearCreateIssueTool()
