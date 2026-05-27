"""Tests for the macOS Browser History tool."""

from __future__ import annotations

from unittest.mock import patch

from app.tools.MacOSBrowserHistoryTool import MacOSBrowserHistoryTool, read_macos_browser_history
from app.tools.registry import get_registered_tool_map

SAFARI_ENTRY = {"browser": "safari", "url": "https://example.com/page", "title": "Example", "visited_at": "2024-03-15T10:00:00Z"}
CHROME_ENTRY = {"browser": "chrome", "url": "https://drive.google.com/file", "title": "Drive File", "visited_at": "2024-03-15T11:00:00Z"}
FIREFOX_ENTRY = {"browser": "firefox", "url": "https://wetransfer.com/upload", "title": "WeTransfer", "visited_at": "2024-03-15T09:00:00Z"}


class TestBrowserHistoryToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "read_macos_browser_history" in tool_map

    def test_source_is_local_device(self) -> None:
        assert read_macos_browser_history.source == "local_device"

    def test_always_available(self) -> None:
        tool = MacOSBrowserHistoryTool()
        assert tool.is_available({})

    def test_use_cases_mention_forensics(self) -> None:
        assert any("history" in uc.lower() or "domain" in uc.lower() for uc in read_macos_browser_history.use_cases)


class TestBrowserHistoryToolRun:
    def test_all_browsers_queried_by_default(self) -> None:
        with (
            patch("app.tools.MacOSBrowserHistoryTool.read_safari_history", return_value=[SAFARI_ENTRY]),
            patch("app.tools.MacOSBrowserHistoryTool.read_chrome_history", return_value=[CHROME_ENTRY]),
            patch("app.tools.MacOSBrowserHistoryTool.read_firefox_history", return_value=[FIREFOX_ENTRY]),
        ):
            tool = MacOSBrowserHistoryTool()
            result = tool.run()

        assert result["available"] is True
        assert result["total"] == 3
        assert result["browser_counts"]["safari"] == 1
        assert result["browser_counts"]["chrome"] == 1
        assert result["browser_counts"]["firefox"] == 1

    def test_safari_only(self) -> None:
        with (
            patch("app.tools.MacOSBrowserHistoryTool.read_safari_history", return_value=[SAFARI_ENTRY]),
            patch("app.tools.MacOSBrowserHistoryTool.read_chrome_history", return_value=[]) as mock_chrome,
            patch("app.tools.MacOSBrowserHistoryTool.read_firefox_history", return_value=[]) as mock_ff,
        ):
            tool = MacOSBrowserHistoryTool()
            result = tool.run(browsers=["safari"])

        assert result["available"] is True
        mock_chrome.assert_not_called()
        mock_ff.assert_not_called()
        assert result["browser_counts"].get("safari") == 1

    def test_entries_sorted_by_visited_at_desc(self) -> None:
        with (
            patch("app.tools.MacOSBrowserHistoryTool.read_safari_history", return_value=[SAFARI_ENTRY]),
            patch("app.tools.MacOSBrowserHistoryTool.read_chrome_history", return_value=[CHROME_ENTRY]),
            patch("app.tools.MacOSBrowserHistoryTool.read_firefox_history", return_value=[FIREFOX_ENTRY]),
        ):
            result = MacOSBrowserHistoryTool().run()

        timestamps = [e["visited_at"] for e in result["entries"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_domain_filter_passed_through(self) -> None:
        with (
            patch("app.tools.MacOSBrowserHistoryTool.read_safari_history", return_value=[]) as mock_s,
            patch("app.tools.MacOSBrowserHistoryTool.read_chrome_history", return_value=[]),
            patch("app.tools.MacOSBrowserHistoryTool.read_firefox_history", return_value=[]),
        ):
            MacOSBrowserHistoryTool().run(browsers=["safari"], domain_filter="example.com")

        mock_s.assert_called_once_with(limit=200, domain_filter="example.com", after_iso=None)

    def test_after_iso_passed_through(self) -> None:
        with (
            patch("app.tools.MacOSBrowserHistoryTool.read_safari_history", return_value=[]) as mock_s,
            patch("app.tools.MacOSBrowserHistoryTool.read_chrome_history", return_value=[]),
            patch("app.tools.MacOSBrowserHistoryTool.read_firefox_history", return_value=[]),
        ):
            MacOSBrowserHistoryTool().run(browsers=["safari"], after_iso="2024-01-01T00:00:00Z")

        mock_s.assert_called_once_with(limit=200, domain_filter=None, after_iso="2024-01-01T00:00:00Z")

    def test_exception_returns_available_false(self) -> None:
        with patch("app.tools.MacOSBrowserHistoryTool.read_safari_history", side_effect=RuntimeError("db locked")):
            result = MacOSBrowserHistoryTool().run(browsers=["safari"])

        assert result["available"] is False
        assert "db locked" in result["error"]

    def test_result_includes_source(self) -> None:
        with (
            patch("app.tools.MacOSBrowserHistoryTool.read_safari_history", return_value=[]),
            patch("app.tools.MacOSBrowserHistoryTool.read_chrome_history", return_value=[]),
            patch("app.tools.MacOSBrowserHistoryTool.read_firefox_history", return_value=[]),
        ):
            result = MacOSBrowserHistoryTool().run()

        assert result["source"] == "local_device"

    def test_limit_applied(self) -> None:
        many = [dict(SAFARI_ENTRY) for _ in range(300)]
        with (
            patch("app.tools.MacOSBrowserHistoryTool.read_safari_history", return_value=many),
            patch("app.tools.MacOSBrowserHistoryTool.read_chrome_history", return_value=[]),
            patch("app.tools.MacOSBrowserHistoryTool.read_firefox_history", return_value=[]),
        ):
            result = MacOSBrowserHistoryTool().run(limit=10)

        assert len(result["entries"]) <= 10
