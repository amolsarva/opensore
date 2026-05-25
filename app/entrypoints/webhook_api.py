"""Inbound webhook router — receive alert payloads and auto-trigger investigations.

Supports three payload formats:
  - Generic (any JSON with name/title/description/severity)
  - PagerDuty webhook v3 (incident.triggered events)
  - Datadog webhook (monitor alert notifications)
  - Alertmanager (Prometheus alerting webhook)

POST /webhooks/investigate
  Body: alert payload in any of the above formats
  Returns: investigation summary, root cause, runbook_id, similar incidents

Security: requests are accepted from any source by default.
Set WEBHOOK_SECRET env var to enable HMAC-SHA256 signature verification
(header: X-Webhook-Signature: sha256=<hex>).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class WebhookInvestigateResponse(BaseModel):
    ok: bool
    alert_name: str
    root_cause: str
    root_cause_category: str
    validity_score: float
    remediation_steps: list[str]
    runbook_id: str | None
    runbook_path: str | None
    similar_incidents: list[dict[str, Any]]
    is_noise: bool


# ---------------------------------------------------------------------------
# Payload normalizers — convert provider-specific shapes to raw_alert dict
# ---------------------------------------------------------------------------


def _normalize_pagerduty(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extract alert data from a PagerDuty v3 webhook event."""
    event = body.get("event", {})
    event_type = event.get("event_type", "")
    if not event_type.startswith("incident."):
        return None
    data = event.get("data", {})
    incident = data if isinstance(data, dict) else {}
    return {
        "name": incident.get("title", event_type),
        "service": incident.get("service", {}).get("name", ""),
        "severity": incident.get("urgency", ""),
        "status": incident.get("status", ""),
        "incident_id": incident.get("id", ""),
        "source": "pagerduty",
        "description": incident.get("summary", ""),
    }


def _normalize_datadog(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extract alert data from a Datadog monitor webhook."""
    if "alert_title" not in body and "title" not in body:
        return None
    return {
        "name": body.get("alert_title") or body.get("title", "Datadog Alert"),
        "service": body.get("tags", {}).get("service", "")
        if isinstance(body.get("tags"), dict)
        else "",
        "severity": body.get("alert_transition", body.get("priority", "")),
        "metric": body.get("metric", ""),
        "host": body.get("hostname", body.get("host", "")),
        "description": body.get("body", body.get("text", "")),
        "source": "datadog",
        "monitor_id": str(body.get("id", "")),
    }


def _normalize_alertmanager(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extract alert data from a Prometheus/Alertmanager webhook."""
    alerts = body.get("alerts", [])
    if not alerts:
        return None
    alert = alerts[0]
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    return {
        "name": labels.get("alertname", annotations.get("summary", "Unknown Alert")),
        "service": labels.get("service", labels.get("job", "")),
        "severity": labels.get("severity", ""),
        "namespace": labels.get("namespace", ""),
        "instance": labels.get("instance", ""),
        "description": annotations.get("description", annotations.get("summary", "")),
        "source": "alertmanager",
        "all_alerts_count": len(alerts),
    }


def _normalize_generic(body: dict[str, Any]) -> dict[str, Any]:
    """Passthrough normalizer for custom/generic alert payloads."""
    return {
        "name": body.get("name") or body.get("title") or body.get("alert_name") or "Webhook Alert",
        "service": body.get("service") or body.get("source_service") or "",
        "severity": body.get("severity") or body.get("priority") or "",
        "description": body.get("description") or body.get("summary") or body.get("message") or "",
        "environment": body.get("environment") or body.get("env") or "",
        "source": "webhook",
        **{
            k: v
            for k, v in body.items()
            if k not in ("name", "title", "service", "severity", "description")
        },
    }


def _detect_and_normalize(body: dict[str, Any]) -> dict[str, Any]:
    """Auto-detect payload format and return a normalized raw_alert dict."""
    if "event" in body and "data" in body.get("event", {}):
        normalized = _normalize_pagerduty(body)
        if normalized:
            return normalized
    if "alerts" in body and isinstance(body.get("alerts"), list):
        normalized = _normalize_alertmanager(body)
        if normalized:
            return normalized
    if "alert_title" in body or ("title" in body and "alert_transition" in body):
        normalized = _normalize_datadog(body)
        if normalized:
            return normalized
    return _normalize_generic(body)


# ---------------------------------------------------------------------------
# HMAC verification (optional)
# ---------------------------------------------------------------------------


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        return True
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/investigate", response_model=WebhookInvestigateResponse)
async def webhook_investigate(request: Request) -> WebhookInvestigateResponse:
    """Accept an inbound alert and run an investigation.

    Supports PagerDuty v3, Datadog, Alertmanager, and generic JSON payloads.
    Returns the RCA summary synchronously (blocking until the investigation completes).

    For high-volume environments, consider putting a queue in front of this endpoint.
    """
    raw_body = await request.body()
    sig = request.headers.get("X-Webhook-Signature") or request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(raw_body, sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature."
        )

    try:
        body: dict[str, Any] = await request.json()
    except Exception as json_exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Request body must be valid JSON."
        ) from json_exc

    raw_alert = _detect_and_normalize(body)
    alert_name = str(raw_alert.get("name") or "Webhook Alert")
    logger.info("[webhook] received alert: %s (source=%s)", alert_name, raw_alert.get("source"))

    try:
        from app.pipeline.pipeline import run_investigation
        from app.state import make_initial_state

        state = make_initial_state(raw_alert)
        result_state = run_investigation(state)
    except Exception as exc:
        logger.exception("[webhook] investigation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Investigation failed: {exc}",
        ) from exc

    return WebhookInvestigateResponse(
        ok=True,
        alert_name=str(result_state.get("alert_name") or alert_name),
        root_cause=str(result_state.get("root_cause") or ""),
        root_cause_category=str(result_state.get("root_cause_category") or "unknown"),
        validity_score=float(result_state.get("validity_score") or 0.0),
        remediation_steps=list(result_state.get("remediation_steps") or []),
        runbook_id=result_state.get("runbook_id"),
        runbook_path=result_state.get("runbook_path"),
        similar_incidents=list(result_state.get("similar_incidents") or []),
        is_noise=bool(result_state.get("is_noise")),
    )


@router.get("/investigate/schema")
def webhook_schema() -> dict[str, Any]:
    """Return the response schema and supported payload examples."""
    return {
        "response_schema": WebhookInvestigateResponse.model_json_schema(),
        "supported_formats": ["pagerduty_v3", "datadog", "alertmanager", "generic"],
        "generic_example": {
            "name": "HighDBLatency",
            "service": "payments-api",
            "severity": "critical",
            "description": "p99 latency on payments RDS exceeded 2000ms",
            "environment": "production",
        },
        "auth": "Set WEBHOOK_SECRET env var to enable HMAC-SHA256 verification (X-Webhook-Signature header).",
    }
