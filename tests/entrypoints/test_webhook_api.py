"""Unit tests for the inbound webhook API — payload normalization and routing."""

from __future__ import annotations

from app.entrypoints.webhook_api import (
    _detect_and_normalize,
    _normalize_alertmanager,
    _normalize_datadog,
    _normalize_generic,
    _normalize_pagerduty,
    _verify_signature,
)

# ---------------------------------------------------------------------------
# PagerDuty normalizer
# ---------------------------------------------------------------------------


def test_pagerduty_normalizer_extracts_incident() -> None:
    body = {
        "event": {
            "event_type": "incident.triggered",
            "data": {
                "id": "P1234",
                "title": "Payments DB latency",
                "urgency": "high",
                "status": "triggered",
                "summary": "High p99 latency on payments RDS",
                "service": {"name": "payments-api"},
            },
        }
    }
    result = _normalize_pagerduty(body)
    assert result is not None
    assert result["name"] == "Payments DB latency"
    assert result["severity"] == "high"
    assert result["source"] == "pagerduty"
    assert result["incident_id"] == "P1234"


def test_pagerduty_normalizer_returns_none_for_non_incident() -> None:
    body = {"event": {"event_type": "service.updated", "data": {}}}
    assert _normalize_pagerduty(body) is None


def test_pagerduty_normalizer_returns_none_for_unrecognized_body() -> None:
    assert _normalize_pagerduty({"something": "else"}) is None


# ---------------------------------------------------------------------------
# Datadog normalizer
# ---------------------------------------------------------------------------


def test_datadog_normalizer_extracts_alert() -> None:
    body = {
        "alert_title": "High error rate on payments",
        "alert_transition": "Triggered",
        "hostname": "prod-payments-01",
        "metric": "trace.requests.errors",
        "body": "Error rate exceeded 5% threshold for 5 minutes.",
    }
    result = _normalize_datadog(body)
    assert result is not None
    assert result["name"] == "High error rate on payments"
    assert result["host"] == "prod-payments-01"
    assert result["source"] == "datadog"


def test_datadog_normalizer_returns_none_when_no_alert_title() -> None:
    assert _normalize_datadog({"random_key": "value"}) is None


# ---------------------------------------------------------------------------
# Alertmanager normalizer
# ---------------------------------------------------------------------------


def test_alertmanager_normalizer_extracts_first_alert() -> None:
    body = {
        "alerts": [
            {
                "labels": {
                    "alertname": "HighCPU",
                    "severity": "critical",
                    "service": "api-server",
                    "namespace": "production",
                },
                "annotations": {"description": "CPU usage above 90% for 10 minutes"},
            },
            {
                "labels": {"alertname": "LowMemory", "severity": "warning"},
                "annotations": {},
            },
        ]
    }
    result = _normalize_alertmanager(body)
    assert result is not None
    assert result["name"] == "HighCPU"
    assert result["severity"] == "critical"
    assert result["service"] == "api-server"
    assert result["all_alerts_count"] == 2
    assert result["source"] == "alertmanager"


def test_alertmanager_normalizer_returns_none_for_empty_alerts() -> None:
    assert _normalize_alertmanager({"alerts": []}) is None
    assert _normalize_alertmanager({}) is None


# ---------------------------------------------------------------------------
# Generic normalizer
# ---------------------------------------------------------------------------


def test_generic_normalizer_uses_name_field() -> None:
    body = {"name": "HighMemory", "service": "worker", "severity": "warning", "extra": "data"}
    result = _normalize_generic(body)
    assert result["name"] == "HighMemory"
    assert result["service"] == "worker"
    assert result["extra"] == "data"


def test_generic_normalizer_falls_back_to_title() -> None:
    body = {"title": "Payment Failure", "description": "Spike in payment errors"}
    result = _normalize_generic(body)
    assert result["name"] == "Payment Failure"
    assert result["description"] == "Spike in payment errors"


def test_generic_normalizer_default_name_when_empty() -> None:
    result = _normalize_generic({})
    assert result["name"] == "Webhook Alert"


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


def test_detect_pagerduty() -> None:
    body = {
        "event": {
            "event_type": "incident.triggered",
            "data": {"title": "DB Down", "urgency": "high", "status": "triggered", "id": "P1"},
        }
    }
    result = _detect_and_normalize(body)
    assert result["source"] == "pagerduty"


def test_detect_alertmanager() -> None:
    body = {
        "alerts": [{"labels": {"alertname": "HighCPU", "severity": "critical"}, "annotations": {}}]
    }
    result = _detect_and_normalize(body)
    assert result["source"] == "alertmanager"


def test_detect_generic_fallback() -> None:
    body = {"name": "MyAlert", "service": "api"}
    result = _detect_and_normalize(body)
    assert result["name"] == "MyAlert"
    assert result["source"] == "webhook"


# ---------------------------------------------------------------------------
# HMAC verification
# ---------------------------------------------------------------------------


def test_verify_signature_no_secret_always_passes() -> None:
    assert _verify_signature(b"payload", None) is True
    assert _verify_signature(b"payload", "sha256=anything") is True


def test_verify_signature_with_secret_correct_sig(monkeypatch) -> None:
    import hashlib
    import hmac as hmac_mod

    monkeypatch.setenv("WEBHOOK_SECRET", "mysecret")
    payload = b'{"test": true}'
    expected_hex = hmac_mod.new(b"mysecret", payload, hashlib.sha256).hexdigest()
    sig = f"sha256={expected_hex}"
    assert _verify_signature(payload, sig) is True


def test_verify_signature_with_secret_wrong_sig(monkeypatch) -> None:
    monkeypatch.setenv("WEBHOOK_SECRET", "mysecret")
    assert _verify_signature(b"payload", "sha256=wronghex") is False


def test_verify_signature_missing_header_fails_when_secret_set(monkeypatch) -> None:
    monkeypatch.setenv("WEBHOOK_SECRET", "mysecret")
    assert _verify_signature(b"payload", None) is False
