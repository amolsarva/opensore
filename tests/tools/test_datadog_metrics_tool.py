"""Tests for the completed DatadogMetricsTool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.DataDogMetricsTool import query_datadog_metrics
from tests.tools.conftest import BaseToolContract, mock_agent_state


class TestDataDogMetricsToolContract(BaseToolContract):
    def get_tool_under_test(self):
        return query_datadog_metrics.__opensore_registered_tool__


def test_is_available_false_when_not_verified() -> None:
    rt = query_datadog_metrics.__opensore_registered_tool__
    assert rt.is_available({}) is False
    assert rt.is_available({"datadog": {}}) is False
    assert rt.is_available({"datadog": {"connection_verified": False}}) is False


def test_is_available_true_when_verified() -> None:
    rt = query_datadog_metrics.__opensore_registered_tool__
    assert rt.is_available({"datadog": {"connection_verified": True}}) is True


def test_extract_params_maps_fields() -> None:
    rt = query_datadog_metrics.__opensore_registered_tool__
    sources = mock_agent_state()
    params = rt.extract_params(sources)
    assert "metric_name" in params
    assert params["api_key"] == "dd_api_key_test"


def test_run_returns_error_without_credentials() -> None:
    result = query_datadog_metrics(metric_name="system.cpu.user")
    assert result["available"] is False
    assert result["data_points"] == 0
    assert result["metrics"] == []


def test_run_success() -> None:
    mock_client = MagicMock()
    mock_client.query_metrics.return_value = {
        "success": True,
        "timestamps": ["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z"],
        "values": [10.0, 20.0],
    }

    # DatadogClient is lazy-imported inside the function — patch at the source
    with patch("app.services.datadog.DatadogClient", return_value=mock_client):
        result = query_datadog_metrics(
            metric_name="system.cpu.user",
            time_range_minutes=30,
            api_key="fake-api-key",
            app_key="fake-app-key",
            site="datadoghq.com",
        )

    assert result["available"] is True
    assert result["data_points"] == 2
    assert result["stats"]["min"] == 10.0
    assert result["stats"]["max"] == 20.0
    assert result["stats"]["avg"] == 15.0
    assert result["query"] == "avg:system.cpu.user{*}"


def test_run_custom_query_overrides_metric_name() -> None:
    mock_client = MagicMock()
    mock_client.query_metrics.return_value = {"success": True, "timestamps": [], "values": []}

    with patch("app.services.datadog.DatadogClient", return_value=mock_client):
        result = query_datadog_metrics(
            metric_name="",
            query="sum:custom.latency{env:prod}",
            api_key="k",
            app_key="a",
        )

    assert result["available"] is True
    assert result["query"] == "sum:custom.latency{env:prod}"


def test_run_propagates_api_error() -> None:
    mock_client = MagicMock()
    mock_client.query_metrics.return_value = {"success": False, "error": "403 Forbidden"}

    with patch("app.services.datadog.DatadogClient", return_value=mock_client):
        result = query_datadog_metrics(
            metric_name="system.mem.used",
            api_key="k",
            app_key="a",
        )

    assert result["available"] is False
    assert result["data_points"] == 0


def test_run_metadata() -> None:
    rt = query_datadog_metrics.__opensore_registered_tool__
    assert rt.name == "query_datadog_metrics"
    assert rt.source == "datadog"
