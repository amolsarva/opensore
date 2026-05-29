"""Microsoft Teams message search tool for HR/legal investigation workflows."""

from __future__ import annotations

from typing import Any

from app.services.microsoft_teams import make_teams_client
from app.tools.base import BaseTool


class TeamsSearchTool(BaseTool):
    """Search Microsoft Teams channel and chat messages for HR/legal investigations.

    Supports searching across team channels and 1:1/group chats using keyword
    filters and date ranges via the Microsoft Graph API.
    """

    name = "search_teams_messages"
    source = "teams"
    description = (
        "Search Microsoft Teams channel messages and direct chats for content relevant to "
        "HR/legal investigations. Retrieves messages by keyword, sender, date range, or "
        "channel context. Returns message text, sender, timestamp, and direct links."
    )
    use_cases = [
        "Finding Teams messages between a complainant and the accused",
        "Searching a team channel for discussion of a specific incident or project",
        "Locating messages referencing harassment, retaliation, or policy violations",
        "Building a timeline of communication from Teams messages during an event window",
        "Identifying which team members were aware of an incident via group chat",
        "Retrieving direct message history between two employees for a specified date range",
    ]
    requires = ["access_token|tenant_id+client_id+client_secret"]
    input_schema = {
        "type": "object",
        "properties": {
            "access_token": {
                "type": "string",
                "description": "OAuth2 bearer token with ChannelMessage.Read.All scope",
            },
            "tenant_id": {
                "type": "string",
                "description": "Azure tenant ID (for client credentials flow)",
            },
            "client_id": {
                "type": "string",
                "description": "Azure app client ID (for client credentials flow)",
            },
            "client_secret": {
                "type": "string",
                "description": "Azure app client secret (for client credentials flow)",
            },
            "team_id": {
                "type": "string",
                "description": "Team (group) GUID to search. Required for channel search.",
            },
            "channel_id": {
                "type": "string",
                "description": "Channel GUID to search. Required for channel search.",
            },
            "chat_id": {
                "type": "string",
                "description": "Chat thread ID for direct/group chat search.",
            },
            "top": {
                "type": "integer",
                "description": "Number of messages to return (max 50 per request)",
                "default": 50,
            },
            "filter_expr": {
                "type": "string",
                "description": (
                    "OData filter expression, e.g. "
                    "'createdDateTime ge 2024-01-01T00:00:00Z and "
                    "createdDateTime le 2024-06-30T23:59:59Z'"
                ),
            },
        },
        "required": [],
    }
    outputs = {
        "messages": "List of messages: id, sender, body_text, created_at, web_url",
        "team_id": "Team GUID if channel search was performed",
        "channel_id": "Channel GUID if channel search was performed",
        "chat_id": "Chat ID if direct chat search was performed",
    }

    def is_available(self, sources: dict) -> bool:
        cfg = sources.get("teams", sources.get("microsoft_teams", {}))
        has_token = bool(cfg.get("access_token"))
        has_creds = bool(cfg.get("tenant_id") and cfg.get("client_id") and cfg.get("client_secret"))
        return has_token or has_creds

    def extract_params(self, sources: dict) -> dict[str, Any]:
        cfg = sources.get("teams", sources.get("microsoft_teams", {}))
        return {
            "access_token": cfg.get("access_token", ""),
            "tenant_id": cfg.get("tenant_id", ""),
            "client_id": cfg.get("client_id", ""),
            "client_secret": cfg.get("client_secret", ""),
            "team_id": "",
            "channel_id": "",
            "chat_id": "",
            "top": 50,
            "filter_expr": "",
        }

    def run(
        self,
        access_token: str = "",
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        team_id: str = "",
        channel_id: str = "",
        chat_id: str = "",
        top: int = 50,
        filter_expr: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not (team_id and channel_id) and not chat_id:
            return {
                "source": "teams",
                "available": False,
                "error": (
                    "Provide team_id + channel_id for channel search, "
                    "or chat_id for direct/group chat search."
                ),
            }

        client = make_teams_client(
            access_token=access_token or None,
            tenant_id=tenant_id or None,
            client_id=client_id or None,
            client_secret=client_secret or None,
        )
        if client is None:
            return {
                "source": "teams",
                "available": False,
                "error": (
                    "Teams credentials not configured. "
                    "Provide access_token or tenant_id + client_id + client_secret."
                ),
            }

        try:
            with client:
                if chat_id:
                    result = client.list_chat_messages(chat_id=chat_id, top=top)
                    return {
                        "source": "teams",
                        "available": True,
                        "chat_id": result["chat_id"],
                        "messages": result["messages"],
                        "returned_count": len(result["messages"]),
                    }
                else:
                    result = client.list_channel_messages(
                        team_id=team_id,
                        channel_id=channel_id,
                        top=top,
                        filter_expr=filter_expr or None,
                    )
                    return {
                        "source": "teams",
                        "available": True,
                        "team_id": result["team_id"],
                        "channel_id": result["channel_id"],
                        "messages": result["messages"],
                        "returned_count": len(result["messages"]),
                    }
        except Exception as exc:
            return {"source": "teams", "available": False, "error": str(exc)}


search_teams_messages = TeamsSearchTool()
