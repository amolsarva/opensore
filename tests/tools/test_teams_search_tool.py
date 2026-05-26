"""Tests for the Microsoft Teams message search tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.registry import get_registered_tool_map
from app.tools.TeamsSearchTool import TeamsSearchTool, search_teams_messages


class TestTeamsToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "search_teams_messages" in tool_map

    def test_source_is_teams(self) -> None:
        assert search_teams_messages.source == "teams"

    def test_input_schema_has_auth_and_target_fields(self) -> None:
        schema = search_teams_messages.input_schema
        props = schema.get("properties", {})
        assert "access_token" in props
        assert "tenant_id" in props
        assert "team_id" in props
        assert "channel_id" in props
        assert "chat_id" in props

    def test_use_cases_are_investigation_focused(self) -> None:
        assert any(
            "harassment" in uc.lower() or "incident" in uc.lower()
            for uc in search_teams_messages.use_cases
        )

    def test_outputs_declared(self) -> None:
        assert "messages" in search_teams_messages.outputs


class TestTeamsToolAvailability:
    def test_available_with_access_token(self) -> None:
        tool = TeamsSearchTool()
        assert tool.is_available({"teams": {"access_token": "tok"}})

    def test_available_with_client_credentials(self) -> None:
        tool = TeamsSearchTool()
        assert tool.is_available(
            {"teams": {"tenant_id": "t", "client_id": "c", "client_secret": "s"}}
        )

    def test_available_via_microsoft_teams_key(self) -> None:
        tool = TeamsSearchTool()
        assert tool.is_available({"microsoft_teams": {"access_token": "tok"}})

    def test_not_available_empty(self) -> None:
        tool = TeamsSearchTool()
        assert not tool.is_available({})

    def test_not_available_partial_creds(self) -> None:
        tool = TeamsSearchTool()
        assert not tool.is_available({"teams": {"tenant_id": "only-tenant"}})

    def test_extract_params_from_sources(self) -> None:
        tool = TeamsSearchTool()
        params = tool.extract_params(
            {"teams": {"access_token": "tok", "tenant_id": "tid"}}
        )
        assert params["access_token"] == "tok"
        assert params["tenant_id"] == "tid"
        assert params["top"] == 50


class TestTeamsToolRun:
    def test_error_without_target(self) -> None:
        tool = TeamsSearchTool()
        result = tool.run(access_token="tok")
        assert result["available"] is False
        assert "team_id" in result["error"] or "channel_id" in result["error"] or "chat_id" in result["error"]

    def test_error_without_credentials(self) -> None:
        tool = TeamsSearchTool()
        result = tool.run(team_id="t1", channel_id="c1")
        assert result["available"] is False
        assert "credentials" in result["error"].lower()

    def test_channel_messages_search(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_channel_messages.return_value = {
            "messages": [
                {
                    "id": "msg-1",
                    "created_at": "2024-03-15T10:00:00Z",
                    "from_display_name": "Alice Johnson",
                    "body_text": "I need to report an incident.",
                    "importance": "normal",
                    "web_url": "https://teams.microsoft.com/l/message/...",
                }
            ],
            "team_id": "team-abc",
            "channel_id": "chan-xyz",
        }

        with patch("app.tools.TeamsSearchTool.make_teams_client", return_value=mock_client):
            tool = TeamsSearchTool()
            result = tool.run(
                access_token="tok",
                team_id="team-abc",
                channel_id="chan-xyz",
                top=20,
            )

        assert result["available"] is True
        assert result["team_id"] == "team-abc"
        assert result["channel_id"] == "chan-xyz"
        assert len(result["messages"]) == 1
        assert result["messages"][0]["from_display_name"] == "Alice Johnson"
        assert result["returned_count"] == 1

    def test_channel_messages_with_filter(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_channel_messages.return_value = {
            "messages": [],
            "team_id": "team-abc",
            "channel_id": "chan-xyz",
        }

        with patch("app.tools.TeamsSearchTool.make_teams_client", return_value=mock_client):
            tool = TeamsSearchTool()
            result = tool.run(
                access_token="tok",
                team_id="team-abc",
                channel_id="chan-xyz",
                filter_expr="createdDateTime ge 2024-01-01T00:00:00Z",
            )

        assert result["available"] is True
        mock_client.list_channel_messages.assert_called_once_with(
            team_id="team-abc",
            channel_id="chan-xyz",
            top=50,
            filter_expr="createdDateTime ge 2024-01-01T00:00:00Z",
        )

    def test_chat_messages_search(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_chat_messages.return_value = {
            "messages": [
                {
                    "id": "chat-msg-1",
                    "created_at": "2024-03-20T14:30:00Z",
                    "from_display_name": "Bob Manager",
                    "body_text": "Let's discuss this offline.",
                    "importance": "normal",
                    "deleted_at": None,
                }
            ],
            "chat_id": "chat-123",
        }

        with patch("app.tools.TeamsSearchTool.make_teams_client", return_value=mock_client):
            tool = TeamsSearchTool()
            result = tool.run(access_token="tok", chat_id="chat-123", top=10)

        assert result["available"] is True
        assert result["chat_id"] == "chat-123"
        assert len(result["messages"]) == 1
        assert result["messages"][0]["from_display_name"] == "Bob Manager"
        assert result["returned_count"] == 1

    def test_chat_takes_priority_over_channel(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_chat_messages.return_value = {
            "messages": [],
            "chat_id": "chat-999",
        }

        with patch("app.tools.TeamsSearchTool.make_teams_client", return_value=mock_client):
            tool = TeamsSearchTool()
            result = tool.run(
                access_token="tok",
                team_id="team-abc",
                channel_id="chan-xyz",
                chat_id="chat-999",
            )

        assert result["available"] is True
        assert result["chat_id"] == "chat-999"
        mock_client.list_chat_messages.assert_called_once()
        mock_client.list_channel_messages.assert_not_called()

    def test_api_error_returns_unavailable(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_channel_messages.side_effect = Exception("403 Forbidden")

        with patch("app.tools.TeamsSearchTool.make_teams_client", return_value=mock_client):
            tool = TeamsSearchTool()
            result = tool.run(access_token="tok", team_id="t1", channel_id="c1")

        assert result["available"] is False
        assert "403 Forbidden" in result["error"]

    def test_client_credentials_flow(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_channel_messages.return_value = {
            "messages": [],
            "team_id": "team-abc",
            "channel_id": "chan-xyz",
        }

        with patch("app.tools.TeamsSearchTool.make_teams_client", return_value=mock_client) as mock_factory:
            tool = TeamsSearchTool()
            result = tool.run(
                tenant_id="my-tenant",
                client_id="my-client",
                client_secret="my-secret",
                team_id="team-abc",
                channel_id="chan-xyz",
            )

        assert result["available"] is True
        mock_factory.assert_called_once_with(
            access_token=None,
            tenant_id="my-tenant",
            client_id="my-client",
            client_secret="my-secret",
        )

    def test_empty_messages_returns_successfully(self) -> None:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_channel_messages.return_value = {
            "messages": [],
            "team_id": "team-abc",
            "channel_id": "chan-xyz",
        }

        with patch("app.tools.TeamsSearchTool.make_teams_client", return_value=mock_client):
            tool = TeamsSearchTool()
            result = tool.run(access_token="tok", team_id="team-abc", channel_id="chan-xyz")

        assert result["available"] is True
        assert result["messages"] == []
        assert result["returned_count"] == 0
