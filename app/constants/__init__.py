"""Application-wide constants: prompts, limits, identifiers, and filesystem paths."""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path

from app.constants.investigation import MAX_EXPANSIONS, MAX_INVESTIGATION_LOOPS
from app.constants.opensore import DEFAULT_RELEASE_VERSION
from app.constants.posthog import (
    DEFAULT_POSTHOG_BOUNCE_THRESHOLD,
    DEFAULT_POSTHOG_BOUNCE_WINDOW,
    DEFAULT_POSTHOG_TIMEOUT_SECONDS,
    DEFAULT_POSTHOG_URL,
    POSTHOG_CAPTURE_API_KEY,
    POSTHOG_HOST,
)
from app.constants.sentry import (
    SENTRY_DSN,
    SENTRY_ERROR_SAMPLE_RATE,
    SENTRY_IN_APP_INCLUDE,
    SENTRY_MAX_BREADCRUMBS,
    SENTRY_TRACES_SAMPLE_RATE,
)

OPENSORE_HOME_DIR: Path = Path.home() / ".config" / "opensore"
LEGACY_OPENSORE_HOME_DIR: Path = Path.home() / ".opensore"
LEGACY_TRACER_HOME_DIR: Path = Path.home() / ".tracer"
INTEGRATIONS_STORE_PATH: Path = OPENSORE_HOME_DIR / "integrations.json"
LEGACY_INTEGRATIONS_STORE_PATH: Path = LEGACY_TRACER_HOME_DIR / "integrations.json"
OPENSORE_TMP_DIR: Path = Path(tempfile.gettempdir()) / "opensore"


def ensure_opensore_tmp_dir() -> Path:
    """Create the OpenSore temp directory with owner-only permissions when possible."""
    OPENSORE_TMP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        OPENSORE_TMP_DIR.chmod(0o700)
    return OPENSORE_TMP_DIR


__all__ = [
    "DEFAULT_RELEASE_VERSION",
    "MAX_EXPANSIONS",
    "MAX_INVESTIGATION_LOOPS",
    "DEFAULT_POSTHOG_BOUNCE_THRESHOLD",
    "DEFAULT_POSTHOG_BOUNCE_WINDOW",
    "DEFAULT_POSTHOG_TIMEOUT_SECONDS",
    "DEFAULT_POSTHOG_URL",
    "INTEGRATIONS_STORE_PATH",
    "LEGACY_OPENSORE_HOME_DIR",
    "LEGACY_INTEGRATIONS_STORE_PATH",
    "LEGACY_TRACER_HOME_DIR",
    "ensure_opensore_tmp_dir",
    "OPENSORE_HOME_DIR",
    "OPENSORE_TMP_DIR",
    "POSTHOG_CAPTURE_API_KEY",
    "POSTHOG_HOST",
    "SENTRY_DSN",
    "SENTRY_ERROR_SAMPLE_RATE",
    "SENTRY_IN_APP_INCLUDE",
    "SENTRY_MAX_BREADCRUMBS",
    "SENTRY_TRACES_SAMPLE_RATE",
]
