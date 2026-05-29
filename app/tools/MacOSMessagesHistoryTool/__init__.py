"""macOS Messages (iMessage/SMS) history tool — reads chat.db."""

from __future__ import annotations

from typing import Any

from app.services.macos_device.client import read_messages_history
from app.tools.base import BaseTool


class MacOSMessagesHistoryTool(BaseTool):
    """Read iMessage and SMS history from the local macOS Messages database.

    Reads ~/Library/Messages/chat.db (SQLite). Requires Full Disk Access
    permission. All access is read-only.
    """

    name = "read_macos_messages_history"
    source = "local_device"
    description = (
        "Read local iMessage and SMS conversation history from the macOS Messages app "
        "(chat.db) for HR/legal forensics. Returns message text, timestamps, sender, "
        "and chat context. Requires Full Disk Access. Read-only."
    )
    use_cases = [
        "Recovering iMessage conversations between parties in a workplace harassment investigation",
        "Finding SMS evidence of threats, coercion, or inappropriate contact",
        "Establishing a timeline of personal communications outside corporate channels",
        "Identifying contact attempts made from a personal device during an investigation period",
        "Documenting the frequency and timing of private communications between two individuals",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "contact_filter": {
                "type": "string",
                "description": "Phone number, email, or name substring to filter messages by contact.",
            },
            "after_iso": {
                "type": "string",
                "description": "ISO-8601 datetime; only return messages after this time.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of messages to return (default: 200).",
                "default": 200,
            },
        },
    }
    outputs = {
        "available": "Whether chat.db was accessible",
        "messages": "List of messages with text, timestamp, direction, contact, chat_name, service",
        "total": "Total messages returned",
    }

    def is_available(self, _sources: dict) -> bool:
        return True

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {"limit": 200}

    def run(
        self,
        contact_filter: str | None = None,
        after_iso: str | None = None,
        limit: int = 200,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        try:
            messages = read_messages_history(
                contact_filter=contact_filter,
                limit=limit,
                after_iso=after_iso,
            )
            return {
                "source": "local_device",
                "available": True,
                "messages": messages,
                "total": len(messages),
                "note": "Requires Full Disk Access in System Settings → Privacy & Security.",
            }
        except Exception as exc:
            return {"source": "local_device", "available": False, "error": str(exc)}


read_macos_messages_history = MacOSMessagesHistoryTool()
