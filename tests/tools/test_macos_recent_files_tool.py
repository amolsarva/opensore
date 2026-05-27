"""Tests for the macOS Recent Files tool."""

from __future__ import annotations

from unittest.mock import patch

from app.tools.MacOSRecentFilesTool import MacOSRecentFilesTool, read_macos_recent_files
from app.tools.registry import get_registered_tool_map

FILE_ENTRY = {
    "source": "downloads",
    "path": "/Users/alice/Downloads/Q1-Report.pdf",
    "name": "Q1-Report.pdf",
    "size_bytes": 204800,
    "modified_at": "2024-03-15T14:30:00Z",
}

AIRDROP_ENTRY = {
    "source": "airdrop_cache",
    "path": "/Users/alice/Library/com.apple.nsurlsessiond/Downloads/secret.zip",
    "name": "secret.zip",
    "size_bytes": 1048576,
    "modified_at": "2024-03-15T22:00:00Z",
}


class TestRecentFilesToolMetadata:
    def test_tool_registered(self) -> None:
        assert "read_macos_recent_files" in get_registered_tool_map("investigation")

    def test_source_is_local_device(self) -> None:
        assert read_macos_recent_files.source == "local_device"

    def test_always_available(self) -> None:
        assert MacOSRecentFilesTool().is_available({})

    def test_use_cases_mention_files(self) -> None:
        assert any("file" in uc.lower() or "download" in uc.lower() for uc in read_macos_recent_files.use_cases)


class TestRecentFilesToolRun:
    def test_returns_files(self) -> None:
        with patch("app.tools.MacOSRecentFilesTool.read_recent_files", return_value=[FILE_ENTRY]):
            result = MacOSRecentFilesTool().run()

        assert result["available"] is True
        assert result["total"] == 1
        assert result["files"][0]["name"] == "Q1-Report.pdf"

    def test_limit_passed_through(self) -> None:
        with patch("app.tools.MacOSRecentFilesTool.read_recent_files", return_value=[]) as mock_fn:
            MacOSRecentFilesTool().run(limit=10)

        mock_fn.assert_called_once_with(limit=10)

    def test_airdrop_entries_included(self) -> None:
        with patch("app.tools.MacOSRecentFilesTool.read_recent_files", return_value=[FILE_ENTRY, AIRDROP_ENTRY]):
            result = MacOSRecentFilesTool().run()

        sources = [f["source"] for f in result["files"]]
        assert "airdrop_cache" in sources

    def test_empty_returns_available_true(self) -> None:
        with patch("app.tools.MacOSRecentFilesTool.read_recent_files", return_value=[]):
            result = MacOSRecentFilesTool().run()

        assert result["available"] is True
        assert result["total"] == 0
        assert result["files"] == []

    def test_exception_returns_available_false(self) -> None:
        with patch("app.tools.MacOSRecentFilesTool.read_recent_files", side_effect=PermissionError("no access")):
            result = MacOSRecentFilesTool().run()

        assert result["available"] is False
        assert "no access" in result["error"]

    def test_source_is_local_device(self) -> None:
        with patch("app.tools.MacOSRecentFilesTool.read_recent_files", return_value=[FILE_ENTRY]):
            result = MacOSRecentFilesTool().run()

        assert result["source"] == "local_device"
