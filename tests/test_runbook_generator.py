"""Unit tests for the auto-runbook generator."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from app.pipeline.runbook import (
    _render_runbook,
    _slugify,
    generate_runbook,
    list_runbooks,
    load_runbook,
)

# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------


def test_slugify_basic() -> None:
    assert _slugify("High Memory Usage") == "high-memory-usage"


def test_slugify_strips_special_chars() -> None:
    assert _slugify("DB/Cache: Miss Rate!") == "db-cache-miss-rate"


def test_slugify_max_length() -> None:
    long_text = "a" * 200
    assert len(_slugify(long_text)) <= 80


# ---------------------------------------------------------------------------
# _render_runbook
# ---------------------------------------------------------------------------


def _sample_render(**overrides: object) -> str:
    kwargs: dict = {
        "alert_name": "HighDBLatency",
        "root_cause": "Connection pool exhausted due to slow queries.",
        "root_cause_category": "database",
        "causal_chain": ["Slow query backlog grew", "Pool hit max connections"],
        "remediation_steps": ["Increase pool size", "Identify and kill slow queries"],
        "validated_claims": [{"claim": "Pool was at 100%", "validation_status": "validated"}],
        "non_validated_claims": [
            {"claim": "Index missing on users table", "validation_status": "not_validated"}
        ],
        "validity_score": 0.85,
        "raw_alert": {"service": "payments-api", "severity": "critical"},
        "evidence_entries": [{"tool": "datadog_metrics", "summary": "DB connections maxed out"}],
        "runbook_id": "abc123def456",
        "generated_at": datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return _render_runbook(**kwargs)  # type: ignore[arg-type]


def test_render_includes_alert_name() -> None:
    md = _sample_render()
    assert "HighDBLatency" in md


def test_render_includes_root_cause() -> None:
    md = _sample_render()
    assert "Connection pool exhausted" in md


def test_render_includes_category() -> None:
    md = _sample_render()
    assert "database" in md


def test_render_includes_causal_chain() -> None:
    md = _sample_render()
    assert "Slow query backlog grew" in md
    assert "Pool hit max connections" in md


def test_render_includes_remediation() -> None:
    md = _sample_render()
    assert "Increase pool size" in md


def test_render_includes_validated_claim() -> None:
    md = _sample_render()
    assert "Pool was at 100%" in md


def test_render_includes_unvalidated_claim() -> None:
    md = _sample_render()
    assert "Index missing on users table" in md


def test_render_includes_evidence() -> None:
    md = _sample_render()
    assert "datadog_metrics" in md
    assert "DB connections maxed out" in md


def test_render_includes_confidence() -> None:
    md = _sample_render()
    assert "85%" in md


def test_render_includes_runbook_id() -> None:
    md = _sample_render()
    assert "abc123def456" in md


def test_render_includes_prevention_checklist() -> None:
    md = _sample_render()
    assert "Prevention" in md
    assert "post-mortem" in md.lower()


def test_render_empty_state_does_not_crash() -> None:
    md = _render_runbook(
        alert_name="test",
        root_cause="",
        root_cause_category="unknown",
        causal_chain=[],
        remediation_steps=[],
        validated_claims=[],
        non_validated_claims=[],
        validity_score=0.0,
        raw_alert={},
        evidence_entries=[],
        runbook_id="deadbeef",
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert "test" in md


# ---------------------------------------------------------------------------
# generate_runbook (uses temp dir)
# ---------------------------------------------------------------------------


def test_generate_runbook_creates_file(tmp_path: Path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        state = {
            "alert_name": "HighCPU",
            "root_cause": "Runaway cron job.",
            "root_cause_category": "cpu",
            "causal_chain": ["Cron job spawned 50 workers"],
            "remediation_steps": ["Kill the job", "Add concurrency limit"],
            "validated_claims": [],
            "non_validated_claims": [],
            "validity_score": 0.9,
            "raw_alert": {"service": "batch"},
            "evidence_entries": [],
        }
        result = generate_runbook(state)

    assert "runbook_id" in result
    assert "runbook_path" in result
    assert "runbook_md" in result
    assert Path(result["runbook_path"]).exists()
    content = Path(result["runbook_path"]).read_text()
    assert "HighCPU" in content


def test_generate_runbook_updates_index(tmp_path: Path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        state = {
            "alert_name": "TestAlert",
            "root_cause": "test",
            "root_cause_category": "test",
            "causal_chain": [],
            "remediation_steps": [],
            "validated_claims": [],
            "non_validated_claims": [],
            "validity_score": 0.5,
            "raw_alert": {},
            "evidence_entries": [],
        }
        result = generate_runbook(state)
        runbook_id = result["runbook_id"]

        index_path = tmp_path / "index.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text())
        ids = [e["runbook_id"] for e in index]
        assert runbook_id in ids


# ---------------------------------------------------------------------------
# list_runbooks
# ---------------------------------------------------------------------------


def test_list_runbooks_empty_dir(tmp_path: Path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        entries = list_runbooks()
    assert entries == []


def test_list_runbooks_returns_entries(tmp_path: Path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        for i in range(3):
            generate_runbook(
                {
                    "alert_name": f"Alert{i}",
                    "root_cause": f"cause {i}",
                    "root_cause_category": "network" if i < 2 else "cpu",
                    "causal_chain": [],
                    "remediation_steps": [],
                    "validated_claims": [],
                    "non_validated_claims": [],
                    "validity_score": 0.5,
                    "raw_alert": {},
                    "evidence_entries": [],
                }
            )

        all_entries = list_runbooks()
        assert len(all_entries) == 3

        network_entries = list_runbooks(category="network")
        assert len(network_entries) == 2

        cpu_entries = list_runbooks(category="cpu")
        assert len(cpu_entries) == 1


# ---------------------------------------------------------------------------
# load_runbook
# ---------------------------------------------------------------------------


def test_load_runbook_returns_none_for_unknown_id(tmp_path: Path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        assert load_runbook("does-not-exist") is None


def test_load_runbook_returns_content(tmp_path: Path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        state = {
            "alert_name": "LoadTest",
            "root_cause": "overload",
            "root_cause_category": "overload",
            "causal_chain": [],
            "remediation_steps": ["scale up"],
            "validated_claims": [],
            "non_validated_claims": [],
            "validity_score": 0.7,
            "raw_alert": {},
            "evidence_entries": [],
        }
        result = generate_runbook(state)
        content = load_runbook(result["runbook_id"])

    assert content is not None
    assert "LoadTest" in content
    assert "scale up" in content
