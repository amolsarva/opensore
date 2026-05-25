"""Discovery source connectors — OAuth workspace integrations and local file sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.discovery.connectors.base import (
    DiscoveryEstimate,
    DiscoverySearchHit,
    DiscoverySourceConnector,
)
from app.discovery.connectors.custom_csv import CustomCsvConnector
from app.discovery.connectors.google_workspace import (
    GoogleWorkspaceConnector,
    run_google_oauth,
)
from app.discovery.connectors.slack import SlackConnector, run_slack_oauth

__all__ = [
    "CustomCsvConnector",
    "DiscoveryEstimate",
    "DiscoverySearchHit",
    "DiscoverySourceConnector",
    "GoogleWorkspaceConnector",
    "SlackConnector",
    "get_connector",
    "run_google_oauth",
    "run_slack_oauth",
]


def get_connector(record: dict[str, Any]) -> DiscoverySourceConnector | None:
    """Dispatch a stored source record to the matching connector implementation.

    Returns ``None`` when the ``kind`` field does not map to a known connector.
    """
    kind = record.get("kind", "")
    if kind == "google_workspace":
        return GoogleWorkspaceConnector(record)
    if kind == "slack":
        return SlackConnector(record)
    if kind == "custom_csv":
        source_path_str = record.get("source_path", "")
        if source_path_str:
            return CustomCsvConnector(Path(source_path_str))
        return None
    return None
