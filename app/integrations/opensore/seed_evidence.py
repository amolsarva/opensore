"""Pre-load OpenRCA / Hugging Face CSV telemetry into investigation evidence.

Uses the same stack as ``infra/opensore-dataset/query_opensore_telemetry.py``: ``OpenSoreCsvGrafanaBackend``
plus ``query_grafana_*`` tool functions so evidence matches normal tool output shapes.
"""

from __future__ import annotations

from typing import Any

from app.integrations.opensore.csv_grafana_backend import OpenSoreCsvGrafanaBackend
from app.integrations.opensore.grafana_mappers import (
    _map_grafana_logs,
    _map_grafana_metrics,
    _map_grafana_traces,
)
from app.integrations.opensore.inject import (
    inject_opensore_into_resolved_integrations,
    resolve_opensore_telemetry_dir,
)
from app.tools.GrafanaLogsTool import query_grafana_logs
from app.tools.GrafanaMetricsTool import query_grafana_metrics
from app.tools.GrafanaTracesTool import query_grafana_traces


def merge_opensore_seed_into_state(
    raw_alert: dict[str, Any],
    resolved_integrations: dict[str, Any] | None,
    existing_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a partial state dict: ``resolved_integrations`` and merged ``evidence``."""
    merged = inject_opensore_into_resolved_integrations(raw_alert, resolved_integrations)
    if merged is None:
        merged = dict(resolved_integrations or {})

    telemetry_dir = resolve_opensore_telemetry_dir(raw_alert)
    evidence = dict(existing_evidence or {})

    if telemetry_dir is None:
        return {"resolved_integrations": merged, "evidence": evidence}

    backend = OpenSoreCsvGrafanaBackend(telemetry_dir=telemetry_dir, alert_fixture=raw_alert)

    evidence.update(
        {
            "opensore_telemetry_dir": str(telemetry_dir),
            "opensore_telemetry_seed": True,
        }
    )
    evidence.update(
        _map_grafana_metrics(
            query_grafana_metrics(
                metric_name="",
                service_name=None,
                grafana_backend=backend,
            )
        )
    )
    evidence.update(
        _map_grafana_logs(
            query_grafana_logs(
                service_name="",
                pipeline_name="",
                execution_run_id=None,
                time_range_minutes=60,
                limit=200,
                grafana_endpoint=None,
                grafana_api_key=None,
                grafana_backend=backend,
            )
        )
    )
    evidence.update(
        _map_grafana_traces(
            query_grafana_traces(
                service_name="",
                execution_run_id=None,
                limit=50,
                grafana_endpoint=None,
                grafana_api_key=None,
                grafana_backend=backend,
            )
        )
    )

    return {"resolved_integrations": merged, "evidence": evidence}
