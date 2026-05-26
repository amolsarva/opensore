"""Alert fingerprint engine — deduplicate similar alerts before investigation.

``fingerprint_alert(raw_alert)`` produces a deterministic SHA-256 hex string
from the alert's key fields. The in-memory TTL cache (``_SEEN``) prevents
duplicate investigations from firing within a configurable window.

Designed for use in the inbound webhook router:

    from app.pipeline.fingerprint import check_and_record, fingerprint_alert

    fp = fingerprint_alert(raw_alert)
    dup = check_and_record(fp, ttl_seconds=300)
    if dup:
        return early  # skip duplicate investigation
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory dedup cache (process-local; survives for the process lifetime)
# ---------------------------------------------------------------------------

_SEEN: dict[str, float] = {}  # fingerprint -> epoch when first seen
_LOCK = threading.Lock()

DEFAULT_TTL_SECONDS = 300  # 5-minute dedup window


def _evict_expired(ttl_seconds: float) -> None:
    """Remove fingerprints older than ttl_seconds (call while holding _LOCK)."""
    now = time.monotonic()
    expired = [fp for fp, ts in _SEEN.items() if now - ts > ttl_seconds]
    for fp in expired:
        del _SEEN[fp]


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

_NOISE_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|uuid:[a-f0-9\-]{36}|\b\d{10,}\b")


def _normalize_value(v: Any) -> str:
    """Stringify and strip volatile sub-strings (timestamps, UUIDs, IDs)."""
    s = str(v).lower().strip()
    return _NOISE_RE.sub("", s).strip()


_FINGERPRINT_KEYS = (
    "name",
    "alert_name",
    "title",
    "alertname",
    "service",
    "severity",
    "source",
    "namespace",
    "host",
    "hostname",
    "instance",
    "metric",
    "pipeline_name",
)


def fingerprint_alert(raw_alert: dict[str, Any]) -> str:
    """Return a stable SHA-256 fingerprint for the alert.

    Extracts the most-identifying fields, normalises them, and hashes the
    result. Fields that are volatile (timestamps, incident IDs, trace IDs)
    are deliberately excluded so the same logical alert hashes identically
    even if the metadata changes slightly between deliveries.
    """
    labels: dict[str, Any] = {}
    for key in ("labels", "commonLabels"):
        maybe = raw_alert.get(key)
        if isinstance(maybe, dict):
            labels = maybe
            break

    parts: list[str] = []
    for key in _FINGERPRINT_KEYS:
        val = raw_alert.get(key) or labels.get(key)
        if val:
            parts.append(f"{key}={_normalize_value(val)}")

    # Also fingerprint the first alert's labels for Alertmanager payloads
    alerts = raw_alert.get("alerts")
    if isinstance(alerts, list) and alerts:
        first = alerts[0]
        first_labels = first.get("labels", {})
        for key in ("alertname", "severity", "namespace", "service", "job"):
            val = first_labels.get(key)
            if val:
                parts.append(f"am.{key}={_normalize_value(val)}")

    canonical = json.dumps(sorted(parts), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Dedup gate
# ---------------------------------------------------------------------------


def check_and_record(
    fingerprint: str,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> bool:
    """Return True (is duplicate) if fingerprint was seen within ttl_seconds.

    Side-effect: records the fingerprint if it is new.
    """
    with _LOCK:
        _evict_expired(ttl_seconds)
        if fingerprint in _SEEN:
            age = time.monotonic() - _SEEN[fingerprint]
            logger.info(
                "[fingerprint] duplicate alert suppressed (fp=%s age=%.0fs)", fingerprint[:12], age
            )
            return True
        _SEEN[fingerprint] = time.monotonic()
        return False


def dedup_stats() -> dict[str, Any]:
    """Return current dedup cache statistics."""
    with _LOCK:
        return {
            "active_fingerprints": len(_SEEN),
            "fingerprints": [
                {"fingerprint": fp[:16] + "…", "age_seconds": round(time.monotonic() - ts, 1)}
                for fp, ts in sorted(_SEEN.items(), key=lambda x: x[1], reverse=True)
            ],
        }


def clear_dedup_cache() -> int:
    """Flush the dedup cache. Returns number of entries cleared."""
    with _LOCK:
        count = len(_SEEN)
        _SEEN.clear()
        return count
