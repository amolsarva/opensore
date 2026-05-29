"""Pre-load opensore telemetry into investigation evidence (stub — Grafana tools removed)."""

from __future__ import annotations

from typing import Any

from app.integrations.opensore.inject import (
    inject_opensore_into_resolved_integrations,
    resolve_opensore_telemetry_dir,
)


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

    evidence.update(
        {
            "opensore_telemetry_dir": str(telemetry_dir),
            "opensore_telemetry_seed": True,
        }
    )
    return {"resolved_integrations": merged, "evidence": evidence}
