from __future__ import annotations

import csv
import json
from pathlib import Path

from app.discovery.models import DiscoveryInvestigationRequest, build_discovery_plan
from app.discovery.runner import run_local_discovery


def _request() -> DiscoveryInvestigationRequest:
    return DiscoveryInvestigationRequest(
        title="Executive complaint review",
        date_start="2026-01-01T00:00:00+00:00",
        date_end="2026-01-31T23:59:59+00:00",
        timezone="UTC",
        custodians=[
            {
                "display_name": "Alex Manager",
                "email": "alex@example.com",
                "aliases": ["alexm", "Alex M."],
            },
            {"email": "hr@example.com"},
        ],
        sources=[{"kind": "custom_csv", "label": "Slack export"}],
        keyword_sets=[
            {
                "name": "retaliation",
                "category": "retaliation",
                "terms": ["retaliation", "keep this quiet", "complaint"],
            }
        ],
        export_target="local_csv",
    )


def test_run_local_discovery_writes_evidence_hit_report_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "slack.csv"
    source.write_text(
        "\n".join(
            [
                "source,message_id,timestamp,sender,recipients,channel,text,thread_id,url",
                (
                    "slack,m1,2026-01-12T10:00:00+00:00,alex@example.com,"
                    "hr@example.com,#people,"
                    '"Please keep this quiet after the complaint.",t1,https://slack/m1'
                ),
                (
                    "slack,m2,2026-02-12T10:00:00+00:00,alex@example.com,"
                    "hr@example.com,#people,"
                    '"Outside the date range retaliation note.",t2,https://slack/m2'
                ),
                (
                    "slack,m3,2026-01-12T10:00:00+00:00,other@example.com,"
                    "legal@example.com,#people,"
                    '"No custodian match but complaint appears.",t3,https://slack/m3'
                ),
            ]
        ),
        encoding="utf-8",
    )

    manifest = run_local_discovery(
        request=_request(),
        source_paths=[source],
        output_dir=tmp_path / "out",
    )

    assert manifest.row_count == 2
    assert manifest.unique_hash_count == 2
    with Path(manifest.evidence_file).open(encoding="utf-8") as handle:
        evidence_rows = list(csv.DictReader(handle))
    assert {row["matched_keyword"] for row in evidence_rows} == {"keep this quiet", "complaint"}
    assert {row["custodian"] for row in evidence_rows} == {"alex@example.com"}
    assert all(row["hash"] for row in evidence_rows)

    with Path(manifest.hit_report_file).open(encoding="utf-8") as handle:
        hit_rows = list(csv.DictReader(handle))
    assert len(hit_rows) == 2
    assert {row["hit_count"] for row in hit_rows} == {"1"}

    manifest_payload = json.loads(Path(manifest.manifest_file).read_text(encoding="utf-8"))
    assert manifest_payload["row_count"] == 2
    assert manifest_payload["query_count"] == 2
    assert "queries" in manifest_payload


def test_run_local_discovery_reads_json_records(tmp_path: Path) -> None:
    source = tmp_path / "gmail.json"
    source.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "source": "gmail",
                        "id": "email-1",
                        "timestamp": "2026-01-10T09:00:00Z",
                        "from": "hr@example.com",
                        "to": "alex@example.com",
                        "subject": "Complaint follow-up",
                        "body": "The retaliation complaint needs counsel review.",
                        "url": "https://mail/email-1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manifest = run_local_discovery(
        request=_request(),
        source_paths=[source],
        output_dir=tmp_path / "out",
    )

    with Path(manifest.evidence_file).open(encoding="utf-8") as handle:
        evidence_rows = list(csv.DictReader(handle))
    assert manifest.row_count == 2
    assert {row["matched_keyword"] for row in evidence_rows} == {"retaliation", "complaint"}
    assert evidence_rows[0]["source"] == "gmail"


def test_build_discovery_plan_allows_uncustodianed_broad_search() -> None:
    request = DiscoveryInvestigationRequest(
        title="Broad executive matter",
        sources=[{"kind": "custom_csv", "label": "Local export"}],
        keyword_sets=[{"name": "complaints", "terms": ["complaint"]}],
        export_target="local_csv",
    )

    plan = build_discovery_plan(request)

    assert plan.custodian_count == 0
    assert plan.queries[0].custodian == ""
    assert plan.queries[0].query_text == "(complaint)"
