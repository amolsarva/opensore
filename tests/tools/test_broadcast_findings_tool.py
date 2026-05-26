"""Tests for BroadcastFindingsTool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.BroadcastFindingsTool import broadcast_findings


def test_tool_metadata() -> None:
    assert broadcast_findings.name == "broadcast_findings"
    assert broadcast_findings.source == "broadcast"
    assert "summary" in broadcast_findings.requires


def test_not_available_when_no_channels_configured() -> None:
    assert broadcast_findings.is_available({}) is False
    assert broadcast_findings.is_available({"pagerduty": {}}) is False


def test_available_when_pagerduty_verified() -> None:
    assert broadcast_findings.is_available({"pagerduty": {"connection_verified": True}}) is True


def test_available_when_linear_verified() -> None:
    assert broadcast_findings.is_available({"linear": {"connection_verified": True}}) is True


def test_available_when_jira_verified() -> None:
    assert broadcast_findings.is_available({"jira": {"connection_verified": True}}) is True


def test_run_requires_summary() -> None:
    result = broadcast_findings.run(summary="")
    assert result["available"] is False


def test_run_no_channels_configured() -> None:
    result = broadcast_findings.run(summary="RCA summary", alert_name="HighDB")
    assert result["available"] is True
    assert result["dispatched"] == 0
    assert "No output channels" in result["message"]


def test_run_dispatches_to_pagerduty() -> None:
    mock_pd = MagicMock()
    mock_pd.add_note.return_value = {"success": True, "note_id": "note-123"}
    mock_pd.__enter__ = MagicMock(return_value=mock_pd)
    mock_pd.__exit__ = MagicMock(return_value=False)

    with patch(
        "app.tools.BroadcastFindingsTool.BroadcastFindingsTool._dispatch_pagerduty"
    ) as mock_dispatch:
        mock_dispatch.return_value = {"ok": True, "note_id": "note-123"}
        result = broadcast_findings.run(
            summary="DB pool exhausted — add PgBouncer.",
            alert_name="HighDBLatency",
            pagerduty_incident_id="INC-001",
            pagerduty_api_token="fake-token",
        )

    assert result["available"] is True
    assert result["dispatched"] == 1
    assert "pagerduty" in result["results"]


def test_run_dispatches_to_linear() -> None:
    with patch(
        "app.tools.BroadcastFindingsTool.BroadcastFindingsTool._dispatch_linear"
    ) as mock_dispatch:
        mock_dispatch.return_value = {"ok": True, "identifier": "ENG-42"}
        result = broadcast_findings.run(
            summary="Memory leak in worker process.",
            alert_name="HighMemUsage",
            linear_team_id="team-abc",
            linear_api_key="lin-key",
        )

    assert result["dispatched"] == 1
    assert "linear" in result["results"]


def test_run_partial_failure_handled() -> None:
    def _fail(*args, **kwargs):
        raise Exception("Network error")

    with (
        patch(
            "app.tools.BroadcastFindingsTool.BroadcastFindingsTool._dispatch_pagerduty",
            side_effect=_fail,
        ),
        patch("app.tools.BroadcastFindingsTool.BroadcastFindingsTool._dispatch_linear") as mock_lin,
    ):
        mock_lin.return_value = {"ok": True}
        result = broadcast_findings.run(
            summary="Incident summary",
            pagerduty_incident_id="INC-X",
            pagerduty_api_token="tok",
            linear_team_id="team-id",
            linear_api_key="lin-key",
        )

    assert result["total_channels"] == 2
    assert result["dispatched"] == 1
    assert result["results"]["pagerduty"]["ok"] is False
    assert "error" in result["results"]["pagerduty"]


def test_extract_params_shape() -> None:
    sources = {
        "pagerduty": {"connection_verified": True, "default_incident_id": ""},
        "linear": {"connection_verified": True, "default_team_id": "team-xyz"},
    }
    params = broadcast_findings.extract_params(sources)
    assert "summary" in params
    assert params["linear_team_id"] == "team-xyz"
