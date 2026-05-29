"""Microsoft Teams client via the Microsoft Graph API.

Authentication: OAuth2 bearer token with the following scopes:
  - ChannelMessage.Read.All (application or delegated)
  - Chat.Read.All / Chat.ReadBasic.All
  - User.Read.All (for resolving display names)

Token acquisition (client credentials flow for app auth):
    POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token

Reference: https://learn.microsoft.com/graph/teams-concept-overview
"""

from __future__ import annotations

from typing import Any

import requests


class TeamsClient:
    """HTTP wrapper around the Microsoft Graph API for Teams data."""

    _GRAPH = "https://graph.microsoft.com/v1.0"

    def __init__(self, access_token: str) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Channel messages
    # ------------------------------------------------------------------

    def list_channel_messages(
        self,
        team_id: str,
        channel_id: str,
        top: int = 50,
        filter_expr: str | None = None,
    ) -> dict[str, Any]:
        """Return recent messages from a Teams channel.

        Args:
            team_id: The team (group) GUID
            channel_id: The channel GUID
            top: Number of messages to return (max 50 per page)
            filter_expr: OData filter (e.g. ``createdDateTime ge 2024-01-01T00:00:00Z``)
        """
        url = f"{self._GRAPH}/teams/{team_id}/channels/{channel_id}/messages"
        params: dict[str, Any] = {"$top": min(top, 50), "$orderby": "createdDateTime desc"}
        if filter_expr:
            params["$filter"] = filter_expr

        resp = self._session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("value", [])
        return {
            "messages": [self._parse_channel_message(m) for m in raw],
            "team_id": team_id,
            "channel_id": channel_id,
        }

    # ------------------------------------------------------------------
    # Chat messages (1:1 and group chats)
    # ------------------------------------------------------------------

    def list_chat_messages(
        self,
        chat_id: str,
        top: int = 50,
    ) -> dict[str, Any]:
        """Return messages from a specific chat thread."""
        url = f"{self._GRAPH}/chats/{chat_id}/messages"
        resp = self._session.get(
            url, params={"$top": min(top, 50), "$orderby": "createdDateTime desc"}, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("value", [])
        return {
            "messages": [self._parse_chat_message(m) for m in raw],
            "chat_id": chat_id,
        }

    # ------------------------------------------------------------------
    # User chat list
    # ------------------------------------------------------------------

    def get_user_chats(self, user_id: str) -> list[dict[str, Any]]:
        """List all chats (1:1 and group) for a user."""
        url = f"{self._GRAPH}/users/{user_id}/chats"
        resp = self._session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json().get("value", [])

    # ------------------------------------------------------------------
    # Teams and channels listing
    # ------------------------------------------------------------------

    def list_teams(self) -> list[dict[str, Any]]:
        """List all teams in the organization."""
        url = f"{self._GRAPH}/groups"
        resp = self._session.get(
            url,
            params={"$filter": "resourceProvisioningOptions/Any(x:x eq 'Team')"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("value", [])

    def list_channels(self, team_id: str) -> list[dict[str, Any]]:
        """List all channels in a team."""
        url = f"{self._GRAPH}/teams/{team_id}/channels"
        resp = self._session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json().get("value", [])

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_channel_message(raw: dict[str, Any]) -> dict[str, Any]:
        sender_info = raw.get("from") or {}
        user_info = sender_info.get("user") or {}
        body = raw.get("body") or {}
        return {
            "id": raw.get("id", ""),
            "created_at": raw.get("createdDateTime", ""),
            "modified_at": raw.get("lastModifiedDateTime"),
            "from_user_id": user_info.get("id", ""),
            "from_display_name": user_info.get("displayName", ""),
            "from_email": user_info.get("userIdentityType"),
            "body_text": _strip_html(body.get("content", "")),
            "body_type": body.get("contentType", "text"),
            "importance": raw.get("importance", "normal"),
            "mentions": [
                {
                    "id": m.get("id"),
                    "display_name": (m.get("mentioned") or {}).get("user", {}).get("displayName"),
                }
                for m in (raw.get("mentions") or [])
            ],
            "web_url": raw.get("webUrl"),
        }

    @staticmethod
    def _parse_chat_message(raw: dict[str, Any]) -> dict[str, Any]:
        sender_info = raw.get("from") or {}
        user_info = sender_info.get("user") or {}
        body = raw.get("body") or {}
        return {
            "id": raw.get("id", ""),
            "created_at": raw.get("createdDateTime", ""),
            "from_user_id": user_info.get("id", ""),
            "from_display_name": user_info.get("displayName", ""),
            "body_text": _strip_html(body.get("content", "")),
            "body_type": body.get("contentType", "text"),
            "importance": raw.get("importance", "normal"),
            "deleted_at": raw.get("deletedDateTime"),
        }

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> TeamsClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _strip_html(text: str) -> str:
    """Very light HTML tag stripper for Teams message bodies."""
    import re

    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    # Unescape common entities
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        clean = clean.replace(entity, char)
    return clean


def get_app_access_token(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    scope: str = "https://graph.microsoft.com/.default",
) -> str:
    """Obtain an app-only access token using client credentials flow."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    resp = requests.post(
        url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def make_teams_client(
    *,
    access_token: str | None = None,
    tenant_id: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> TeamsClient | None:
    """Create a TeamsClient from credentials.

    Pass either:
    - ``access_token``: a pre-obtained OAuth2 bearer token
    - ``tenant_id`` + ``client_id`` + ``client_secret``: for client credentials flow
    """
    if access_token:
        return TeamsClient(access_token=access_token)

    if tenant_id and client_id and client_secret:
        try:
            token = get_app_access_token(tenant_id, client_id, client_secret)
            return TeamsClient(access_token=token)
        except Exception:
            return None

    return None
