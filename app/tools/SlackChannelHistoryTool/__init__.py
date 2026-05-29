"""Slack channel history tool — read recent messages from a specific channel."""

from __future__ import annotations

from typing import Any

from app.services.slack import make_slack_client
from app.tools.base import BaseTool


class SlackChannelHistoryTool(BaseTool):
    """Fetch recent messages from a specific Slack channel for timeline correlation."""

    name = "slack_channel_history"
    source = "slack"
    description = (
        "Fetch recent messages from a specific Slack channel. Use this after identifying "
        "the relevant channel (e.g. #incidents, #alerts, #eng-ops) to pull a timeline of "
        "discussion around the incident window."
    )
    use_cases = [
        "Reading the #incidents or #alerts channel to see engineer response timeline",
        "Fetching ops channel messages during the alert window for correlation",
        "Getting channel history to identify when an issue was first noticed by the team",
        "Pulling deployment or release channel messages to find triggering changes",
    ]
    requires = ["bot_token", "channel_id"]
    input_schema = {
        "type": "object",
        "properties": {
            "bot_token": {
                "type": "string",
                "description": "Slack bot token with channels:history scope",
            },
            "channel_id": {
                "type": "string",
                "description": "Slack channel ID (e.g. C1234567890). Use list_channels to find it.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of messages to fetch",
                "default": 50,
            },
            "oldest": {
                "type": "string",
                "description": "Start of time window as Unix timestamp (e.g. '1704067200')",
                "default": "",
            },
            "latest": {
                "type": "string",
                "description": "End of time window as Unix timestamp",
                "default": "",
            },
        },
        "required": ["bot_token", "channel_id"],
    }
    outputs = {
        "messages": "List of messages with text, user, timestamp, and reactions",
        "has_more": "Whether more messages exist beyond the returned window",
    }

    def is_available(self, sources: dict) -> bool:
        return bool(sources.get("slack", {}).get("connection_verified"))

    def extract_params(self, sources: dict) -> dict[str, Any]:
        slack = sources.get("slack", {})
        return {
            "bot_token": slack.get("bot_token", ""),
            "channel_id": slack.get("default_channel", ""),
            "limit": 50,
            "oldest": "",
            "latest": "",
        }

    def run(
        self,
        bot_token: str,
        channel_id: str,
        limit: int = 50,
        oldest: str = "",
        latest: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not channel_id:
            return {"source": "slack", "available": False, "error": "channel_id is required."}

        client = make_slack_client(bot_token)
        if client is None:
            return {"source": "slack", "available": False, "error": "Slack is not configured."}

        with client:
            result = client.channel_history(
                channel_id=channel_id, limit=limit, oldest=oldest, latest=latest
            )

        if not result.get("success"):
            return {"source": "slack", "available": False, "error": result.get("error", "unknown")}
        return {
            "source": "slack",
            "available": True,
            "channel_id": channel_id,
            "messages": result.get("messages", []),
            "has_more": result.get("has_more", False),
        }


slack_channel_history = SlackChannelHistoryTool()
