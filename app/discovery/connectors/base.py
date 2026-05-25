"""Protocol and data types shared by all discovery source connectors."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.discovery.models import DiscoveryInvestigationRequest


@dataclass(frozen=True)
class DiscoverySearchHit:
    """One matched item returned from a live source connector search."""

    source_kind: str
    source_label: str
    message_id: str
    timestamp: str
    sender: str
    recipients: str
    subject: str
    excerpt: str
    source_url: str
    custodian: str
    matched_keyword: str
    matched_keyword_set: str
    thread_id: str = ""
    channel: str = ""
    file_name: str = ""
    attachment_names: str = ""


@dataclass
class DiscoveryEstimate:
    """Lightweight pre-search cost estimate for a connector and request."""

    source_kind: str
    label: str
    query_count: int
    estimated_rows: int | None = field(default=None)


@runtime_checkable
class DiscoverySourceConnector(Protocol):
    """Structural protocol implemented by every workspace source connector."""

    @property
    def source_id(self) -> str:
        """Stable unique ID for this credential record."""
        ...

    @property
    def kind(self) -> str:
        """Source kind string (e.g. ``"google_workspace"``, ``"slack"``)."""
        ...

    @property
    def label(self) -> str:
        """Human-readable label shown in CLI output."""
        ...

    def verify(self) -> bool:
        """Return True if the stored credentials are still valid."""
        ...

    def estimate(self, request: DiscoveryInvestigationRequest) -> DiscoveryEstimate:
        """Return a lightweight query-count estimate without fetching evidence."""
        ...

    def search(self, request: DiscoveryInvestigationRequest) -> Iterator[DiscoverySearchHit]:
        """Yield search hits matching the request keyword sets and date range."""
        ...
