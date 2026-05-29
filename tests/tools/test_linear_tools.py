"""Unit tests for Linear tools — mocked GraphQL responses, no live credentials."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.linear.client import LinearClient, make_linear_client
from app.tools.LinearCreateIssueTool import LinearCreateIssueTool
from app.tools.LinearSearchTool import LinearSearchTool

# ---------------------------------------------------------------------------
# Client / factory
# ---------------------------------------------------------------------------


def test_make_linear_client_empty_returns_none() -> None:
    assert make_linear_client("") is None
    assert make_linear_client(None) is None  # type: ignore[arg-type]


def test_make_linear_client_with_key() -> None:
    client = make_linear_client("lin_api_abc123")
    assert client is not None
    assert isinstance(client, LinearClient)
    assert client.is_configured


# ---------------------------------------------------------------------------
# LinearSearchTool
# ---------------------------------------------------------------------------


def test_search_tool_metadata() -> None:
    tool = LinearSearchTool()
    assert tool.name == "linear_search_issues"
    assert tool.source == "linear"
    assert "query" in tool.input_schema["properties"]
    assert "limit" in tool.input_schema["properties"]


def test_search_tool_not_available_when_unconfigured() -> None:
    tool = LinearSearchTool()
    assert not tool.is_available({})
    assert not tool.is_available({"linear": {"connection_verified": False}})


def test_search_tool_available_when_verified() -> None:
    tool = LinearSearchTool()
    assert tool.is_available({"linear": {"connection_verified": True}})


def test_search_tool_requires_query() -> None:
    tool = LinearSearchTool()
    result = tool.run(api_key="lin_abc", query="")
    assert result["available"] is False
    assert "query" in result["error"]


def test_search_tool_returns_error_without_api_key() -> None:
    tool = LinearSearchTool()
    result = tool.run(api_key="", query="payment latency")
    assert result["available"] is False


def test_search_tool_success() -> None:
    tool = LinearSearchTool()
    mock_result = {
        "success": True,
        "issues": [
            {
                "id": "issue-abc",
                "identifier": "ENG-123",
                "title": "Payments DB connection pool saturation",
                "state": "In Progress",
                "state_type": "started",
                "priority": 1,
                "team": "Engineering",
                "team_key": "ENG",
                "assignee": "Alice",
                "url": "https://linear.app/org/issue/ENG-123",
                "created_at": "2024-01-15T08:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
                "description": "Connection pool hitting max connections during peak traffic.",
            }
        ],
        "total": 1,
    }
    with patch("app.tools.LinearSearchTool.make_linear_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_issues.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(api_key="lin_abc", query="payment latency", limit=5)

    assert result["available"] is True
    assert result["total"] == 1
    assert result["issues"][0]["identifier"] == "ENG-123"


def test_search_tool_propagates_api_error() -> None:
    tool = LinearSearchTool()
    mock_result = {"success": False, "error": "Unauthorized", "issues": []}
    with patch("app.tools.LinearSearchTool.make_linear_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_issues.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(api_key="bad", query="anything")

    assert result["available"] is False
    assert "Unauthorized" in result["error"]


# ---------------------------------------------------------------------------
# LinearCreateIssueTool
# ---------------------------------------------------------------------------


def test_create_tool_metadata() -> None:
    tool = LinearCreateIssueTool()
    assert tool.name == "linear_create_issue"
    assert tool.source == "linear"
    assert "team_id" in tool.input_schema["properties"]
    assert "priority" in tool.input_schema["properties"]


def test_create_tool_requires_team_id() -> None:
    tool = LinearCreateIssueTool()
    result = tool.run(api_key="lin_abc", team_id="", title="DB outage")
    assert result["available"] is False
    assert "team_id" in result["error"]


def test_create_tool_requires_title() -> None:
    tool = LinearCreateIssueTool()
    result = tool.run(api_key="lin_abc", team_id="team-xyz", title="")
    assert result["available"] is False
    assert "title" in result["error"]


def test_create_tool_success() -> None:
    tool = LinearCreateIssueTool()
    mock_result = {
        "success": True,
        "id": "issue-def",
        "identifier": "ENG-999",
        "title": "Incident: HighDBLatency 2024-01-15",
        "url": "https://linear.app/org/issue/ENG-999",
    }
    with patch("app.tools.LinearCreateIssueTool.make_linear_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.create_issue.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(
            api_key="lin_abc",
            team_id="team-xyz",
            title="Incident: HighDBLatency 2024-01-15",
            description="Root cause: connection pool exhausted.",
            priority="urgent",
        )

    assert result["available"] is True
    assert result["identifier"] == "ENG-999"
    assert "linear.app" in result["url"]
    mock_client.create_issue.assert_called_once()
    call_kwargs = mock_client.create_issue.call_args[1]
    assert call_kwargs["priority"] == 1  # urgent maps to 1


def test_create_tool_priority_mapping() -> None:
    from app.tools.LinearCreateIssueTool import _PRIORITY_MAP

    assert _PRIORITY_MAP["urgent"] == 1
    assert _PRIORITY_MAP["high"] == 2
    assert _PRIORITY_MAP["medium"] == 3
    assert _PRIORITY_MAP["low"] == 4
    assert _PRIORITY_MAP["none"] == 0
