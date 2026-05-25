"""Unit tests for Slack investigation tools — mocked HTTP, no live credentials."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.slack.client import SlackClient, _ts_to_iso, make_slack_client
from app.tools.SlackChannelHistoryTool import SlackChannelHistoryTool
from app.tools.SlackSearchTool import SlackSearchTool

# ---------------------------------------------------------------------------
# Client / factory helpers
# ---------------------------------------------------------------------------


def test_make_slack_client_empty_returns_none() -> None:
    assert make_slack_client("") is None
    assert make_slack_client(None) is None  # type: ignore[arg-type]


def test_make_slack_client_with_token() -> None:
    client = make_slack_client("xoxb-abc-123")
    assert client is not None
    assert isinstance(client, SlackClient)
    assert client.is_configured


def test_ts_to_iso_converts_correctly() -> None:
    iso = _ts_to_iso("1704067200.000000")
    assert iso.startswith("2024-01-01")


def test_ts_to_iso_empty_returns_empty() -> None:
    assert _ts_to_iso("") == ""


def test_ts_to_iso_bad_value_returns_input() -> None:
    assert _ts_to_iso("not-a-timestamp") == "not-a-timestamp"


# ---------------------------------------------------------------------------
# SlackSearchTool
# ---------------------------------------------------------------------------


def test_search_tool_metadata() -> None:
    tool = SlackSearchTool()
    assert tool.name == "slack_search_messages"
    assert tool.source == "slack"
    assert "query" in tool.input_schema["properties"]
    assert "count" in tool.input_schema["properties"]


def test_search_tool_not_available_when_unconfigured() -> None:
    tool = SlackSearchTool()
    assert not tool.is_available({})
    assert not tool.is_available({"slack": {"connection_verified": False}})


def test_search_tool_available_when_verified() -> None:
    tool = SlackSearchTool()
    assert tool.is_available({"slack": {"connection_verified": True}})


def test_search_tool_requires_query() -> None:
    tool = SlackSearchTool()
    result = tool.run(bot_token="xoxb-abc", query="")
    assert result["available"] is False
    assert "query" in result["error"].lower()


def test_search_tool_returns_error_without_token() -> None:
    tool = SlackSearchTool()
    result = tool.run(bot_token="", query="latency spike")
    assert result["available"] is False


def test_search_tool_success() -> None:
    tool = SlackSearchTool()
    mock_result = {
        "success": True,
        "query": "latency spike payments",
        "messages": [
            {
                "ts": "1704067200.000000",
                "text": "seeing massive latency on payments service",
                "user": "alice",
                "channel": "incidents",
                "channel_id": "C123",
                "permalink": "https://slack.com/archives/C123/p123",
                "isoformat": "2024-01-01T00:00:00+00:00",
            }
        ],
        "total": 1,
    }
    with patch("app.tools.SlackSearchTool.make_slack_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_messages.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(bot_token="xoxb-abc", query="latency spike payments", count=10)

    assert result["available"] is True
    assert result["total"] == 1
    assert result["messages"][0]["channel"] == "incidents"


def test_search_tool_api_error_propagated() -> None:
    tool = SlackSearchTool()
    mock_result = {"success": False, "error": "not_authed", "messages": []}
    with patch("app.tools.SlackSearchTool.make_slack_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_messages.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(bot_token="xoxb-bad", query="anything")

    assert result["available"] is False
    assert "not_authed" in result["error"]


# ---------------------------------------------------------------------------
# SlackChannelHistoryTool
# ---------------------------------------------------------------------------


def test_channel_history_tool_metadata() -> None:
    tool = SlackChannelHistoryTool()
    assert tool.name == "slack_channel_history"
    assert "channel_id" in tool.input_schema["properties"]
    assert "oldest" in tool.input_schema["properties"]


def test_channel_history_requires_channel_id() -> None:
    tool = SlackChannelHistoryTool()
    result = tool.run(bot_token="xoxb-abc", channel_id="")
    assert result["available"] is False
    assert "channel_id" in result["error"]


def test_channel_history_success() -> None:
    tool = SlackChannelHistoryTool()
    mock_result = {
        "success": True,
        "channel_id": "C123",
        "messages": [
            {
                "ts": "1704067200.000000",
                "text": "DB is down, investigating",
                "user": "U456",
                "type": "message",
                "isoformat": "2024-01-01T00:00:00+00:00",
                "reactions": ["eyes", "fire"],
            }
        ],
        "has_more": False,
    }
    with patch("app.tools.SlackChannelHistoryTool.make_slack_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.channel_history.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(bot_token="xoxb-abc", channel_id="C123", limit=20)

    assert result["available"] is True
    assert result["channel_id"] == "C123"
    assert result["messages"][0]["text"] == "DB is down, investigating"
    assert "fire" in result["messages"][0]["reactions"]
    assert result["has_more"] is False


def test_channel_history_with_time_window() -> None:
    tool = SlackChannelHistoryTool()
    mock_result = {"success": True, "channel_id": "C123", "messages": [], "has_more": False}
    with patch("app.tools.SlackChannelHistoryTool.make_slack_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.channel_history.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(
            bot_token="xoxb-abc",
            channel_id="C123",
            oldest="1704067200",
            latest="1704153600",
        )

    mock_client.channel_history.assert_called_once_with(
        channel_id="C123", limit=50, oldest="1704067200", latest="1704153600"
    )
    assert result["available"] is True
