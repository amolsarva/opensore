"""Tests for the SharePoint/OneDrive document search tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.registry import get_registered_tool_map
from app.tools.SharePointSearchTool import SharePointSearchTool, search_sharepoint_documents

SAMPLE_ITEM = {
    "id": "item-001",
    "name": "HR Investigation Report.docx",
    "web_url": "https://contoso.sharepoint.com/sites/HR/Shared Documents/HR Investigation Report.docx",
    "created_at": "2024-03-10T09:00:00Z",
    "modified_at": "2024-03-15T14:30:00Z",
    "created_by_name": "Jane Investigator",
    "modified_by_name": "Jane Investigator",
    "size_bytes": 45678,
    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "is_folder": False,
    "parent_path": "/drive/root:/HR/Investigations",
    "drive_id": "drive-abc",
}


class TestSharePointToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "search_sharepoint_documents" in tool_map

    def test_source_is_sharepoint(self) -> None:
        assert search_sharepoint_documents.source == "sharepoint"

    def test_input_schema_requires_query(self) -> None:
        schema = search_sharepoint_documents.input_schema
        assert "query" in schema.get("required", [])

    def test_input_schema_has_scope_fields(self) -> None:
        props = search_sharepoint_documents.input_schema["properties"]
        assert "site_id" in props
        assert "drive_id" in props
        assert "user_id" in props

    def test_use_cases_are_investigation_focused(self) -> None:
        assert any(
            "document" in uc.lower() or "sharepoint" in uc.lower()
            for uc in search_sharepoint_documents.use_cases
        )


class TestSharePointToolAvailability:
    def test_available_with_access_token(self) -> None:
        tool = SharePointSearchTool()
        assert tool.is_available({"sharepoint": {"access_token": "tok"}})

    def test_available_with_client_credentials(self) -> None:
        tool = SharePointSearchTool()
        assert tool.is_available(
            {"sharepoint": {"tenant_id": "t", "client_id": "c", "client_secret": "s"}}
        )

    def test_available_via_microsoft_sharepoint_key(self) -> None:
        tool = SharePointSearchTool()
        assert tool.is_available({"microsoft_sharepoint": {"access_token": "tok"}})

    def test_not_available_empty(self) -> None:
        tool = SharePointSearchTool()
        assert not tool.is_available({})

    def test_not_available_partial_creds(self) -> None:
        tool = SharePointSearchTool()
        assert not tool.is_available({"sharepoint": {"tenant_id": "only-tenant"}})

    def test_extract_params(self) -> None:
        tool = SharePointSearchTool()
        params = tool.extract_params({"sharepoint": {"access_token": "tok", "default_site_id": "hr-site"}})
        assert params["access_token"] == "tok"
        assert params["site_id"] == "hr-site"
        assert params["top"] == 25


class TestSharePointToolRun:
    def test_error_without_query(self) -> None:
        tool = SharePointSearchTool()
        result = tool.run(access_token="tok", site_id="s1")
        assert result["available"] is False
        assert "query" in result["error"]

    def test_error_without_scope(self) -> None:
        tool = SharePointSearchTool()
        result = tool.run(access_token="tok", query="harassment")
        assert result["available"] is False
        assert "site_id" in result["error"]

    def test_error_without_credentials(self) -> None:
        tool = SharePointSearchTool()
        result = tool.run(query="harassment", site_id="s1")
        assert result["available"] is False
        assert "credentials" in result["error"].lower()

    def test_site_search(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_site_files.return_value = {
            "items": [SAMPLE_ITEM],
            "site_id": "hr-site",
            "query": "investigation",
        }

        with patch("app.tools.SharePointSearchTool.make_sharepoint_client", return_value=mock_client):
            tool = SharePointSearchTool()
            result = tool.run(access_token="tok", query="investigation", site_id="hr-site")

        assert result["available"] is True
        assert result["site_id"] == "hr-site"
        assert result["query"] == "investigation"
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "HR Investigation Report.docx"
        assert result["returned_count"] == 1

    def test_drive_search(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_drive_files.return_value = {
            "items": [SAMPLE_ITEM],
            "drive_id": "drive-abc",
            "query": "complaint",
        }

        with patch("app.tools.SharePointSearchTool.make_sharepoint_client", return_value=mock_client):
            tool = SharePointSearchTool()
            result = tool.run(access_token="tok", query="complaint", drive_id="drive-abc")

        assert result["available"] is True
        assert result["drive_id"] == "drive-abc"
        mock_client.search_drive_files.assert_called_once()
        mock_client.search_site_files.assert_not_called()

    def test_user_drive_search(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_user_drive.return_value = {
            "items": [],
            "user_id": "alice@corp.com",
            "query": "performance review",
        }

        with patch("app.tools.SharePointSearchTool.make_sharepoint_client", return_value=mock_client):
            tool = SharePointSearchTool()
            result = tool.run(access_token="tok", query="performance review", user_id="alice@corp.com")

        assert result["available"] is True
        assert result["user_id"] == "alice@corp.com"
        assert result["returned_count"] == 0
        mock_client.search_user_drive.assert_called_once()

    def test_site_takes_priority_over_drive(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_site_files.return_value = {
            "items": [],
            "site_id": "site-1",
            "query": "test",
        }

        with patch("app.tools.SharePointSearchTool.make_sharepoint_client", return_value=mock_client):
            tool = SharePointSearchTool()
            result = tool.run(
                access_token="tok",
                query="test",
                site_id="site-1",
                drive_id="drive-2",
            )

        assert result["available"] is True
        mock_client.search_site_files.assert_called_once()
        mock_client.search_drive_files.assert_not_called()

    def test_api_error_returns_unavailable(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_site_files.side_effect = Exception("403 Forbidden")

        with patch("app.tools.SharePointSearchTool.make_sharepoint_client", return_value=mock_client):
            tool = SharePointSearchTool()
            result = tool.run(access_token="tok", query="test", site_id="s1")

        assert result["available"] is False
        assert "403 Forbidden" in result["error"]

    def test_empty_results(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_site_files.return_value = {
            "items": [],
            "site_id": "site-1",
            "query": "nonexistent topic",
        }

        with patch("app.tools.SharePointSearchTool.make_sharepoint_client", return_value=mock_client):
            tool = SharePointSearchTool()
            result = tool.run(access_token="tok", query="nonexistent topic", site_id="site-1")

        assert result["available"] is True
        assert result["items"] == []
        assert result["returned_count"] == 0

    def test_client_credentials_flow(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_user_drive.return_value = {
            "items": [],
            "user_id": "bob@corp.com",
            "query": "incident",
        }

        with patch(
            "app.tools.SharePointSearchTool.make_sharepoint_client", return_value=mock_client
        ) as mock_factory:
            tool = SharePointSearchTool()
            tool.run(
                tenant_id="tid",
                client_id="cid",
                client_secret="sec",
                query="incident",
                user_id="bob@corp.com",
            )

        mock_factory.assert_called_once_with(
            access_token=None,
            tenant_id="tid",
            client_id="cid",
            client_secret="sec",
        )
