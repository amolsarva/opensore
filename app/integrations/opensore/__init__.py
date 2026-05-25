"""Local telemetry from the tracer-cloud/opensore Hugging Face dataset (OpenRCA-style CSVs)."""

from __future__ import annotations

from app.integrations.opensore.constants import OPENSORE_HF_DATASET_ID
from app.integrations.opensore.csv_grafana_backend import OpenSoreCsvGrafanaBackend
from app.integrations.opensore.hf_remote import (
    extract_openrca_scoring_points,
    infer_opensore_telemetry_relative,
    materialize_opensore_telemetry_from_hub,
    stream_opensore_query_alerts,
    strip_scoring_points_from_alert,
)
from app.integrations.opensore.inject import (
    inject_opensore_into_resolved_integrations,
    resolve_opensore_telemetry_dir,
)
from app.integrations.opensore.seed_evidence import merge_opensore_seed_into_state

__all__ = (
    "OPENSORE_HF_DATASET_ID",
    "OpenSoreCsvGrafanaBackend",
    "extract_openrca_scoring_points",
    "infer_opensore_telemetry_relative",
    "inject_opensore_into_resolved_integrations",
    "merge_opensore_seed_into_state",
    "materialize_opensore_telemetry_from_hub",
    "resolve_opensore_telemetry_dir",
    "stream_opensore_query_alerts",
    "strip_scoring_points_from_alert",
)
