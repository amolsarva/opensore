"""Tests for the macOS Keychain tool."""

from __future__ import annotations

from unittest.mock import patch

from app.tools.MacOSKeychainTool import MacOSKeychainTool, inspect_macos_keychain
from app.tools.registry import get_registered_tool_map


class TestKeychainToolMetadata:
    def test_tool_registered(self) -> None:
        assert "inspect_macos_keychain" in get_registered_tool_map("investigation")

    def test_source_is_local_device(self) -> None:
        assert inspect_macos_keychain.source == "local_device"

    def test_is_available_only_on_macos(self) -> None:
        tool = MacOSKeychainTool()
        with patch("app.tools.MacOSKeychainTool.is_macos", return_value=True):
            assert tool.is_available({})
        with patch("app.tools.MacOSKeychainTool.is_macos", return_value=False):
            assert not tool.is_available({})

    def test_use_cases_mention_keychain(self) -> None:
        assert any("credential" in uc.lower() or "keychain" in uc.lower() or "service" in uc.lower() for uc in inspect_macos_keychain.use_cases)


class TestKeychainToolRun:
    def test_not_available_on_non_macos(self) -> None:
        with patch("app.tools.MacOSKeychainTool.is_macos", return_value=False):
            result = MacOSKeychainTool().run()

        assert result["available"] is False
        assert "macOS" in result["error"]

    def test_list_services_returns_service_list(self) -> None:
        services = ["com.apple.mail", "com.dropbox.client", "com.slack.SlackMacApp"]
        with (
            patch("app.tools.MacOSKeychainTool.is_macos", return_value=True),
            patch("app.tools.MacOSKeychainTool.keychain_list_services", return_value=services),
        ):
            result = MacOSKeychainTool().run(action="list_services")

        assert result["available"] is True
        assert result["action"] == "list_services"
        assert "com.dropbox.client" in result["services"]
        assert result["service_count"] == 3

    def test_list_services_no_credentials_in_output(self) -> None:
        with (
            patch("app.tools.MacOSKeychainTool.is_macos", return_value=True),
            patch("app.tools.MacOSKeychainTool.keychain_list_services", return_value=["svc"]),
        ):
            result = MacOSKeychainTool().run(action="list_services")

        assert "password" not in result
        assert "secret" not in result

    def test_find_entry_calls_keychain_find_generic(self) -> None:
        entry = {"found": True, "service": "Corp VPN", "account": "alice@corp.com", "note": "approved"}
        with (
            patch("app.tools.MacOSKeychainTool.is_macos", return_value=True),
            patch("app.tools.MacOSKeychainTool.keychain_find_generic", return_value=entry) as mock_fn,
        ):
            result = MacOSKeychainTool().run(action="find_entry", service="Corp VPN", account="alice@corp.com")

        mock_fn.assert_called_once_with(service="Corp VPN", account="alice@corp.com")
        assert result["available"] is True
        assert result["action"] == "find_entry"
        assert result["entry"]["found"] is True
        assert "warning" in result

    def test_find_entry_not_found(self) -> None:
        entry = {"found": False, "error": "Item not found."}
        with (
            patch("app.tools.MacOSKeychainTool.is_macos", return_value=True),
            patch("app.tools.MacOSKeychainTool.keychain_find_generic", return_value=entry),
        ):
            result = MacOSKeychainTool().run(action="find_entry", service="unknown-service")

        assert result["available"] is True
        assert result["entry"]["found"] is False

    def test_exception_returns_available_false(self) -> None:
        with (
            patch("app.tools.MacOSKeychainTool.is_macos", return_value=True),
            patch("app.tools.MacOSKeychainTool.keychain_list_services", side_effect=RuntimeError("CLI error")),
        ):
            result = MacOSKeychainTool().run(action="list_services")

        assert result["available"] is False
        assert "CLI error" in result["error"]

    def test_source_is_local_device(self) -> None:
        with (
            patch("app.tools.MacOSKeychainTool.is_macos", return_value=True),
            patch("app.tools.MacOSKeychainTool.keychain_list_services", return_value=[]),
        ):
            result = MacOSKeychainTool().run()

        assert result["source"] == "local_device"
