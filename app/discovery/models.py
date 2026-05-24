"""Typed contracts for workplace discovery investigations.

These models define a hosted investigation setup that avoids storing user
evidence on the OpenSRE host. Source systems are queried with user-scoped
credentials and evidence exports are written to the user's own destination.
"""

from __future__ import annotations

import csv
import io
import re
from enum import StrEnum

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


class DiscoveryKeywordSet(StrictConfigModel):
    """A named keyword group for search planning."""

    name: str
    terms: list[str] = Field(default_factory=list)

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
    custodians: list[str] = Field(default_factory=list)
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
        return [str(item).strip() for item in raw_items if str(item).strip()]

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
]


def default_keyword_sets() -> list[DiscoveryKeywordSet]:
    """Return seed keyword groups for workplace misconduct discovery.

    These are starting points for counsel or an investigator to edit. They are
    intentionally broad and should not be treated as legal advice.
    """

    return [
        DiscoveryKeywordSet(
            name="workplace harassment",
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
            terms=[
                "executive",
                "board",
                "off the record",
                "settlement",
                "NDA",
                "do not forward",
            ],
        ),
    ]


def build_discovery_plan(request: DiscoveryInvestigationRequest) -> DiscoveryInvestigationPlan:
    """Build a no-evidence execution plan for the web/API setup flow."""

    keyword_count = sum(len(group.terms) for group in request.keyword_sets)
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
    )


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
