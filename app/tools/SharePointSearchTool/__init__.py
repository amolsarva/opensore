"""SharePoint and OneDrive document search tool for HR/legal investigation workflows."""

from __future__ import annotations

from typing import Any

from app.services.sharepoint import make_sharepoint_client
from app.tools.base import BaseTool


class SharePointSearchTool(BaseTool):
    """Search SharePoint sites and OneDrive drives for documents relevant to investigations.

    Uses the Microsoft Graph API to locate files by keyword, returning metadata
    such as file name, author, modification history, and direct links.
    Document content is not fetched — only metadata and file details are returned.
    """

    name = "search_sharepoint_documents"
    source = "sharepoint"
    description = (
        "Search SharePoint sites or OneDrive drives for documents matching HR/legal "
        "investigation keywords. Returns file metadata: name, author, creation/modification "
        "dates, and direct links. Supports site-scoped, drive-scoped, and user-scoped search. "
        "Requires Microsoft Graph API credentials."
    )
    use_cases = [
        "Locating HR policy documents or investigation procedure files in SharePoint",
        "Finding documents authored or modified by a specific employee during an incident window",
        "Searching for files referencing a complaint, case number, or incident keywords",
        "Identifying whether sensitive documents were shared or modified around the time of an event",
        "Locating meeting notes, performance reviews, or written warnings stored in SharePoint",
        "Tracing document modification history to establish who knew what and when",
    ]
    requires = ["access_token|tenant_id+client_id+client_secret"]
    input_schema = {
        "type": "object",
        "properties": {
            "access_token": {
                "type": "string",
                "description": "OAuth2 bearer token with Sites.Read.All and Files.Read.All scopes",
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
            "query": {
                "type": "string",
                "description": "Keyword search query for file name and content",
            },
            "site_id": {
                "type": "string",
                "description": "SharePoint site ID to scope the search. "
                               "Use 'root' for the root site. Mutually exclusive with drive_id/user_id.",
            },
            "drive_id": {
                "type": "string",
                "description": "OneDrive drive ID to scope the search. "
                               "Mutually exclusive with site_id/user_id.",
            },
            "user_id": {
                "type": "string",
                "description": "User ID or UPN to search that user's OneDrive. "
                               "Mutually exclusive with site_id/drive_id.",
            },
            "top": {
                "type": "integer",
                "description": "Maximum results to return (Graph caps at 25 per request)",
                "default": 25,
            },
        },
        "required": ["query"],
    }
    outputs = {
        "items": "List of file metadata: name, author, created_at, modified_at, web_url, mime_type",
        "query": "The search query used",
        "returned_count": "Number of items returned",
    }

    def is_available(self, sources: dict) -> bool:
        cfg = sources.get("sharepoint", sources.get("microsoft_sharepoint", {}))
        has_token = bool(cfg.get("access_token"))
        has_creds = bool(
            cfg.get("tenant_id") and cfg.get("client_id") and cfg.get("client_secret")
        )
        return has_token or has_creds

    def extract_params(self, sources: dict) -> dict[str, Any]:
        cfg = sources.get("sharepoint", sources.get("microsoft_sharepoint", {}))
        return {
            "access_token": cfg.get("access_token", ""),
            "tenant_id": cfg.get("tenant_id", ""),
            "client_id": cfg.get("client_id", ""),
            "client_secret": cfg.get("client_secret", ""),
            "query": "",
            "site_id": cfg.get("default_site_id", ""),
            "drive_id": "",
            "user_id": "",
            "top": 25,
        }

    def run(
        self,
        query: str = "",
        access_token: str = "",
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
        site_id: str = "",
        drive_id: str = "",
        user_id: str = "",
        top: int = 25,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not query:
            return {"source": "sharepoint", "available": False, "error": "query is required."}

        if not (site_id or drive_id or user_id):
            return {
                "source": "sharepoint",
                "available": False,
                "error": (
                    "Provide one of: site_id (for SharePoint site), "
                    "drive_id (for a specific drive), or user_id (for a user's OneDrive)."
                ),
            }

        client = make_sharepoint_client(
            access_token=access_token or None,
            tenant_id=tenant_id or None,
            client_id=client_id or None,
            client_secret=client_secret or None,
        )
        if client is None:
            return {
                "source": "sharepoint",
                "available": False,
                "error": (
                    "SharePoint credentials not configured. "
                    "Provide access_token or tenant_id + client_id + client_secret."
                ),
            }

        try:
            with client:
                if site_id:
                    result = client.search_site_files(site_id=site_id, query=query, top=top)
                elif drive_id:
                    result = client.search_drive_files(drive_id=drive_id, query=query, top=top)
                else:
                    result = client.search_user_drive(user_id=user_id, query=query, top=top)

            return {
                "source": "sharepoint",
                "available": True,
                "query": result["query"],
                "items": result["items"],
                "returned_count": len(result["items"]),
                **({"site_id": result["site_id"]} if "site_id" in result else {}),
                **({"drive_id": result["drive_id"]} if "drive_id" in result else {}),
                **({"user_id": result["user_id"]} if "user_id" in result else {}),
            }
        except Exception as exc:
            return {"source": "sharepoint", "available": False, "error": str(exc)}


search_sharepoint_documents = SharePointSearchTool()
