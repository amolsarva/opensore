"""Slack Web API client for investigation tool use (search, channel history, user lookup).

Distinct from slack_delivery.py which handles outbound report posting.
This client focuses on *reading* Slack data during investigations.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.probes import ProbeResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://slack.com/api"
_DEFAULT_TIMEOUT = 20


class SlackClient:
    """Read-only Slack Web API client for searching messages and channel history."""

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token.strip()
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                timeout=_DEFAULT_TIMEOUT,
            )
        return self._client

    @property
    def is_configured(self) -> bool:
        return bool(self._token)

    def probe_access(self) -> ProbeResult:
        if not self.is_configured:
            return ProbeResult.missing("Missing Slack bot token.")
        with self:
            result = self.list_channels(limit=1)
        if not result.get("success"):
            return ProbeResult.failed(f"Slack probe failed: {result.get('error', 'unknown')}")
        return ProbeResult.passed("Connected to Slack API; bot token accepted.")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> SlackClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _check_ok(self, data: dict[str, Any]) -> tuple[bool, str]:
        if data.get("ok"):
            return True, ""
        return False, str(data.get("error", "unknown_error"))

    def search_messages(
        self,
        query: str,
        count: int = 20,
        sort: str = "timestamp",
    ) -> dict[str, Any]:
        """Full-text search across all Slack messages the bot can access.

        Requires ``search:read`` scope.
        """
        try:
            resp = self._get_client().get(
                "/search.messages",
                params={"query": query, "count": min(count, 100), "sort": sort},
            )
            resp.raise_for_status()
            data = resp.json()
            ok, error = self._check_ok(data)
            if not ok:
                return {"success": False, "error": error, "messages": []}

            raw_messages = data.get("messages", {}).get("matches", [])
            messages = [
                {
                    "ts": m.get("ts", ""),
                    "text": m.get("text", ""),
                    "user": m.get("username", "") or m.get("user", ""),
                    "channel": m.get("channel", {}).get("name", ""),
                    "channel_id": m.get("channel", {}).get("id", ""),
                    "permalink": m.get("permalink", ""),
                    "isoformat": _ts_to_iso(m.get("ts", "")),
                }
                for m in raw_messages
            ]
            return {
                "success": True,
                "query": query,
                "messages": messages,
                "total": data.get("messages", {}).get("total", len(messages)),
            }
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}"
            logger.warning("[slack] search_messages error: %s", error)
            return {"success": False, "error": error, "messages": []}
        except Exception as exc:
            logger.warning("[slack] search_messages exception: %s", exc)
            return {"success": False, "error": str(exc), "messages": []}

    def channel_history(
        self,
        channel_id: str,
        limit: int = 50,
        oldest: str = "",
        latest: str = "",
    ) -> dict[str, Any]:
        """Fetch recent messages from a channel.

        Requires ``channels:history`` (public) or ``groups:history`` (private) scope.
        """
        params: dict[str, Any] = {"channel": channel_id, "limit": min(limit, 200)}
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest

        try:
            resp = self._get_client().get("/conversations.history", params=params)
            resp.raise_for_status()
            data = resp.json()
            ok, error = self._check_ok(data)
            if not ok:
                return {"success": False, "error": error, "messages": []}

            messages = [
                {
                    "ts": m.get("ts", ""),
                    "text": m.get("text", ""),
                    "user": m.get("user", ""),
                    "type": m.get("type", "message"),
                    "isoformat": _ts_to_iso(m.get("ts", "")),
                    "reactions": [r.get("name", "") for r in m.get("reactions", [])],
                }
                for m in data.get("messages", [])
                if m.get("type") == "message" and not m.get("subtype")
            ]
            return {
                "success": True,
                "channel_id": channel_id,
                "messages": messages,
                "has_more": data.get("has_more", False),
            }
        except Exception as exc:
            logger.warning("[slack] channel_history exception: %s", exc)
            return {"success": False, "error": str(exc), "messages": []}

    def list_channels(self, limit: int = 100, exclude_archived: bool = True) -> dict[str, Any]:
        """List public channels the bot is a member of."""
        params: dict[str, Any] = {
            "limit": min(limit, 1000),
            "exclude_archived": str(exclude_archived).lower(),
            "types": "public_channel",
        }
        try:
            resp = self._get_client().get("/conversations.list", params=params)
            resp.raise_for_status()
            data = resp.json()
            ok, error = self._check_ok(data)
            if not ok:
                return {"success": False, "error": error, "channels": []}
            channels = [
                {
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "is_member": c.get("is_member", False),
                    "num_members": c.get("num_members", 0),
                    "topic": c.get("topic", {}).get("value", ""),
                    "purpose": c.get("purpose", {}).get("value", ""),
                }
                for c in data.get("channels", [])
            ]
            return {"success": True, "channels": channels}
        except Exception as exc:
            logger.warning("[slack] list_channels exception: %s", exc)
            return {"success": False, "error": str(exc), "channels": []}


def _ts_to_iso(ts: str) -> str:
    """Convert a Slack timestamp (unix seconds) to an ISO 8601 string."""
    if not ts:
        return ""
    try:
        from datetime import UTC, datetime

        seconds = float(ts.split(".")[0])
        return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
    except Exception:
        return ts


def make_slack_client(bot_token: str | None) -> SlackClient | None:
    token = (bot_token or "").strip()
    if not token:
        return None
    return SlackClient(bot_token=token)
