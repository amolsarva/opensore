"""Slack full-text search tool — query Slack messages during investigation."""

from __future__ import annotations

from typing import Any

from app.services.slack import make_slack_client
from app.tools.base import BaseTool


class SlackSearchTool(BaseTool):
    """Search Slack messages for incident discussion, error reports, and on-call chatter."""

    name = "slack_search_messages"
    source = "slack"
    description = (
        "Full-text search across Slack to find messages related to the current incident. "
        "Useful for finding engineer discussions, error reports pasted into channels, "
        "deployment announcements, or prior mentions of the affected service."
    )
    use_cases = [
        "Finding Slack discussion about the affected service or host during the incident window",
        "Searching for error messages or stack traces shared in engineering channels",
        "Locating deployment announcements that may have triggered the alert",
        "Finding prior mentions of the same issue to detect recurring failures",
        "Identifying which team is actively discussing or working on the problem",
    ]
    requires = ["bot_token"]
    input_schema = {
        "type": "object",
        "properties": {
            "bot_token": {
                "type": "string",
                "description": "Slack bot token with search:read scope",
            },
            "query": {
                "type": "string",
                "description": "Search query — use Slack search modifiers like 'in:#channel', 'from:@user', or 'after:YYYY-MM-DD'",
            },
            "count": {
                "type": "integer",
                "description": "Maximum number of messages to return",
                "default": 20,
            },
            "sort": {
                "type": "string",
                "description": "Sort order: 'timestamp' (newest first) or 'score' (relevance)",
                "enum": ["timestamp", "score"],
                "default": "timestamp",
            },
        },
        "required": ["bot_token", "query"],
    }
    outputs = {
        "messages": "List of matching messages with text, user, channel, permalink, and timestamp",
        "total": "Total number of matching messages across all channels",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(sources.get("slack", {}).get("connection_verified"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        slack = sources.get("slack", {})
        return {
            "bot_token": slack.get("bot_token", ""),
            "query": "",
            "count": 20,
            "sort": "timestamp",
        }

    def run(
        self,
        bot_token: str,
        query: str,
        count: int = 20,
        sort: str = "timestamp",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not query:
            return {"source": "slack", "available": False, "error": "query is required."}

        client = make_slack_client(bot_token)
        if client is None:
            return {"source": "slack", "available": False, "error": "Slack is not configured."}

        with client:
            result = client.search_messages(query=query, count=count, sort=sort)

        if not result.get("success"):
            return {"source": "slack", "available": False, "error": result.get("error", "unknown")}
        return {
            "source": "slack",
            "available": True,
            "query": query,
            "messages": result.get("messages", []),
            "total": result.get("total", 0),
        }


slack_search_messages = SlackSearchTool()
