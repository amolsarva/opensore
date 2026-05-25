"""Unit tests for PagerDuty tools — mocked HTTP, no live credentials needed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.pagerduty.client import PagerDutyClient, PagerDutyConfig, make_pagerduty_client
from app.tools.PagerDutyAddNoteTool import PagerDutyAddNoteTool
from app.tools.PagerDutyIncidentsTool import PagerDutyIncidentsTool
from app.tools.PagerDutyOnCallTool import PagerDutyOnCallTool

# ---------------------------------------------------------------------------
# Config / factory
# ---------------------------------------------------------------------------


def test_make_pagerduty_client_empty_token_returns_none() -> None:
    assert make_pagerduty_client("") is None
    assert make_pagerduty_client(None) is None  # type: ignore[arg-type]


def test_make_pagerduty_client_with_token_returns_client() -> None:
    client = make_pagerduty_client("abc123")
    assert client is not None
    assert isinstance(client, PagerDutyClient)


def test_config_headers_contain_token() -> None:
    cfg = PagerDutyConfig(api_token="tok-xyz", from_email="ops@example.com")
    assert "tok-xyz" in cfg.headers["Authorization"]
    assert cfg.headers["From"] == "ops@example.com"


def test_config_headers_no_from_when_empty() -> None:
    cfg = PagerDutyConfig(api_token="tok-xyz")
    assert "From" not in cfg.headers


# ---------------------------------------------------------------------------
# PagerDutyIncidentsTool
# ---------------------------------------------------------------------------


def test_incidents_tool_metadata() -> None:
    tool = PagerDutyIncidentsTool()
    assert tool.name == "pagerduty_incidents"
    assert tool.source == "pagerduty"
    assert "api_token" in tool.input_schema["properties"]


def test_incidents_tool_not_available_when_unconfigured() -> None:
    tool = PagerDutyIncidentsTool()
    assert not tool.is_available({})
    assert not tool.is_available({"pagerduty": {}})
    assert not tool.is_available({"pagerduty": {"connection_verified": False}})


def test_incidents_tool_available_when_verified() -> None:
    tool = PagerDutyIncidentsTool()
    assert tool.is_available({"pagerduty": {"connection_verified": True}})


def test_incidents_tool_returns_error_without_token() -> None:
    tool = PagerDutyIncidentsTool()
    result = tool.run(api_token="")
    assert result["available"] is False
    assert "configured" in result["error"].lower()


def test_incidents_tool_list_success() -> None:
    tool = PagerDutyIncidentsTool()
    mock_result = {
        "success": True,
        "incidents": [
            {
                "id": "P1234",
                "incident_number": 42,
                "title": "DB latency spike",
                "status": "triggered",
                "urgency": "high",
                "created_at": "2024-01-01T00:00:00Z",
                "html_url": "https://example.pagerduty.com/incidents/P1234",
                "service": "payments-service",
                "assigned_to": ["oncall-alice"],
                "escalation_policy": "Engineering",
            }
        ],
        "total": 1,
    }
    with patch("app.tools.PagerDutyIncidentsTool.make_pagerduty_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_incidents.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(api_token="tok", statuses=["triggered"])

    assert result["available"] is True
    assert len(result["incidents"]) == 1
    assert result["incidents"][0]["title"] == "DB latency spike"


def test_incidents_tool_get_single_incident() -> None:
    tool = PagerDutyIncidentsTool()
    mock_result = {
        "success": True,
        "incident": {
            "id": "P1234",
            "incident_number": 42,
            "title": "DB latency spike",
            "status": "triggered",
            "urgency": "high",
            "created_at": "2024-01-01T00:00:00Z",
            "resolved_at": "",
            "html_url": "https://example.pagerduty.com/incidents/P1234",
            "service": "payments-service",
            "body": "High p99 latency detected on payments RDS instance.",
            "assigned_to": ["oncall-alice"],
            "alert_counts": {"triggered": 3, "resolved": 0},
        },
    }
    with patch("app.tools.PagerDutyIncidentsTool.make_pagerduty_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_incident.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(api_token="tok", incident_id="P1234")

    assert result["available"] is True
    assert result["incident"]["title"] == "DB latency spike"


# ---------------------------------------------------------------------------
# PagerDutyOnCallTool
# ---------------------------------------------------------------------------


def test_oncall_tool_metadata() -> None:
    tool = PagerDutyOnCallTool()
    assert tool.name == "pagerduty_oncall"
    assert "schedule_ids" in tool.input_schema["properties"]


def test_oncall_tool_returns_oncall_list() -> None:
    tool = PagerDutyOnCallTool()
    mock_result = {
        "success": True,
        "oncalls": [
            {
                "user": "Alice Engineer",
                "user_email": "alice@example.com",
                "schedule": "Engineering Primary",
                "escalation_policy": "Engineering",
                "escalation_level": 1,
                "start": "2024-01-01T00:00:00Z",
                "end": "2024-01-08T00:00:00Z",
            }
        ],
    }
    with patch("app.tools.PagerDutyOnCallTool.make_pagerduty_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get_oncall.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(api_token="tok")

    assert result["available"] is True
    assert result["oncalls"][0]["user"] == "Alice Engineer"


# ---------------------------------------------------------------------------
# PagerDutyAddNoteTool
# ---------------------------------------------------------------------------


def test_add_note_tool_metadata() -> None:
    tool = PagerDutyAddNoteTool()
    assert tool.name == "pagerduty_add_note"
    assert tool.source == "pagerduty"
    assert "incident_id" in tool.input_schema["properties"]
    assert "content" in tool.input_schema["properties"]


def test_add_note_tool_requires_incident_id() -> None:
    tool = PagerDutyAddNoteTool()
    result = tool.run(api_token="tok", from_email="ops@x.com", incident_id="", content="rca")
    assert result["available"] is False
    assert "incident_id" in result["error"]


def test_add_note_tool_requires_content() -> None:
    tool = PagerDutyAddNoteTool()
    result = tool.run(api_token="tok", from_email="ops@x.com", incident_id="P123", content="")
    assert result["available"] is False
    assert "content" in result["error"]


def test_add_note_tool_success() -> None:
    tool = PagerDutyAddNoteTool()
    mock_result = {"success": True, "note_id": "N999", "created_at": "2024-01-01T00:00:00Z"}
    with patch("app.tools.PagerDutyAddNoteTool.make_pagerduty_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.add_note.return_value = mock_result
        mock_factory.return_value = mock_client

        result = tool.run(
            api_token="tok",
            from_email="ops@example.com",
            incident_id="P1234",
            content="Root cause: DB connection pool exhaustion.",
        )

    assert result["available"] is True
    assert result["note_id"] == "N999"
    assert result["incident_id"] == "P1234"
