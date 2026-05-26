"""SharePoint and OneDrive document search via Microsoft Graph API."""

from __future__ import annotations

from app.services.sharepoint.client import SharePointClient, make_sharepoint_client

__all__ = ["SharePointClient", "make_sharepoint_client"]
