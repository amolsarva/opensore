"""CustomCsvConnector — wraps the local file runner for the connector protocol."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from app.discovery.connectors.base import DiscoveryEstimate, DiscoverySearchHit
from app.discovery.models import (
    DiscoveryExportTarget,
    DiscoveryInvestigationRequest,
    DiscoverySource,
    DiscoverySourceKind,
)
from app.discovery.runner import run_local_discovery


class CustomCsvConnector:
    """Discovery connector backed by a local CSV or JSON export file."""

    def __init__(self, source_path: Path) -> None:
        self._path = source_path

    @property
    def source_id(self) -> str:
        return f"csv_{self._path.stem}"

    @property
    def kind(self) -> str:
        return "custom_csv"

    @property
    def label(self) -> str:
        return self._path.name

    def verify(self) -> bool:
        """Return True if the source file exists."""
        return self._path.exists()

    def estimate(self, request: DiscoveryInvestigationRequest) -> DiscoveryEstimate:  # noqa: ARG002
        """Return a single-query estimate (local runner scans all terms in one pass)."""
        return DiscoveryEstimate(
            source_kind=self.kind,
            label=self.label,
            query_count=1,
            estimated_rows=None,
        )

    def search(self, request: DiscoveryInvestigationRequest) -> Iterator[DiscoverySearchHit]:
        """Run local keyword discovery and yield hits as DiscoverySearchHit objects."""
        import tempfile

        patched_request = DiscoveryInvestigationRequest(
            title=request.title,
            matter_type=request.matter_type,
            date_start=request.date_start,
            date_end=request.date_end,
            timezone=request.timezone,
            custodians=[c.model_dump() for c in request.custodians],
            sources=[
                DiscoverySource(kind=DiscoverySourceKind.CUSTOM_CSV, label=self.label)
            ],
            keyword_sets=[ks.model_dump() for ks in request.keyword_sets],
            export_target=DiscoveryExportTarget.LOCAL_CSV,
            store_evidence_locally=False,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest = run_local_discovery(
                request=patched_request,
                source_paths=[self._path],
                output_dir=Path(tmp_dir),
            )
            import csv as _csv

            evidence_path = Path(manifest.evidence_file)
            if not evidence_path.exists():
                return

            with evidence_path.open("r", encoding="utf-8", newline="") as handle:
                reader = _csv.DictReader(handle)
                for row in reader:
                    yield DiscoverySearchHit(
                        source_kind=self.kind,
                        source_label=self.label,
                        message_id=row.get("message_id", ""),
                        timestamp=row.get("timestamp", ""),
                        sender=row.get("sender", ""),
                        recipients=row.get("recipients", ""),
                        subject=row.get("subject", ""),
                        excerpt=row.get("context_excerpt", ""),
                        source_url=row.get("source_url", ""),
                        custodian=row.get("custodian", ""),
                        matched_keyword=row.get("matched_keyword", ""),
                        matched_keyword_set=row.get("matched_keyword_set", ""),
                        thread_id=row.get("thread_id", ""),
                        channel=row.get("channel", ""),
                        file_name=row.get("file_name", ""),
                        attachment_names=row.get("attachment_names", ""),
                    )
