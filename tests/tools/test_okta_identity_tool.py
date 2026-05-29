"""Tests for the Okta identity lookup tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.OktaIdentityTool import OktaIdentityTool, lookup_okta_identity
from app.tools.registry import get_registered_tool_map

ALICE = {
    "id": "okta-001",
    "login": "alice@corp.com",
    "email": "alice@corp.com",
    "first_name": "Alice",
    "last_name": "Johnson",
    "display_name": "Alice Johnson",
    "title": "Software Engineer",
    "department": "Engineering",
    "manager": "Bob Smith",
    "status": "ACTIVE",
    "created_at": "2022-01-15T10:00:00.000Z",
    "last_login": "2024-03-14T08:45:00.000Z",
    "password_changed": "2024-01-01T00:00:00.000Z",
}


class TestOktaToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "lookup_okta_identity" in tool_map

    def test_source_is_okta(self) -> None:
        assert lookup_okta_identity.source == "okta"

    def test_input_schema_required_fields(self) -> None:
        required = lookup_okta_identity.input_schema.get("required", [])
        assert "domain" in required
        assert "api_token" in required

    def test_use_cases_are_investigation_focused(self) -> None:
        assert any("access" in uc.lower() or "login" in uc.lower() for uc in lookup_okta_identity.use_cases)


class TestOktaToolAvailability:
    def test_available_when_configured(self) -> None:
        tool = OktaIdentityTool()
        assert tool.is_available({"okta": {"domain": "corp.okta.com", "api_token": "tok"}})

    def test_not_available_missing_token(self) -> None:
        tool = OktaIdentityTool()
        assert not tool.is_available({"okta": {"domain": "corp.okta.com"}})

    def test_not_available_empty(self) -> None:
        tool = OktaIdentityTool()
        assert not tool.is_available({})

    def test_extract_params(self) -> None:
        tool = OktaIdentityTool()
        params = tool.extract_params({"okta": {"domain": "corp.okta.com", "api_token": "tok"}})
        assert params["domain"] == "corp.okta.com"
        assert params["api_token"] == "tok"
        assert params["include_groups"] is True


class TestOktaToolRun:
    def test_error_without_credentials(self) -> None:
        tool = OktaIdentityTool()
        result = tool.run(domain="", api_token="", user_id="x")
        assert result["available"] is False
        assert "api_token" in result["error"]

    def test_error_without_target(self) -> None:
        tool = OktaIdentityTool()
        result = tool.run(domain="corp.okta.com", api_token="tok")
        assert result["available"] is False
        assert "search_query" in result["error"]

    def test_lookup_by_user_id(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_user.return_value = ALICE
        mock_client.get_user_groups.return_value = [
            {"id": "grp-1", "name": "Engineering", "description": "", "type": "OKTA_GROUP"}
        ]

        with patch("app.tools.OktaIdentityTool.make_okta_client", return_value=mock_client):
            tool = OktaIdentityTool()
            result = tool.run(
                domain="corp.okta.com",
                api_token="tok",
                user_id="okta-001",
                include_groups=True,
            )

        assert result["available"] is True
        assert result["user"]["display_name"] == "Alice Johnson"
        assert result["user"]["status"] == "ACTIVE"
        assert len(result["groups"]) == 1
        assert result["groups"][0]["name"] == "Engineering"

    def test_search_multiple_results(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_users.return_value = [
            {**ALICE, "id": "okta-001"},
            {**ALICE, "id": "okta-002", "login": "alice.j@corp.com", "display_name": "Alice J"},
        ]

        with patch("app.tools.OktaIdentityTool.make_okta_client", return_value=mock_client):
            tool = OktaIdentityTool()
            result = tool.run(
                domain="corp.okta.com", api_token="tok", search_query="alice"
            )

        assert result["available"] is True
        assert len(result["search_results"]) == 2
        assert "Refine" in result["message"]

    def test_search_no_results(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_users.return_value = []

        with patch("app.tools.OktaIdentityTool.make_okta_client", return_value=mock_client):
            tool = OktaIdentityTool()
            result = tool.run(domain="corp.okta.com", api_token="tok", search_query="nobody")

        assert result["available"] is True
        assert result["search_results"] == []
        assert "No users found" in result["message"]

    def test_search_single_result_fetches_profile(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_users.return_value = [ALICE]
        mock_client.get_user.return_value = ALICE
        mock_client.get_user_groups.return_value = []

        with patch("app.tools.OktaIdentityTool.make_okta_client", return_value=mock_client):
            tool = OktaIdentityTool()
            result = tool.run(domain="corp.okta.com", api_token="tok", search_query="alice")

        assert result["available"] is True
        assert result["user"]["email"] == "alice@corp.com"
        mock_client.get_user.assert_called_once_with("okta-001")

    def test_include_apps(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_user.return_value = ALICE
        mock_client.get_user_groups.return_value = []
        mock_client.get_user_app_assignments.return_value = [
            {"app_name": "github", "label": "GitHub", "app_instance_id": "app-1", "url": "https://github.com"}
        ]

        with patch("app.tools.OktaIdentityTool.make_okta_client", return_value=mock_client):
            tool = OktaIdentityTool()
            result = tool.run(
                domain="corp.okta.com",
                api_token="tok",
                user_id="okta-001",
                include_apps=True,
            )

        assert result["available"] is True
        assert len(result["apps"]) == 1
        assert result["apps"][0]["label"] == "GitHub"

    def test_include_auth_events(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_user.return_value = ALICE
        mock_client.get_user_groups.return_value = []
        mock_client.get_user_auth_events.return_value = [
            {
                "event_type": "user.session.start",
                "published": "2024-03-14T08:45:00.000Z",
                "actor_login": "alice@corp.com",
                "outcome": "SUCCESS",
                "ip_address": "10.0.0.1",
            }
        ]

        with patch("app.tools.OktaIdentityTool.make_okta_client", return_value=mock_client):
            tool = OktaIdentityTool()
            result = tool.run(
                domain="corp.okta.com",
                api_token="tok",
                user_id="okta-001",
                include_groups=False,
                include_auth_events=True,
                auth_since="2024-03-01T00:00:00Z",
            )

        assert result["available"] is True
        assert len(result["auth_events"]) == 1
        assert result["auth_events"][0]["outcome"] == "SUCCESS"
        mock_client.get_user_auth_events.assert_called_once_with(
            "okta-001",
            since="2024-03-01T00:00:00Z",
            until=None,
            limit=50,
        )

    def test_api_error_returns_unavailable(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_user.side_effect = Exception("401 Unauthorized")

        with patch("app.tools.OktaIdentityTool.make_okta_client", return_value=mock_client):
            tool = OktaIdentityTool()
            result = tool.run(domain="corp.okta.com", api_token="tok", user_id="okta-001")

        assert result["available"] is False
        assert "401 Unauthorized" in result["error"]

    def test_groups_not_included_when_disabled(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_user.return_value = ALICE

        with patch("app.tools.OktaIdentityTool.make_okta_client", return_value=mock_client):
            tool = OktaIdentityTool()
            result = tool.run(
                domain="corp.okta.com",
                api_token="tok",
                user_id="okta-001",
                include_groups=False,
            )

        assert result["available"] is True
        assert "groups" not in result
        mock_client.get_user_groups.assert_not_called()
