"""Tests for the alert fingerprint deduplication engine."""

from __future__ import annotations

import time

from app.pipeline.fingerprint import (
    check_and_record,
    clear_dedup_cache,
    dedup_stats,
    fingerprint_alert,
)


def setup_function() -> None:
    clear_dedup_cache()


def test_fingerprint_is_deterministic() -> None:
    alert = {"name": "HighDBLatency", "service": "payments", "severity": "critical"}
    fp1 = fingerprint_alert(alert)
    fp2 = fingerprint_alert(alert)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_fingerprint_differs_for_different_alerts() -> None:
    a = {"name": "HighDBLatency", "service": "payments"}
    b = {"name": "HighMemoryUsage", "service": "payments"}
    assert fingerprint_alert(a) != fingerprint_alert(b)


def test_fingerprint_ignores_timestamps_and_ids() -> None:
    base = {"name": "HighCPU", "severity": "warning", "service": "web"}
    a = {**base, "incident_id": "abc-123", "created_at": "2024-01-01T00:00:00Z"}
    b = {**base, "incident_id": "xyz-789", "created_at": "2024-06-15T12:00:00Z"}
    assert fingerprint_alert(a) == fingerprint_alert(b)


def test_fingerprint_alertmanager_labels() -> None:
    alert = {
        "alerts": [
            {
                "labels": {
                    "alertname": "TargetDown",
                    "severity": "critical",
                    "namespace": "production",
                }
            }
        ]
    }
    fp = fingerprint_alert(alert)
    assert isinstance(fp, str) and len(fp) == 64


def test_check_and_record_first_call_not_duplicate() -> None:
    fp = fingerprint_alert({"name": "Test", "service": "svc"})
    assert check_and_record(fp, ttl_seconds=60) is False


def test_check_and_record_second_call_is_duplicate() -> None:
    alert = {"name": "DuplicateTest", "service": "svc", "severity": "high"}
    fp = fingerprint_alert(alert)
    assert check_and_record(fp, ttl_seconds=60) is False
    assert check_and_record(fp, ttl_seconds=60) is True


def test_check_and_record_different_alerts_not_duplicate() -> None:
    fp1 = fingerprint_alert({"name": "Alert1", "service": "svc"})
    fp2 = fingerprint_alert({"name": "Alert2", "service": "svc"})
    assert check_and_record(fp1, ttl_seconds=60) is False
    assert check_and_record(fp2, ttl_seconds=60) is False


def test_dedup_cache_expiry() -> None:
    alert = {"name": "ExpiryTest", "service": "svc"}
    fp = fingerprint_alert(alert)
    # Record with a very short TTL (0.01s)
    assert check_and_record(fp, ttl_seconds=0.01) is False
    time.sleep(0.05)
    # After TTL, eviction should happen on next call; new alert should not be a duplicate
    fp2 = fingerprint_alert({"name": "ExpiryTest2"})
    check_and_record(fp2, ttl_seconds=0.01)  # triggers eviction
    # fp is now gone from the cache; re-recording it should succeed
    assert check_and_record(fp, ttl_seconds=0.01) is False


def test_dedup_stats_returns_count() -> None:
    clear_dedup_cache()
    check_and_record("aaa", ttl_seconds=60)
    check_and_record("bbb", ttl_seconds=60)
    stats = dedup_stats()
    assert stats["active_fingerprints"] == 2


def test_clear_dedup_cache_returns_count() -> None:
    check_and_record("fp1", ttl_seconds=60)
    check_and_record("fp2", ttl_seconds=60)
    n = clear_dedup_cache()
    assert n >= 2
    assert dedup_stats()["active_fingerprints"] == 0
