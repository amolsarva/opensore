"""Local workplace discovery runner for exported source data."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.discovery.connectors.base import DiscoverySearchHit

from app.discovery.models import (
    CSV_COLUMNS,
    DiscoveryEvidenceRow,
    DiscoveryHitReportRow,
    DiscoveryInvestigationRequest,
    DiscoveryRunManifest,
    DiscoveryRunStatus,
    build_discovery_queries,
    discovery_evidence_csv,
)
from app.version import get_version

TEXT_FIELDS = (
    "body",
    "text",
    "message",
    "content",
    "description",
    "comment",
    "comments",
    "subject",
    "title",
    "summary",
    "file_name",
    "attachment_names",
)
PARTICIPANT_FIELDS = (
    "custodian",
    "sender",
    "from",
    "author",
    "owner",
    "recipients",
    "to",
    "cc",
    "bcc",
    "participants",
    "assignee",
    "reporter",
)
TIMESTAMP_FIELDS = ("timestamp", "date", "sent_at", "created_at", "updated_at", "modified_at")
ID_FIELDS = ("message_id", "id", "record_id", "event_id", "issue_key", "url")
SOURCE_FIELD = "source"
MAX_EXCERPT_CHARS = 280


def run_local_discovery(
    *,
    request: DiscoveryInvestigationRequest,
    source_paths: list[Path],
    output_dir: Path,
) -> DiscoveryRunManifest:
    """Search local CSV/JSON exports and write review artifacts.

    This runner is intentionally deterministic and source-agnostic. It is the
    bridge between eDiscovery-style export files and future live connectors.
    """

    started_at = _utc_now()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = _load_records(source_paths)
    evidence_rows = list(_matching_rows(request=request, records=records))
    evidence_rows.sort(key=lambda row: (row.timestamp, row.source, row.custodian, row.hash))

    evidence_file = output_dir / "discovery_evidence.csv"
    hit_report_file = output_dir / "discovery_hit_report.csv"
    manifest_file = output_dir / "discovery_manifest.json"

    _write_text(evidence_file, discovery_evidence_csv(evidence_rows))
    _write_hit_report(hit_report_file, _hit_report(evidence_rows))

    completed_at = _utc_now()
    manifest = DiscoveryRunManifest(
        title=request.title,
        matter_type=request.matter_type,
        status=DiscoveryRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        source_files=[str(path) for path in source_paths],
        evidence_file=str(evidence_file),
        hit_report_file=str(hit_report_file),
        manifest_file=str(manifest_file),
        row_count=len(evidence_rows),
        unique_hash_count=len({row.hash for row in evidence_rows}),
        query_count=len(build_discovery_queries(request)),
        retention_mode=(
            "local explicit export mode; evidence written only to requested output directory"
        ),
    )
    _write_json(
        manifest_file,
        {
            **manifest.model_dump(mode="json"),
            "opensore_version": get_version(),
            "csv_columns": CSV_COLUMNS,
            "queries": [
                query.model_dump(mode="json") for query in build_discovery_queries(request)
            ],
        },
    )
    return manifest


def evidence_row_from_hit(
    hit: DiscoverySearchHit,
    *,
    matter_title: str,
) -> DiscoveryEvidenceRow:
    """Convert a live connector hit to a CSV-ready evidence row."""
    hash_val = _hash_row(
        source=hit.source_label,
        message_id=hit.message_id,
        matched_keyword=hit.matched_keyword,
    )
    return DiscoveryEvidenceRow(
        matter_title=matter_title,
        source=hit.source_label,
        custodian=hit.custodian,
        message_id=hit.message_id,
        timestamp=hit.timestamp,
        sender=hit.sender,
        recipients=hit.recipients,
        matched_keyword_set=hit.matched_keyword_set,
        matched_keyword=hit.matched_keyword,
        context_excerpt=hit.excerpt[:MAX_EXCERPT_CHARS],
        source_url=hit.source_url,
        hash=hash_val,
        thread_id=hit.thread_id,
        channel=hit.channel,
        file_name=hit.file_name,
        subject=hit.subject,
        attachment_names=hit.attachment_names,
        ingested_at=_utc_now(),
    )


def run_discovery(
    *,
    request: DiscoveryInvestigationRequest,
    source_paths: list[Path],
    connector_ids: list[str],
    output_dir: Path,
) -> DiscoveryRunManifest:
    """Run discovery over local exports and/or live connector sources.

    Combines file-based rows and live connector rows into a single unified
    output package. Either ``source_paths`` or ``connector_ids`` may be empty
    but at least one must be non-empty.
    """
    from app.discovery.connectors import get_connector
    from app.discovery.credentials import get_source

    started_at = _utc_now()
    output_dir.mkdir(parents=True, exist_ok=True)

    evidence_rows: list[DiscoveryEvidenceRow] = []

    if source_paths:
        records = _load_records(source_paths)
        evidence_rows.extend(_matching_rows(request=request, records=records))

    for cid in connector_ids:
        record = get_source(cid)
        if record is None:
            continue
        connector = get_connector(record)
        if connector is None:
            continue
        for hit in connector.search(request):
            evidence_rows.append(evidence_row_from_hit(hit, matter_title=request.title))

    evidence_rows.sort(key=lambda row: (row.timestamp, row.source, row.custodian, row.hash))

    evidence_file = output_dir / "discovery_evidence.csv"
    hit_report_file = output_dir / "discovery_hit_report.csv"
    manifest_file = output_dir / "discovery_manifest.json"

    _write_text(evidence_file, discovery_evidence_csv(evidence_rows))
    _write_hit_report(hit_report_file, _hit_report(evidence_rows))

    completed_at = _utc_now()
    manifest = DiscoveryRunManifest(
        title=request.title,
        matter_type=request.matter_type,
        status=DiscoveryRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        source_files=[str(p) for p in source_paths],
        evidence_file=str(evidence_file),
        hit_report_file=str(hit_report_file),
        manifest_file=str(manifest_file),
        row_count=len(evidence_rows),
        unique_hash_count=len({row.hash for row in evidence_rows}),
        query_count=len(build_discovery_queries(request)),
        retention_mode=(
            "local explicit export mode; evidence written only to requested output directory"
        ),
    )
    _write_json(
        manifest_file,
        {
            **manifest.model_dump(mode="json"),
            "opensore_version": get_version(),
            "csv_columns": CSV_COLUMNS,
            "queries": [
                query.model_dump(mode="json") for query in build_discovery_queries(request)
            ],
        },
    )
    return manifest


def load_discovery_request(path: Path) -> DiscoveryInvestigationRequest:
    """Load a discovery request from a JSON file."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("discovery config must be a JSON object")
    return DiscoveryInvestigationRequest.model_validate(data)


def _matching_rows(
    *,
    request: DiscoveryInvestigationRequest,
    records: list[dict[str, Any]],
) -> list[DiscoveryEvidenceRow]:
    rows: list[DiscoveryEvidenceRow] = []
    ingested_at = _utc_now()
    for record in records:
        timestamp = _first_value(record, TIMESTAMP_FIELDS)
        if not _timestamp_in_range(timestamp, request.date_start, request.date_end):
            continue
        custodian = _matched_custodian(request, record)
        if request.custodians and custodian is None:
            continue

        searchable_text = _searchable_text(record)
        for keyword_set in request.keyword_sets:
            for term in keyword_set.terms:
                if not _term_matches(term, searchable_text):
                    continue
                rows.append(
                    _evidence_row(
                        request=request,
                        record=record,
                        keyword_set=keyword_set.name,
                        keyword=term,
                        custodian=custodian or _first_value(record, ("custodian", "owner")),
                        searchable_text=searchable_text,
                        ingested_at=ingested_at,
                    )
                )
    return _dedupe_rows(rows)


def _evidence_row(
    *,
    request: DiscoveryInvestigationRequest,
    record: dict[str, Any],
    keyword_set: str,
    keyword: str,
    custodian: str,
    searchable_text: str,
    ingested_at: str,
) -> DiscoveryEvidenceRow:
    source = _first_value(record, (SOURCE_FIELD, "system", "platform")) or "custom_csv"
    message_id = _first_value(record, ID_FIELDS)
    timestamp = _first_value(record, TIMESTAMP_FIELDS)
    source_url = _first_value(record, ("source_url", "url", "web_url", "permalink"))
    row_hash = _hash_row(
        matter_title=request.title,
        source=source,
        message_id=message_id,
        timestamp=timestamp,
        keyword_set=keyword_set,
        keyword=keyword,
        text=searchable_text,
    )
    return DiscoveryEvidenceRow(
        matter_title=request.title,
        source=source,
        custodian=custodian,
        message_id=message_id,
        timestamp=timestamp,
        sender=_first_value(record, ("sender", "from", "author", "owner")),
        recipients=_first_value(record, ("recipients", "to", "cc", "bcc")),
        matched_keyword_set=keyword_set,
        matched_keyword=keyword,
        context_excerpt=_excerpt(searchable_text, keyword),
        source_url=source_url,
        hash=row_hash,
        thread_id=_first_value(record, ("thread_id", "conversation_id", "channel_thread_id")),
        channel=_first_value(record, ("channel", "room", "team", "site")),
        file_name=_first_value(record, ("file_name", "filename", "name")),
        file_type=_first_value(record, ("file_type", "mime_type", "kind")),
        subject=_first_value(record, ("subject", "title")),
        participants=_first_value(record, PARTICIPANT_FIELDS),
        source_record_type=_first_value(
            record, ("source_record_type", "record_type", "type", "kind")
        ),
        family_id=_first_value(record, ("family_id", "thread_id", "conversation_id")),
        attachment_names=_first_value(record, ("attachment_names", "attachments")),
        ingested_at=ingested_at,
    )


def _dedupe_rows(rows: list[DiscoveryEvidenceRow]) -> list[DiscoveryEvidenceRow]:
    deduped: dict[tuple[str, str, str], DiscoveryEvidenceRow] = {}
    for row in rows:
        key = (row.hash, row.matched_keyword_set, row.matched_keyword.lower())
        deduped.setdefault(key, row)
    return list(deduped.values())


def _hit_report(rows: list[DiscoveryEvidenceRow]) -> list[DiscoveryHitReportRow]:
    counts: Counter[tuple[str, str, str, str]] = Counter()
    for row in rows:
        counts[
            (
                row.source,
                row.custodian,
                row.matched_keyword_set,
                row.matched_keyword,
            )
        ] += 1
    return [
        DiscoveryHitReportRow(
            source=source,
            custodian=custodian,
            matched_keyword_set=keyword_set,
            matched_keyword=keyword,
            hit_count=count,
        )
        for (source, custodian, keyword_set, keyword), count in sorted(counts.items())
    ]


def _write_hit_report(path: Path, rows: list[DiscoveryHitReportRow]) -> None:
    fieldnames = ["source", "custodian", "matched_keyword_set", "matched_keyword", "hit_count"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump(mode="json"))


def _load_records(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        if path.suffix.lower() == ".csv":
            records.extend(_load_csv(path))
        elif path.suffix.lower() in {".json", ".jsonl", ".ndjson"}:
            records.extend(_load_json(path))
        else:
            raise ValueError(f"unsupported discovery source file type: {path}")
    return records


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _load_json(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        return [_ensure_record(json.loads(line)) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return [_ensure_record(item) for item in data]
    if isinstance(data, dict):
        for key in ("records", "messages", "items", "events", "rows"):
            value = data.get(key)
            if isinstance(value, list):
                return [_ensure_record(item) for item in value]
        return [_flatten_record(data)]
    raise ValueError(f"unsupported JSON discovery source shape: {path}")


def _ensure_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": value}
    return _flatten_record(value)


def _flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                flattened[f"{key}_{nested_key}"] = _stringify(nested_value)
        else:
            flattened[key] = _stringify(value)
    return flattened


def _searchable_text(record: dict[str, Any]) -> str:
    values = [_first_value(record, TEXT_FIELDS)]
    values.extend(_first_value(record, (field,)) for field in PARTICIPANT_FIELDS)
    return "\n".join(value for value in values if value)


def _matched_custodian(
    request: DiscoveryInvestigationRequest,
    record: dict[str, Any],
) -> str | None:
    participant_text = " ".join(
        _first_value(record, (field,))
        for field in PARTICIPANT_FIELDS
        if _first_value(record, (field,))
    ).lower()
    for custodian in request.custodians:
        for term in custodian.search_terms():
            if term.lower() in participant_text:
                return custodian.primary_label
    return None


def _term_matches(term: str, text: str) -> bool:
    normalized = term.strip()
    if not normalized:
        return False
    if " NEAR/" in normalized.upper():
        return _near_matches(normalized, text)
    return (
        re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", text, flags=re.IGNORECASE) is not None
    )


def _near_matches(term: str, text: str) -> bool:
    match = re.match(r"(.+?)\s+NEAR/(\d+)\s+(.+)", term, flags=re.IGNORECASE)
    if match is None:
        return False
    left, distance_text, right = match.groups()
    distance = int(distance_text)
    words = re.findall(r"\w+", text.lower())
    left_words = {index for index, word in enumerate(words) if word == left.strip().lower()}
    right_words = {index for index, word in enumerate(words) if word == right.strip().lower()}
    return any(
        abs(left_index - right_index) <= distance
        for left_index in left_words
        for right_index in right_words
    )


def _timestamp_in_range(
    timestamp: str,
    start: str | None,
    end: str | None,
) -> bool:
    if not timestamp or (not start and not end):
        return True
    value_dt = _parse_datetime(timestamp)
    if value_dt is None:
        return True
    start_dt = _parse_datetime(start) if start else None
    end_dt = _parse_datetime(end) if end else None
    if start_dt and value_dt < start_dt:
        return False
    return not (end_dt and value_dt > end_dt)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _excerpt(text: str, keyword: str) -> str:
    normalized = " ".join(text.split())
    match = re.search(re.escape(keyword), normalized, flags=re.IGNORECASE)
    if match is None:
        return normalized[:MAX_EXCERPT_CHARS]
    start = max(0, match.start() - MAX_EXCERPT_CHARS // 2)
    end = min(len(normalized), match.end() + MAX_EXCERPT_CHARS // 2)
    return normalized[start:end]


def _first_value(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    lowered = {key.lower(): value for key, value in record.items()}
    for field in fields:
        value = lowered.get(field.lower())
        if value not in (None, ""):
            return _stringify(value)
    return ""


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list | tuple | set):
        return "; ".join(_stringify(item) for item in value if _stringify(item))
    return str(value).strip()


def _hash_row(**parts: str) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
