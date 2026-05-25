from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.discovery.models import (
    DiscoveryCustodian,
    DiscoveryEvidenceRow,
    DiscoveryInvestigationRequest,
    DiscoveryKeywordSet,
    DiscoverySource,
    build_discovery_plan,
    discovery_evidence_csv,
    discovery_plan_csv,
)


def _request() -> DiscoveryInvestigationRequest:
    return DiscoveryInvestigationRequest(
        title="Board complaint review",
        custodians=["ceo@example.com", "hr@example.com"],
        sources=[
            DiscoverySource(
                kind="google_workspace",
                label="Company Google Workspace",
                scopes=["gmail.readonly", "drive.readonly"],
            )
        ],
        keyword_sets=[
            DiscoveryKeywordSet(
                name="harassment",
                terms=["retaliation", "hostile work environment", "retaliation"],
            )
        ],
    )


def test_discovery_request_rejects_local_evidence_storage() -> None:
    with pytest.raises(ValidationError, match="cannot store user evidence locally"):
        DiscoveryInvestigationRequest(
            title="Matter",
            sources=[DiscoverySource(kind="slack", label="Slack")],
            keyword_sets=[DiscoveryKeywordSet(name="terms", terms=["complaint"])],
            store_evidence_locally=True,
        )


def test_keyword_set_deduplicates_terms() -> None:
    group = DiscoveryKeywordSet(name="Terms", terms=[" complaint ", "Complaint", "board"])

    assert group.terms == ["complaint", "board"]


def test_custodian_accepts_structured_identity() -> None:
    custodian = DiscoveryCustodian(
        display_name="Pat Lee",
        email="PAT@example.com",
        aliases=["P. Lee", "p. lee", "plee"],
        source_ids={"slack": "U123"},
    )

    assert custodian.email == "pat@example.com"
    assert custodian.primary_label == "pat@example.com"
    assert custodian.search_terms() == ["pat@example.com", "Pat Lee", "P. Lee", "plee", "U123"]


def test_build_discovery_plan_summarizes_without_evidence() -> None:
    plan = build_discovery_plan(_request())

    assert plan.source_count == 1
    assert plan.custodian_count == 2
    assert plan.keyword_count == 2
    assert "no local evidence storage" in plan.retention_mode
    assert "context_excerpt" in plan.csv_columns
    assert len(plan.queries) == 2
    assert plan.queries[0].custodian == "ceo@example.com"
    assert "retaliation" in plan.queries[0].query_text


def test_discovery_plan_csv_has_summary_row() -> None:
    csv_text = discovery_plan_csv(build_discovery_plan(_request()))

    assert "title,matter_type,source_count" in csv_text
    assert "Board complaint review" in csv_text


def test_discovery_evidence_csv_uses_stable_columns() -> None:
    csv_text = discovery_evidence_csv(
        [
            DiscoveryEvidenceRow(
                matter_title="Matter",
                source="gmail",
                matched_keyword="retaliation",
                context_excerpt="context",
            )
        ]
    )

    assert csv_text.startswith("matter_title,source,custodian,message_id")
    assert "retaliation" in csv_text
