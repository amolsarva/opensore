"""Tests for HttpProbeTool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from app.tools.HttpProbeTool import http_probe


def test_tool_metadata() -> None:
    assert http_probe.name == "http_probe"
    assert http_probe.source == "http_probe"
    assert "url" in http_probe.requires


def test_tool_always_available() -> None:
    assert http_probe.is_available({}) is True
    assert http_probe.is_available({"anything": {}}) is True


def test_run_requires_url() -> None:
    result = http_probe.run(url="")
    assert result["available"] is False
    assert "url" in result["error"].lower()


def test_run_success_200() -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = '{"status":"ok"}'
    mock_resp.history = []
    mock_resp.headers = {"content-type": "application/json"}

    with patch("app.tools.HttpProbeTool.httpx.request", return_value=mock_resp):
        result = http_probe.run(url="http://example.com/health", expected_status=200)

    assert result["available"] is True
    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["latency_ms"] >= 0
    assert result["body_excerpt"] == '{"status":"ok"}'
    assert result["redirect_count"] == 0


def test_run_wrong_status_code_ok_false() -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"
    mock_resp.history = []
    mock_resp.headers = {}

    with patch("app.tools.HttpProbeTool.httpx.request", return_value=mock_resp):
        result = http_probe.run(url="http://example.com/health", expected_status=200)

    assert result["ok"] is False
    assert result["status_code"] == 503


def test_run_timeout_returns_error() -> None:
    with patch("app.tools.HttpProbeTool.httpx.request", side_effect=httpx.TimeoutException("timeout")):
        result = http_probe.run(url="http://example.com/health", timeout_seconds=1.0)

    assert result["available"] is True
    assert result["ok"] is False
    assert "timed out" in result["error"]
    assert result["latency_ms"] >= 0


def test_run_connection_error() -> None:
    with patch(
        "app.tools.HttpProbeTool.httpx.request",
        side_effect=Exception("Connection refused"),
    ):
        result = http_probe.run(url="http://192.0.2.1/health")

    assert result["available"] is True
    assert result["ok"] is False
    assert "Connection refused" in result["error"]


def test_run_redirect_count() -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = "OK"
    mock_resp.history = [MagicMock(), MagicMock()]
    mock_resp.headers = {}

    with patch("app.tools.HttpProbeTool.httpx.request", return_value=mock_resp):
        result = http_probe.run(url="http://example.com/", follow_redirects=True)

    assert result["redirect_count"] == 2


def test_ssl_expiry_skipped_for_http() -> None:
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = ""
    mock_resp.history = []
    mock_resp.headers = {}

    with patch("app.tools.HttpProbeTool.httpx.request", return_value=mock_resp):
        result = http_probe.run(url="http://example.com/")

    # No SSL check attempted for plain http
    assert result.get("ssl_expiry_days") is None


def test_extract_params_shape() -> None:
    params = http_probe.extract_params({})
    assert "url" in params
    assert params["method"] == "GET"
    assert params["expected_status"] == 200
