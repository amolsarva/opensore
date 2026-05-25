"""Typed contracts for workplace discovery investigations.

These models define a hosted investigation setup that avoids storing user
evidence on the OpenSore host. Source systems are queried with user-scoped
credentials and evidence exports are written to the user's own destination.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.strict_config import StrictConfigModel


class DiscoverySourceKind(StrEnum):
    """External systems that can be searched during discovery."""

    GOOGLE_WORKSPACE = "google_workspace"
    SLACK = "slack"
    MICROSOFT_365 = "microsoft_365"
    GITHUB = "github"
    JIRA = "jira"
    ZENDESK = "zendesk"
    CUSTOM_CSV = "custom_csv"


class DiscoveryExportTarget(StrEnum):
    """Where discovery artifacts should be written."""

    GOOGLE_DRIVE_CSV = "google_drive_csv"
    LOCAL_CSV = "local_csv"


class DiscoveryRunStatus(StrEnum):
    """Lifecycle state for a discovery search run."""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscoveryCustodian(StrictConfigModel):
    """A person or account whose records are in scope."""

    display_name: str = ""
    email: str = ""
    aliases: list[str] = Field(default_factory=list)
    department: str = ""
    role: str = ""
    source_ids: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            value = re.sub(r"\s+", " ", data.strip())
            if "@" in value:
                return {"email": value}
            return {"display_name": value}
        return data

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: object) -> str:
        return str(value or "").strip().lower()

    @field_validator("aliases", mode="before")
    @classmethod
    def _normalize_aliases(cls, value: object) -> list[str]:
        if isinstance(value, str):
            raw_items = value.splitlines()
        elif isinstance(value, list | tuple | set):
            raw_items = list(value)
        else:
            raw_items = []

        aliases: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            alias = re.sub(r"\s+", " ", str(item or "").strip())
            if not alias:
                continue
            key = alias.lower()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(alias)
        return aliases

    @model_validator(mode="after")
    def _require_identity(self) -> DiscoveryCustodian:
        if not self.display_name and not self.email and not self.aliases and not self.source_ids:
            raise ValueError("custodian requires a name, email, alias, or source id")
        return self

    @property
    def primary_label(self) -> str:
        """Return the most useful display label for exports."""

        return self.email or self.display_name or next(iter(self.aliases), "")

    def search_terms(self) -> list[str]:
        """Return identity strings used to associate source records to this custodian."""

        terms = [self.email, self.display_name, *self.aliases, *self.source_ids.values()]
        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            normalized = str(term or "").strip()
            key = normalized.lower()
            if normalized and key not in seen:
                seen.add(key)
                deduped.append(normalized)
        return deduped


class DiscoveryDateRange(StrictConfigModel):
    """Date scope for a discovery request."""

    start: str | None = None
    end: str | None = None
    timezone: str = "UTC"

    @model_validator(mode="after")
    def _validate_order(self) -> DiscoveryDateRange:
        start_dt = _parse_date(self.start)
        end_dt = _parse_date(self.end)
        if start_dt and end_dt and start_dt > end_dt:
            raise ValueError("date range start cannot be after end")
        return self


class DiscoveryKeywordSet(StrictConfigModel):
    """A named keyword group for search planning."""

    name: str
    terms: list[str] = Field(default_factory=list)
    category: str = "custom"
    description: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> str:
        normalized = re.sub(r"\s+", " ", str(value or "").strip())
        if not normalized:
            raise ValueError("keyword set name cannot be empty")
        return normalized

    @field_validator("terms", mode="before")
    @classmethod
    def _normalize_terms(cls, value: object) -> list[str]:
        if isinstance(value, str):
            raw_terms = value.splitlines()
        elif isinstance(value, list | tuple | set):
            raw_terms = list(value)
        else:
            raw_terms = []

        terms: list[str] = []
        seen: set[str] = set()
        for item in raw_terms:
            term = re.sub(r"\s+", " ", str(item or "").strip())
            if not term:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(term)
        return terms

    @model_validator(mode="after")
    def _require_terms(self) -> DiscoveryKeywordSet:
        if not self.terms:
            raise ValueError("keyword set requires at least one term")
        return self


class DiscoverySource(StrictConfigModel):
    """A user-authorized source to search."""

    kind: DiscoverySourceKind
    label: str
    scopes: list[str] = Field(default_factory=list)

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value: object) -> str:
        normalized = re.sub(r"\s+", " ", str(value or "").strip())
        if not normalized:
            raise ValueError("source label cannot be empty")
        return normalized


class DiscoveryInvestigationRequest(StrictConfigModel):
    """Hosted workplace discovery investigation setup request."""

    title: str
    matter_type: str = "workplace_misconduct"
    date_start: str | None = None
    date_end: str | None = None
    timezone: str = "UTC"
    custodians: list[DiscoveryCustodian] = Field(default_factory=list)
    sources: list[DiscoverySource] = Field(default_factory=list)
    keyword_sets: list[DiscoveryKeywordSet] = Field(default_factory=list)
    export_target: DiscoveryExportTarget = DiscoveryExportTarget.GOOGLE_DRIVE_CSV
    store_evidence_locally: bool = False

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title(cls, value: object) -> str:
        normalized = re.sub(r"\s+", " ", str(value or "").strip())
        if not normalized:
            raise ValueError("title cannot be empty")
        return normalized

    @field_validator("custodians", mode="before")
    @classmethod
    def _normalize_custodians(cls, value: object) -> list[str]:
        if isinstance(value, str):
            raw_items = value.splitlines()
        elif isinstance(value, list | tuple | set):
            raw_items = list(value)
        else:
            raw_items = []
        return [item for item in raw_items if str(item).strip() or isinstance(item, dict)]

    @model_validator(mode="after")
    def _enforce_non_retention(self) -> DiscoveryInvestigationRequest:
        if self.store_evidence_locally:
            raise ValueError("hosted discovery mode cannot store user evidence locally")
        if not self.sources:
            raise ValueError("at least one source is required")
        if not self.keyword_sets:
            raise ValueError("at least one keyword set is required")
        return self


class DiscoveryInvestigationPlan(StrictConfigModel):
    """Non-evidence plan returned before a discovery run starts."""

    title: str
    matter_type: str
    source_count: int
    custodian_count: int
    keyword_count: int
    export_target: DiscoveryExportTarget
    csv_columns: list[str]
    retention_mode: str
    next_steps: list[str]
    queries: list[DiscoveryQuery] = Field(default_factory=list)


class DiscoveryQuery(StrictConfigModel):
    """One executable query unit for a source, custodian, and keyword set."""

    source: str
    source_kind: DiscoverySourceKind
    keyword_set: str
    terms: list[str]
    custodian: str = ""
    date_start: str | None = None
    date_end: str | None = None
    timezone: str = "UTC"
    query_text: str


class DiscoveryEvidenceRow(StrictConfigModel):
    """One transient evidence row destined for CSV export."""

    matter_title: str
    source: str
    custodian: str = ""
    message_id: str = ""
    timestamp: str = ""
    sender: str = ""
    recipients: str = ""
    matched_keyword_set: str = ""
    matched_keyword: str = ""
    context_excerpt: str = ""
    source_url: str = ""
    hash: str = ""
    thread_id: str = ""
    channel: str = ""
    file_name: str = ""
    file_type: str = ""
    subject: str = ""
    participants: str = ""
    source_record_type: str = ""
    family_id: str = ""
    attachment_names: str = ""
    ingested_at: str = ""

    def as_csv_row(self) -> dict[str, str]:
        """Return the row in stable CSV column order."""

        data = self.model_dump()
        return {column: str(data.get(column) or "") for column in CSV_COLUMNS}


CSV_COLUMNS = [
    "matter_title",
    "source",
    "custodian",
    "message_id",
    "timestamp",
    "sender",
    "recipients",
    "matched_keyword_set",
    "matched_keyword",
    "context_excerpt",
    "source_url",
    "hash",
    "thread_id",
    "channel",
    "file_name",
    "file_type",
    "subject",
    "participants",
    "source_record_type",
    "family_id",
    "attachment_names",
    "ingested_at",
]


class DiscoveryHitReportRow(StrictConfigModel):
    """Aggregate hit count for review and query tuning."""

    source: str
    custodian: str = ""
    matched_keyword_set: str
    matched_keyword: str
    hit_count: int


class DiscoveryRunManifest(StrictConfigModel):
    """Durable metadata for a local discovery run."""

    title: str
    matter_type: str
    status: DiscoveryRunStatus
    started_at: str
    completed_at: str
    source_files: list[str]
    evidence_file: str
    hit_report_file: str
    manifest_file: str
    row_count: int
    unique_hash_count: int
    query_count: int
    retention_mode: str


def default_keyword_sets() -> list[DiscoveryKeywordSet]:
    """Return seed keyword groups for workplace misconduct discovery.

    These are starting points for counsel or an investigator to edit. They are
    intentionally broad and should not be treated as legal advice.
    """

    return [
        DiscoveryKeywordSet(
            name="workplace harassment",
            category="harassment",
            description="Broad workplace harassment and hostile-environment language.",
            terms=[
                "harass",
                "hostile work environment",
                "retaliation",
                "complaint",
                "uncomfortable",
                "inappropriate",
            ],
        ),
        DiscoveryKeywordSet(
            name="sexual misconduct",
            category="sexual_misconduct",
            description="Sexual misconduct, unwanted conduct, and consent-related language.",
            terms=[
                "sexual",
                "unwanted",
                "touch",
                "quid pro quo",
                "advances",
                "consent",
            ],
        ),
        DiscoveryKeywordSet(
            name="executive misconduct",
            category="executive_misconduct",
            description="Executive escalation, concealment, board, and settlement language.",
            terms=[
                "executive",
                "board",
                "off the record",
                "settlement",
                "NDA",
                "do not forward",
            ],
        ),
        DiscoveryKeywordSet(
            name="HR and legal escalation",
            category="hr_legal_escalation",
            description="Signals that complaints, HR, legal, or management were notified.",
            terms=[
                "HR",
                "human resources",
                "legal",
                "counsel",
                "reported",
                "escalate",
                "investigation",
            ],
        ),
        DiscoveryKeywordSet(
            name="cover-up and confidentiality",
            category="cover_up",
            description="Language indicating concealment, secrecy, or restricted sharing.",
            terms=[
                "keep this quiet",
                "delete this",
                "off channel",
                "private matter",
                "confidential",
                "do not put in writing",
            ],
        ),
        DiscoveryKeywordSet(
            name="conflicts and financial impropriety",
            category="conflicts_financial",
            description="Conflict of interest, gifts, approvals, and improper benefit language.",
            terms=[
                "conflict of interest",
                "kickback",
                "gift",
                "side deal",
                "expense",
                "approval",
                "vendor",
            ],
        ),
    ]


def build_discovery_plan(request: DiscoveryInvestigationRequest) -> DiscoveryInvestigationPlan:
    """Build a no-evidence execution plan for the web/API setup flow."""

    keyword_count = sum(len(group.terms) for group in request.keyword_sets)
    queries = build_discovery_queries(request)
    return DiscoveryInvestigationPlan(
        title=request.title,
        matter_type=request.matter_type,
        source_count=len(request.sources),
        custodian_count=len(request.custodians),
        keyword_count=keyword_count,
        export_target=request.export_target,
        csv_columns=list(CSV_COLUMNS),
        retention_mode="no local evidence storage; write CSV artifacts to user-owned Google Drive",
        next_steps=[
            "Authenticate each source with read-only scopes.",
            "Run keyword discovery against selected custodians and date range.",
            "Write CSV exports directly to the user's Google Drive.",
            "Delete transient buffers after export completes.",
        ],
        queries=queries,
    )


def build_discovery_queries(request: DiscoveryInvestigationRequest) -> list[DiscoveryQuery]:
    """Build executable query units without retrieving evidence."""

    custodians = request.custodians or [DiscoveryCustodian(display_name="")]
    queries: list[DiscoveryQuery] = []
    for source in request.sources:
        for keyword_set in request.keyword_sets:
            for custodian in custodians:
                custodian_label = custodian.primary_label
                terms = list(keyword_set.terms)
                query_text = _query_text(
                    terms=terms,
                    custodian_terms=custodian.search_terms(),
                    date_start=request.date_start,
                    date_end=request.date_end,
                )
                queries.append(
                    DiscoveryQuery(
                        source=source.label,
                        source_kind=source.kind,
                        keyword_set=keyword_set.name,
                        terms=terms,
                        custodian=custodian_label,
                        date_start=request.date_start,
                        date_end=request.date_end,
                        timezone=request.timezone,
                        query_text=query_text,
                    )
                )
    return queries


def _query_text(
    *,
    terms: list[str],
    custodian_terms: list[str],
    date_start: str | None,
    date_end: str | None,
) -> str:
    keyword_clause = " OR ".join(_quote_query_value(term) for term in terms)
    parts = [f"({keyword_clause})" if keyword_clause else ""]
    if custodian_terms:
        custodian_clause = " OR ".join(_quote_query_value(term) for term in custodian_terms)
        parts.append(f"custodian:({custodian_clause})")
    if date_start:
        parts.append(f"date>={date_start}")
    if date_end:
        parts.append(f"date<={date_end}")
    return " AND ".join(part for part in parts if part)


def _quote_query_value(value: str) -> str:
    escaped = value.replace('"', '\\"')
    if re.search(r"\s", escaped):
        return f'"{escaped}"'
    return escaped


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid date value: {value}") from exc


def discovery_plan_csv(plan: DiscoveryInvestigationPlan) -> str:
    """Render a plan summary as CSV without evidence rows."""

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "title",
            "matter_type",
            "source_count",
            "custodian_count",
            "keyword_count",
            "export_target",
            "retention_mode",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "title": plan.title,
            "matter_type": plan.matter_type,
            "source_count": plan.source_count,
            "custodian_count": plan.custodian_count,
            "keyword_count": plan.keyword_count,
            "export_target": plan.export_target.value,
            "retention_mode": plan.retention_mode,
        }
    )
    return output.getvalue()


def discovery_evidence_csv(rows: list[DiscoveryEvidenceRow]) -> str:
    """Render transient evidence rows as CSV."""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row.as_csv_row())
    return output.getvalue()
