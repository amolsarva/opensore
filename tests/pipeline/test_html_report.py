"""Tests for the HTML report generator."""

from __future__ import annotations

from app.pipeline.html_report import generate_html_report


def _make_state(**overrides):
    base = {
        "alert_name": "HighDBLatency",
        "root_cause": "Connection pool exhausted on payments RDS.",
        "root_cause_category": "database",
        "severity": "critical",
        "validity_score": 0.87,
        "remediation_steps": [
            "Increase max_connections in RDS parameter group.",
            "Add connection pooling via PgBouncer.",
        ],
        "similar_incidents": [],
        "runbook_id": "rb-test123",
        "raw_alert": {"service": "payments", "env": "prod"},
    }
    return {**base, **overrides}


def test_generates_valid_html() -> None:
    html = generate_html_report(_make_state())
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "</html>" in html


def test_contains_alert_name() -> None:
    html = generate_html_report(_make_state())
    assert "HighDBLatency" in html


def test_contains_root_cause() -> None:
    html = generate_html_report(_make_state())
    assert "Connection pool exhausted" in html


def test_contains_remediation_steps() -> None:
    html = generate_html_report(_make_state())
    assert "PgBouncer" in html
    assert "max_connections" in html


def test_contains_severity_badge() -> None:
    html = generate_html_report(_make_state(severity="critical"))
    assert "badge-critical" in html or "critical" in html


def test_contains_confidence_score() -> None:
    html = generate_html_report(_make_state(validity_score=0.87))
    assert "87%" in html


def test_contains_runbook_id() -> None:
    html = generate_html_report(_make_state())
    assert "rb-test123" in html


def test_escapes_html_in_alert_name() -> None:
    html = generate_html_report(_make_state(alert_name="<script>alert(1)</script>"))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html or "script" not in html.lower().split("title")[1][:100]


def test_empty_state_does_not_raise() -> None:
    html = generate_html_report({})
    assert "<!DOCTYPE html>" in html


def test_runbook_markdown_rendered() -> None:
    md = "## Root Cause\n\nConnection pool **exhausted**.\n\n- Restart service\n- Check logs"
    html = generate_html_report(_make_state(), runbook_md=md)
    assert "<h2>" in html
    assert "<strong>" in html


def test_similar_incidents_rendered() -> None:
    state = _make_state(
        similar_incidents=[
            {
                "runbook_id": "rb-old1",
                "alert_name": "HighDBLatency",
                "root_cause_category": "database",
                "similarity_score": 0.92,
            }
        ]
    )
    html = generate_html_report(state)
    assert "rb-old1" in html
    assert "92%" in html


def test_raw_alert_json_included() -> None:
    html = generate_html_report(_make_state())
    assert "payments" in html
    assert "prod" in html
