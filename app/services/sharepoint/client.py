"""SharePoint and OneDrive client via the Microsoft Graph API.

Authentication: OAuth2 bearer token with the following scopes:
  - Sites.Read.All (for SharePoint site/file search)
  - Files.Read.All (for OneDrive/drive items)
  - User.Read.All (for resolving user info)

Token acquisition: same client credentials flow as Teams client.

Reference: https://learn.microsoft.com/graph/api/driveitem-search
"""

from __future__ import annotations

from typing import Any

import requests


class SharePointClient:
    """HTTP wrapper around the Microsoft Graph API for SharePoint/OneDrive data."""

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
    # Site search
    # ------------------------------------------------------------------

    def search_site_files(
        self,
        site_id: str,
        query: str,
        top: int = 25,
    ) -> dict[str, Any]:
        """Search for files in a SharePoint site by keyword.

        Args:
            site_id: SharePoint site ID or ``root`` for the root site
            query: Keyword search query
            top: Max results to return (Graph search caps at 25 per request)
        """
        url = f"{self._GRAPH}/sites/{site_id}/drive/root/search(q='{_escape_odata(query)}')"
        resp = self._session.get(url, params={"$top": min(top, 25)}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("value", [])
        return {
            "items": [self._parse_drive_item(i) for i in raw],
            "site_id": site_id,
            "query": query,
        }

    def search_drive_files(
        self,
        drive_id: str,
        query: str,
        top: int = 25,
    ) -> dict[str, Any]:
        """Search for files in a specific OneDrive drive by keyword."""
        url = f"{self._GRAPH}/drives/{drive_id}/root/search(q='{_escape_odata(query)}')"
        resp = self._session.get(url, params={"$top": min(top, 25)}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("value", [])
        return {
            "items": [self._parse_drive_item(i) for i in raw],
            "drive_id": drive_id,
            "query": query,
        }

    def search_user_drive(
        self,
        user_id: str,
        query: str,
        top: int = 25,
    ) -> dict[str, Any]:
        """Search a specific user's OneDrive by keyword."""
        url = f"{self._GRAPH}/users/{user_id}/drive/root/search(q='{_escape_odata(query)}')"
        resp = self._session.get(url, params={"$top": min(top, 25)}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("value", [])
        return {
            "items": [self._parse_drive_item(i) for i in raw],
            "user_id": user_id,
            "query": query,
        }

    # ------------------------------------------------------------------
    # Site listing
    # ------------------------------------------------------------------

    def list_sites(self, search_term: str = "") -> list[dict[str, Any]]:
        """List SharePoint sites, optionally filtered by search term."""
        url = f"{self._GRAPH}/sites"
        params: dict[str, Any] = {}
        if search_term:
            params["search"] = search_term
        resp = self._session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return [
            {
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "display_name": s.get("displayName", ""),
                "web_url": s.get("webUrl", ""),
                "description": s.get("description", ""),
            }
            for s in resp.json().get("value", [])
        ]

    def get_file_metadata(self, drive_id: str, item_id: str) -> dict[str, Any]:
        """Retrieve metadata for a specific drive item."""
        url = f"{self._GRAPH}/drives/{drive_id}/items/{item_id}"
        resp = self._session.get(url, timeout=15)
        resp.raise_for_status()
        return self._parse_drive_item(resp.json())

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_drive_item(raw: dict[str, Any]) -> dict[str, Any]:
        created_by = (raw.get("createdBy") or {}).get("user") or {}
        modified_by = (raw.get("lastModifiedBy") or {}).get("user") or {}
        file_info = raw.get("file") or {}
        folder_info = raw.get("folder") or {}
        return {
            "id": raw.get("id", ""),
            "name": raw.get("name", ""),
            "web_url": raw.get("webUrl", ""),
            "created_at": raw.get("createdDateTime", ""),
            "modified_at": raw.get("lastModifiedDateTime", ""),
            "created_by_id": created_by.get("id", ""),
            "created_by_name": created_by.get("displayName", ""),
            "modified_by_id": modified_by.get("id", ""),
            "modified_by_name": modified_by.get("displayName", ""),
            "size_bytes": raw.get("size"),
            "mime_type": file_info.get("mimeType"),
            "is_folder": bool(folder_info),
            "parent_path": (raw.get("parentReference") or {}).get("path", ""),
            "drive_id": (raw.get("parentReference") or {}).get("driveId", ""),
        }

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> SharePointClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _escape_odata(query: str) -> str:
    """Escape single quotes in OData query string function arguments."""
    return query.replace("'", "''")


def make_sharepoint_client(
    *,
    access_token: str | None = None,
    tenant_id: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> SharePointClient | None:
    """Create a SharePointClient from credentials.

    Pass either:
    - ``access_token``: a pre-obtained OAuth2 bearer token
    - ``tenant_id`` + ``client_id`` + ``client_secret``: for client credentials flow
    """
    if access_token:
        return SharePointClient(access_token=access_token)

    if tenant_id and client_id and client_secret:
        try:
            from app.services.microsoft_teams.client import get_app_access_token

            token = get_app_access_token(tenant_id, client_id, client_secret)
            return SharePointClient(access_token=token)
        except Exception:
            return None

    return None
