from __future__ import annotations

import json
from pathlib import Path

from app.discovery.review import ReviewTag, build_review_summary, write_review_artifacts


def _write_run_artifacts(tmp_path: Path) -> Path:
    evidence = tmp_path / "discovery_evidence.csv"
    evidence.write_text(
        "\n".join(
            [
                (
                    "matter_title,source,custodian,message_id,timestamp,sender,recipients,"
                    "matched_keyword_set,matched_keyword,context_excerpt,source_url,hash,"
                    "thread_id,channel,file_name,file_type,subject,participants,"
                    "source_record_type,family_id,attachment_names,ingested_at"
                ),
                (
                    "Executive complaint review,slack,alex@example.com,m1,"
                    "2026-01-12T10:00:00+00:00,alex@example.com,hr@example.com,"
                    "retaliation,complaint,Complaint sent to HR and legal counsel,"
                    "https://slack/m1,hash-one,t1,#people,,,,message,t1,,"
                    "2026-01-12T10:01:00Z"
                ),
                (
                    "Executive complaint review,gmail,hr@example.com,email-1,"
                    "2026-01-13T09:00:00+00:00,hr@example.com,counsel@example.com,"
                    "confidentiality,confidential,Confidential legal review needed,"
                    "https://mail/email-1,hash-two,,,#file,pdf,Legal follow-up,,email,,,"
                    "2026-01-13T09:01:00Z"
                ),
            ]
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "discovery_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "title": "Executive complaint review",
                "matter_type": "workplace_misconduct",
                "evidence_file": str(evidence),
                "manifest_file": str(manifest),
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_build_review_summary_generates_timeline_facets_tags_and_report(tmp_path: Path) -> None:
    manifest = _write_run_artifacts(tmp_path)

    summary = build_review_summary(manifest)

    assert summary.row_count == 2
    assert summary.unique_hash_count == 2
    assert [event.hash for event in summary.timeline] == ["hash-one", "hash-two"]
    assert summary.facets["source"][0].value == "slack"
    assert ReviewTag.ESCALATION in summary.suggested_tags["hash-one"]
    assert ReviewTag.PRIVILEGE_REVIEW in summary.suggested_tags["hash-two"]
    assert "does not make legal, HR, or factual determinations" in summary.report_markdown
    assert "[row:hash-one]" in summary.report_markdown


def test_write_review_artifacts_writes_json_and_markdown(tmp_path: Path) -> None:
    manifest = _write_run_artifacts(tmp_path)
    json_output = tmp_path / "review.json"
    report_output = tmp_path / "report.md"

    write_review_artifacts(
        manifest,
        json_output=json_output,
        report_output=report_output,
    )

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["title"] == "Executive complaint review"
    assert report_output.read_text(encoding="utf-8").startswith(
        "# OpenSore Discovery Review"
    )
