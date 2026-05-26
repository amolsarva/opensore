"""Tests for GrafanaAnnotateTool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from app.tools.GrafanaAnnotateTool import grafana_annotate


def test_tool_metadata() -> None:
    assert grafana_annotate.name == "grafana_annotate"
    assert grafana_annotate.source == "grafana"
    assert "grafana_url" in grafana_annotate.requires
    assert "api_key" in grafana_annotate.requires


def test_not_available_when_unconfigured() -> None:
    assert grafana_annotate.is_available({}) is False
    assert grafana_annotate.is_available({"grafana": {}}) is False
    assert grafana_annotate.is_available({"grafana": {"connection_verified": False}}) is False


def test_available_when_configured() -> None:
    assert grafana_annotate.is_available({"grafana": {"connection_verified": True}}) is True


def test_run_requires_grafana_url() -> None:
    result = grafana_annotate.run(grafana_url="", api_key="token", text="RCA summary")
    assert result["available"] is False


def test_run_requires_text() -> None:
    result = grafana_annotate.run(grafana_url="http://grafana.local", api_key="token", text="")
    assert result["available"] is False


def test_run_success() -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 42, "message": "Annotation added"}
    mock_resp.raise_for_status = MagicMock()

    with patch("app.tools.GrafanaAnnotateTool.httpx.post", return_value=mock_resp) as mock_post:
        result = grafana_annotate.run(
            grafana_url="https://grafana.example.com",
            api_key="glsa_token",
            text="DB connection pool exhausted — root cause identified.",
            tags=["opensore", "rca", "database"],
        )

    assert result["available"] is True
    assert result["annotation_id"] == 42
    assert "grafana.example.com" in result["url"]

    call_kwargs = mock_post.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert "Bearer glsa_token" in headers.get("Authorization", "")


def test_run_with_region_annotation() -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"id": 99, "message": "ok"}
    mock_resp.raise_for_status = MagicMock()

    with patch("app.tools.GrafanaAnnotateTool.httpx.post", return_value=mock_resp):
        result = grafana_annotate.run(
            grafana_url="http://grafana.local",
            api_key="tok",
            text="Incident window",
            time_ms=1700000000000,
            time_end_ms=1700003600000,
            dashboard_uid="abc123",
            panel_id=5,
        )

    assert result["available"] is True


def test_run_http_error() -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)
    mock_resp.raise_for_status.side_effect = error

    with patch("app.tools.GrafanaAnnotateTool.httpx.post", return_value=mock_resp):
        result = grafana_annotate.run(
            grafana_url="http://grafana.local",
            api_key="bad",
            text="test",
        )

    assert result["available"] is False
    assert "401" in result["error"]


def test_extract_params_shape() -> None:
    sources = {"grafana": {"endpoint": "https://g.local", "api_key": "tok", "connection_verified": True}}
    params = grafana_annotate.extract_params(sources)
    assert params["grafana_url"] == "https://g.local"
    assert params["api_key"] == "tok"
