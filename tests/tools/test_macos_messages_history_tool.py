"""Tests for the macOS Messages History tool."""

from __future__ import annotations

from unittest.mock import patch

from app.tools.MacOSMessagesHistoryTool import MacOSMessagesHistoryTool, read_macos_messages_history
from app.tools.registry import get_registered_tool_map

MSG = {
    "text": "Can we meet privately?",
    "timestamp": "2024-03-15T22:00:00Z",
    "direction": "received",
    "contact": "+15551234567",
    "chat_name": "",
    "service": "iMessage",
}


class TestMessagesHistoryToolMetadata:
    def test_tool_registered(self) -> None:
        assert "read_macos_messages_history" in get_registered_tool_map("investigation")

    def test_source_is_local_device(self) -> None:
        assert read_macos_messages_history.source == "local_device"

    def test_always_available(self) -> None:
        assert MacOSMessagesHistoryTool().is_available({})

    def test_use_cases_mention_messages(self) -> None:
        assert any("message" in uc.lower() or "imessage" in uc.lower() for uc in read_macos_messages_history.use_cases)


class TestMessagesHistoryToolRun:
    def test_returns_messages(self) -> None:
        with patch("app.tools.MacOSMessagesHistoryTool.read_messages_history", return_value=[MSG]):
            result = MacOSMessagesHistoryTool().run()

        assert result["available"] is True
        assert result["total"] == 1
        assert result["messages"][0]["text"] == "Can we meet privately?"

    def test_contact_filter_passed_through(self) -> None:
        with patch("app.tools.MacOSMessagesHistoryTool.read_messages_history", return_value=[]) as mock_fn:
            MacOSMessagesHistoryTool().run(contact_filter="+15551234567")

        mock_fn.assert_called_once_with(contact_filter="+15551234567", limit=200, after_iso=None)

    def test_after_iso_passed_through(self) -> None:
        with patch("app.tools.MacOSMessagesHistoryTool.read_messages_history", return_value=[]) as mock_fn:
            MacOSMessagesHistoryTool().run(after_iso="2024-01-01T00:00:00Z")

        mock_fn.assert_called_once_with(contact_filter=None, limit=200, after_iso="2024-01-01T00:00:00Z")

    def test_no_messages_still_available(self) -> None:
        with patch("app.tools.MacOSMessagesHistoryTool.read_messages_history", return_value=[]):
            result = MacOSMessagesHistoryTool().run()

        assert result["available"] is True
        assert result["total"] == 0
        assert result["messages"] == []

    def test_exception_returns_available_false(self) -> None:
        with patch("app.tools.MacOSMessagesHistoryTool.read_messages_history", side_effect=PermissionError("FDA required")):
            result = MacOSMessagesHistoryTool().run()

        assert result["available"] is False
        assert "FDA required" in result["error"]

    def test_source_is_local_device(self) -> None:
        with patch("app.tools.MacOSMessagesHistoryTool.read_messages_history", return_value=[MSG]):
            result = MacOSMessagesHistoryTool().run()

        assert result["source"] == "local_device"
