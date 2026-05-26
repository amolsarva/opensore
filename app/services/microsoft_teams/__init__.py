"""Microsoft Teams / Microsoft Graph API client for message and chat search."""

from __future__ import annotations

from app.services.microsoft_teams.client import TeamsClient, make_teams_client

__all__ = ["TeamsClient", "make_teams_client"]
