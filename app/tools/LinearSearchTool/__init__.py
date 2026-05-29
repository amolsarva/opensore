"""Linear issue search tool — find existing incidents and engineering issues during investigation."""

from __future__ import annotations

from typing import Any

from app.services.linear import make_linear_client
from app.tools.base import BaseTool


class LinearSearchTool(BaseTool):
    """Search Linear issues for existing incident reports, bugs, or known issues."""

    name = "linear_search_issues"
    source = "linear"
    description = (
        "Search Linear for existing issues related to the current incident. "
        "Use this to find any known bugs, open incidents, or engineering tickets "
        "that may already describe the root cause or a prior occurrence."
    )
    use_cases = [
        "Finding existing Linear tickets that describe the same failure",
        "Checking whether the service team is already aware of the issue",
        "Locating prior incidents for the same service or component",
        "Linking the current investigation to an open engineering issue",
        "Finding related bugs that may have contributed to the failure",
    ]
    requires = ["api_key"]
    input_schema = {
        "type": "object",
        "properties": {
            "api_key": {"type": "string", "description": "Linear API key"},
            "query": {
                "type": "string",
                "description": "Search query — service name, error message, or symptom description",
            },
            "limit": {"type": "integer", "description": "Max issues to return", "default": 10},
        },
        "required": ["api_key", "query"],
    }
    outputs = {
        "issues": "List of matching issues with identifier, title, state, team, url, and description",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(sources.get("linear", {}).get("connection_verified"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        linear = sources.get("linear", {})
        return {"api_key": linear.get("api_key", ""), "query": "", "limit": 10}

    def run(self, api_key: str, query: str, limit: int = 10, **_kwargs: Any) -> dict[str, Any]:
        if not query:
            return {"source": "linear", "available": False, "error": "query is required."}
        client = make_linear_client(api_key)
        if client is None:
            return {"source": "linear", "available": False, "error": "Linear is not configured."}
        with client:
            result = client.search_issues(query=query, limit=limit)
        if not result.get("success"):
            return {"source": "linear", "available": False, "error": result.get("error", "unknown")}
        return {
            "source": "linear",
            "available": True,
            "query": query,
            "issues": result.get("issues", []),
            "total": result.get("total", 0),
        }


linear_search_issues = LinearSearchTool()
