"""Datadog metrics query tool — retrieve time-series metrics for investigation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.tools.tool_decorator import tool


class QueryDatadogMetricsInput(BaseModel):
    metric_name: str = Field(
        description="Datadog metric name to query, for example `system.cpu.user`."
    )
    time_range_minutes: int = Field(
        default=60,
        description="Lookback window in minutes for metric retrieval.",
    )
    query: str | None = Field(
        default=None,
        description="Optional full Datadog metrics query string override (e.g. 'avg:system.cpu.user{service:web}').",
    )


class QueryDatadogMetricsOutput(BaseModel):
    source: str = Field(description="Evidence source label.")
    available: bool = Field(description="Whether Datadog metrics query is available.")
    metric_name: str = Field(description="Metric name requested.")
    query: str = Field(description="Query string executed against Datadog.")
    metrics: list[dict[str, Any]] = Field(
        default_factory=list, description="Time-series data points [{timestamp, value}]."
    )
    stats: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics: min, max, avg, latest.",
    )
    data_points: int = Field(default=0, description="Number of data points returned.")
    error: str | None = Field(default=None, description="Error details when unavailable.")


def _metrics_is_available(sources: dict[str, dict]) -> bool:
    return bool(sources.get("datadog", {}).get("connection_verified"))


def _metrics_extract_params(sources: dict[str, dict]) -> dict[str, Any]:
    dd = sources.get("datadog", {})
    return {
        "metric_name": "",
        "time_range_minutes": 60,
        "api_key": dd.get("api_key", ""),
        "app_key": dd.get("app_key", ""),
        "site": dd.get("site", "datadoghq.com"),
    }


@tool(
    name="query_datadog_metrics",
    source="datadog",
    description=(
        "Query Datadog metrics for infrastructure and application performance data. "
        "Returns time-series data points with summary statistics (min, max, avg, latest)."
    ),
    use_cases=[
        "Investigating CPU or memory spikes correlated with an alert",
        "Reviewing custom pipeline throughput metrics over time",
        "Checking host resource utilisation trends",
        "Correlating error rate spikes with infrastructure metrics",
    ],
    requires=[],
    source_id="datadog_metrics_api",
    evidence_type="metrics",
    side_effect_level="read_only",
    examples=[
        "Check `system.cpu.user` around incident window for saturation patterns.",
        "Run a custom metrics query string for service-specific error-rate metrics.",
    ],
    anti_examples=["Use this tool for log content or deployment timeline evidence."],
    input_model=QueryDatadogMetricsInput,
    output_model=QueryDatadogMetricsOutput,
    injected_params=("api_key", "app_key", "site"),
    is_available=_metrics_is_available,
    extract_params=_metrics_extract_params,
)
def query_datadog_metrics(
    metric_name: str,
    time_range_minutes: int = 60,
    query: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Query Datadog metrics API v1 for time-series data."""
    from app.integrations.config_models import DatadogIntegrationConfig
    from app.services.datadog import DatadogClient

    api_key = str(kwargs.get("api_key") or "")
    app_key = str(kwargs.get("app_key") or "")
    site = str(kwargs.get("site") or "datadoghq.com")

    if not api_key or not app_key:
        return {
            "source": "datadog",
            "available": False,
            "error": "Missing Datadog api_key or app_key.",
            "metric_name": metric_name,
            "query": "",
            "metrics": [],
            "stats": {},
            "data_points": 0,
        }

    config = DatadogIntegrationConfig(api_key=api_key, app_key=app_key, site=site)
    client = DatadogClient(config)

    now = datetime.now(UTC)
    start = now - timedelta(minutes=time_range_minutes)
    dd_query = query or f"avg:{metric_name}{{*}}"

    result = client.query_metrics(dd_query, start=start, end=now)

    if not result.get("success"):
        return {
            "source": "datadog",
            "available": False,
            "error": result.get("error", "Metrics query failed."),
            "metric_name": metric_name,
            "query": dd_query,
            "metrics": [],
            "stats": {},
            "data_points": 0,
        }

    timestamps: list[str] = result.get("timestamps", [])
    values: list[float] = result.get("values", [])
    metrics = [{"timestamp": ts, "value": v} for ts, v in zip(timestamps, values)]

    stats: dict[str, Any] = {}
    if values:
        stats = {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "latest": values[-1],
        }

    return {
        "source": "datadog",
        "available": True,
        "metric_name": metric_name,
        "query": dd_query,
        "time_range_minutes": time_range_minutes,
        "metrics": metrics,
        "stats": stats,
        "data_points": len(metrics),
    }
