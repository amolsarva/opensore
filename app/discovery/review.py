"""Review-grade summaries for local workplace discovery artifacts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from app.strict_config import StrictConfigModel


class ReviewTag(StrEnum):
    """Suggested reviewer tags for discovery evidence rows."""

    RELEVANT = "relevant"
    PRIVILEGE_REVIEW = "privilege_review"
    CONFIDENTIAL = "confidential"
    WITNESS_FOLLOW_UP = "witness_follow_up"
    ESCALATION = "escalation"
    POST_COMPLAINT_ACTION = "post_complaint_action"


class DiscoveryTimelineEvent(StrictConfigModel):
    """One chronology event derived from evidence metadata."""

    timestamp: str
    source: str
    custodian: str = ""
    subject: str = ""
    matched_keyword_set: str
    matched_keyword: str
    context_excerpt: str
    hash: str


class DiscoveryFacetValue(StrictConfigModel):
    """One value inside a review facet."""

    value: str
    count: int


class DiscoveryReviewSummary(StrictConfigModel):
    """Deterministic review package derived from a discovery run."""

    title: str
    matter_type: str
    generated_at: str
    evidence_file: str
    manifest_file: str
    row_count: int
    unique_hash_count: int
    timeline: list[DiscoveryTimelineEvent] = Field(default_factory=list)
    facets: dict[str, list[DiscoveryFacetValue]] = Field(default_factory=dict)
    suggested_tags: dict[str, list[ReviewTag]] = Field(default_factory=dict)
    open_questions: list[str] = Field(default_factory=list)
    report_markdown: str = ""


_FACET_FIELDS = (
    "source",
    "custodian",
    "matched_keyword_set",
    "matched_keyword",
    "sender",
    "recipients",
    "channel",
    "file_type",
    "source_record_type",
)

_PRIVILEGE_TERMS = ("attorney", "counsel", "legal", "privileged", "work product")
_CONFIDENTIAL_TERMS = ("confidential", "private matter", "do not forward", "nda")
_ESCALATION_TERMS = ("hr", "human resources", "legal", "reported", "escalate", "complaint")
_WITNESS_TERMS = ("witness", "saw", "heard", "interview", "statement")
_POST_COMPLAINT_TERMS = ("retaliation", "demotion", "terminated", "discipline", "reassigned")


def build_review_summary(manifest_path: Path, *, max_timeline: int = 50) -> DiscoveryReviewSummary:
    """Build a deterministic review package from a discovery run manifest."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence_file = Path(str(manifest["evidence_file"]))
    rows = _read_evidence_rows(evidence_file)
    unique_hash_count = len({row.get("hash", "") for row in rows if row.get("hash")})

    summary = DiscoveryReviewSummary(
        title=str(manifest.get("title", "")),
        matter_type=str(manifest.get("matter_type", "")),
        generated_at=_utc_now(),
        evidence_file=str(evidence_file),
        manifest_file=str(manifest_path),
        row_count=len(rows),
        unique_hash_count=unique_hash_count,
        timeline=_timeline(rows, max_timeline=max_timeline),
        facets=_facets(rows),
        suggested_tags=_suggested_tags(rows),
        open_questions=_open_questions(rows),
    )
    summary.report_markdown = _report(summary)
    return summary


def write_review_artifacts(
    manifest_path: Path,
    *,
    json_output: Path | None = None,
    report_output: Path | None = None,
) -> DiscoveryReviewSummary:
    """Build a review package and optionally write JSON and Markdown artifacts."""

    summary = build_review_summary(manifest_path)
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            f"{json.dumps(summary.model_dump(mode='json'), indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )
    if report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(summary.report_markdown, encoding="utf-8")
    return summary


def _read_evidence_rows(evidence_file: Path) -> list[dict[str, str]]:
    if not evidence_file.exists():
        return []
    with evidence_file.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _timeline(rows: list[dict[str, str]], *, max_timeline: int) -> list[DiscoveryTimelineEvent]:
    dated_rows = [row for row in rows if _parse_datetime(row.get("timestamp")) is not None]
    dated_rows.sort(
        key=lambda row: (
            _parse_datetime(row.get("timestamp")) or datetime.max.replace(tzinfo=UTC),
            row.get("source", ""),
            row.get("hash", ""),
        )
    )
    return [
        DiscoveryTimelineEvent(
            timestamp=row.get("timestamp", ""),
            source=row.get("source", ""),
            custodian=row.get("custodian", ""),
            subject=row.get("subject", ""),
            matched_keyword_set=row.get("matched_keyword_set", ""),
            matched_keyword=row.get("matched_keyword", ""),
            context_excerpt=row.get("context_excerpt", ""),
            hash=row.get("hash", ""),
        )
        for row in dated_rows[:max_timeline]
    ]


def _facets(rows: list[dict[str, str]]) -> dict[str, list[DiscoveryFacetValue]]:
    facets: dict[str, list[DiscoveryFacetValue]] = {}
    for field in _FACET_FIELDS:
        counts: Counter[str] = Counter(
            value for row in rows if (value := str(row.get(field, "")).strip())
        )
        facets[field] = [
            DiscoveryFacetValue(value=value, count=count)
            for value, count in counts.most_common(12)
        ]
    return facets


def _suggested_tags(rows: list[dict[str, str]]) -> dict[str, list[ReviewTag]]:
    tags_by_hash: dict[str, list[ReviewTag]] = {}
    for row in rows:
        row_hash = row.get("hash", "")
        if not row_hash:
            continue
        text = " ".join(
            [
                row.get("matched_keyword_set", ""),
                row.get("matched_keyword", ""),
                row.get("context_excerpt", ""),
                row.get("subject", ""),
            ]
        ).lower()
        tags = [ReviewTag.RELEVANT]
        if _contains_any(text, _PRIVILEGE_TERMS):
            tags.append(ReviewTag.PRIVILEGE_REVIEW)
        if _contains_any(text, _CONFIDENTIAL_TERMS):
            tags.append(ReviewTag.CONFIDENTIAL)
        if _contains_any(text, _ESCALATION_TERMS):
            tags.append(ReviewTag.ESCALATION)
        if _contains_any(text, _WITNESS_TERMS):
            tags.append(ReviewTag.WITNESS_FOLLOW_UP)
        if _contains_any(text, _POST_COMPLAINT_TERMS):
            tags.append(ReviewTag.POST_COMPLAINT_ACTION)
        tags_by_hash[row_hash] = _dedupe_tags(tags)
    return tags_by_hash


def _open_questions(rows: list[dict[str, str]]) -> list[str]:
    questions: list[str] = []
    if not rows:
        return ["No evidence rows were matched. Review the date range, custodians, and terms."]
    if any("complaint" in row.get("matched_keyword", "").lower() for row in rows):
        questions.append("Which HR, legal, or management recipients received complaint-related records?")
    if any("retaliation" in row.get("matched_keyword", "").lower() for row in rows):
        questions.append("What materially changed for the complainant after the complaint date?")
    if any("confidential" in row.get("context_excerpt", "").lower() for row in rows):
        questions.append("Which confidentiality or privilege restrictions apply before broader review?")
    if not any(row.get("custodian") for row in rows):
        questions.append("Should the search be rerun with named custodians or source-specific IDs?")
    return questions


def _report(summary: DiscoveryReviewSummary) -> str:
    lines = [
        f"# OpenSore Discovery Review: {summary.title}",
        "",
        "This draft organizes discovery hits for review. It does not make legal, HR, or factual determinations.",
        "",
        "## Run Summary",
        "",
        f"- Matter type: {summary.matter_type}",
        f"- Evidence rows: {summary.row_count}",
        f"- Unique records: {summary.unique_hash_count}",
        f"- Evidence file: `{summary.evidence_file}`",
        "",
        "## Top Facets",
        "",
    ]
    for facet in ("source", "custodian", "matched_keyword_set", "matched_keyword"):
        values = summary.facets.get(facet, [])[:8]
        if not values:
            continue
        rendered = ", ".join(f"{item.value} ({item.count})" for item in values)
        lines.append(f"- {facet}: {rendered}")

    lines.extend(["", "## Chronology", ""])
    if summary.timeline:
        for event in summary.timeline[:20]:
            citation = event.hash[:10] if event.hash else "no-hash"
            subject = f" — {event.subject}" if event.subject else ""
            lines.append(
                f"- {event.timestamp}: {event.source}{subject}; matched "
                f"`{event.matched_keyword}` in {event.matched_keyword_set}. "
                f"[row:{citation}] {event.context_excerpt}"
            )
    else:
        lines.append("- No timestamped evidence rows were available for chronology.")

    lines.extend(["", "## Open Questions", ""])
    for question in summary.open_questions:
        lines.append(f"- {question}")

    lines.extend(
        [
            "",
            "## Review Notes",
            "",
            "- Confirm privilege and confidentiality treatment before wider distribution.",
            "- Validate source exports against the approved search plan.",
            "- Interview and legal conclusions should be drafted by authorized reviewers.",
            "",
        ]
    )
    return "\n".join(lines)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _dedupe_tags(tags: list[ReviewTag]) -> list[ReviewTag]:
    deduped: list[ReviewTag] = []
    seen: set[ReviewTag] = set()
    for tag in tags:
        if tag not in seen:
            deduped.append(tag)
            seen.add(tag)
    return deduped


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


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
