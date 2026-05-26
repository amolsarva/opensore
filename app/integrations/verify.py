"""Verification facade: per-service verifiers and the top-level verify_integrations runner."""

from __future__ import annotations

from typing import Any

from app.integrations import _verification_adapters as _adapters
from app.integrations.catalog import (
    resolve_effective_integrations as _resolve_effective_integrations,
)
from app.integrations.registry import CORE_VERIFY_SERVICES, SUPPORTED_VERIFY_SERVICES

# Re-export type and all verifiers so external callers keep working.
VerifierFn = _adapters.VerifierFn

_verify_bitbucket = _adapters._verify_bitbucket
_verify_discord = _adapters._verify_discord
_verify_github = _adapters._verify_github
_verify_google_docs = _adapters._verify_google_docs
_verify_openclaw = _adapters._verify_openclaw
_verify_slack = _adapters._verify_slack
_verify_telegram = _adapters._verify_telegram
_verify_tracer = _adapters._verify_tracer
_verify_twilio = _adapters._verify_twilio
_verify_whatsapp = _adapters._verify_whatsapp

_result = _adapters.result

VERIFIER_REGISTRY: dict[str, VerifierFn] = {
    spec_service: (
        (lambda s, c: _adapters._verify_slack(s, c, send_slack_test=False))
        if spec_service == "slack"
        else _adapters.__dict__[f"_verify_{spec_service}"]
    )
    for spec_service in SUPPORTED_VERIFY_SERVICES
}


def resolve_effective_integrations() -> dict[str, dict[str, Any]]:
    """Resolve effective local integrations from ~/.config/opensore and environment variables."""
    return _resolve_effective_integrations()


def verify_integrations(
    service: str | None = None,
    *,
    send_slack_test: bool = False,
) -> list[dict[str, str]]:
    """Run verification checks for configured integrations."""
    effective_integrations = resolve_effective_integrations()
    services = [service] if service else list(SUPPORTED_VERIFY_SERVICES)
    results: list[dict[str, str]] = []

    for current_service in services:
        verifier = VERIFIER_REGISTRY.get(current_service)
        if verifier is None:
            results.append(
                _result(
                    current_service,
                    "-",
                    "failed",
                    "Verification is not supported for this service.",
                )
            )
            continue

        integration = effective_integrations.get(current_service)

        if current_service == "slack":
            if not integration:
                results.append(
                    _result("slack", "-", "missing", "SLACK_WEBHOOK_URL is not configured.")
                )
                continue
            results.append(
                _adapters._verify_slack(
                    source=str(integration["source"]),
                    config=dict(integration["config"]),
                    send_slack_test=send_slack_test,
                )
            )
            continue

        if not integration:
            results.append(
                _result(current_service, "-", "missing", "Not configured in local store or env.")
            )
            continue

        try:
            results.append(verifier(str(integration["source"]), dict(integration["config"])))
        except Exception as exc:
            results.append(
                _result(current_service, str(integration.get("source", "-")), "failed", str(exc))
            )

    return results


def format_verification_results(results: list[dict[str, str]]) -> str:
    """Render verification results as a compact terminal table."""
    lines = ["", "  SERVICE    SOURCE       STATUS      DETAIL"]
    for row in results:
        service = row.get("service", "?")
        source = row.get("source", "-")
        status = row.get("status", "?")
        detail = row.get("detail", "")
        lines.append(f"  {service:<10}{source:<13}{status:<12}{detail}")
    lines.append("")
    return "\n".join(lines)


def verification_exit_code(
    results: list[dict[str, str]],
    *,
    requested_service: str | None = None,
) -> int:
    """Return a CLI exit code for a verification run."""
    if any(row.get("status") == "failed" for row in results):
        return 1
    if requested_service:
        return 1 if any(row.get("status") in {"missing", "failed"} for row in results) else 0
    core_results = [row for row in results if row.get("service") in CORE_VERIFY_SERVICES]
    if not any(row.get("status") == "passed" for row in core_results):
        return 1
    return 0


__all__ = [
    "CORE_VERIFY_SERVICES",
    "SUPPORTED_VERIFY_SERVICES",
    "VERIFIER_REGISTRY",
    "VerifierFn",
    "_verify_bitbucket",
    "_verify_discord",
    "_verify_github",
    "_verify_google_docs",
    "_verify_openclaw",
    "_verify_slack",
    "_verify_telegram",
    "_verify_tracer",
    "_verify_twilio",
    "_verify_whatsapp",
    "format_verification_results",
    "resolve_effective_integrations",
    "verification_exit_code",
    "verify_integrations",
]
