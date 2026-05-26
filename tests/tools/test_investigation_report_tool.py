"""Tests for the Investigation Report Generator tool."""

from __future__ import annotations

from app.tools.InvestigationReportTool import (
    InvestigationReportTool,
    generate_investigation_report,
    generate_report,
)
from app.tools.registry import get_registered_tool_map

PARTIES = [
    {"role": "Complainant", "name": "Alice Johnson", "title": "Software Engineer", "department": "Engineering"},
    {"role": "Respondent", "name": "Bob Manager", "title": "Engineering Manager", "department": "Engineering"},
]

FINDINGS = [
    {
        "label": "Unsolicited contact",
        "text": "Alice received 14 direct messages from Bob outside working hours over 6 weeks.",
        "source": "slack",
        "date": "2024-03-01 – 2024-04-15",
    },
    {
        "label": "Pattern of private meetings",
        "text": "Google Calendar shows 8 private 1:1 meetings not on the team calendar.",
        "source": "google_calendar",
        "date": "2024-01-10 – 2024-03-20",
    },
]

CONTRADICTIONS = [
    {
        "type": "negation_conflict",
        "statement_a": {"actor": "Bob", "text_preview": "I never contacted Alice outside of work."},
        "statement_b": {"actor": "Alice", "text_preview": "Bob messaged me repeatedly after hours."},
        "note": "Bob denies contact that Slack records confirm.",
    }
]


class TestReportToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "generate_investigation_report" in tool_map

    def test_source_is_knowledge(self) -> None:
        assert generate_investigation_report.source == "knowledge"

    def test_always_available(self) -> None:
        tool = InvestigationReportTool()
        assert tool.is_available({})

    def test_required_fields(self) -> None:
        assert "case_id" in generate_investigation_report.input_schema.get("required", [])

    def test_use_cases_are_report_focused(self) -> None:
        assert any("report" in uc.lower() for uc in generate_investigation_report.use_cases)


class TestGenerateReport:
    def test_minimal_report(self) -> None:
        result = generate_report(case_id="HR-001")
        assert "case_id" in result
        assert result["case_id"] == "HR-001"

    def test_text_format_contains_case_id(self) -> None:
        result = generate_report(case_id="HR-2024-042", fmt="text")
        assert "HR-2024-042" in result["report"]

    def test_text_format_contains_confidentiality_notice(self) -> None:
        result = generate_report(case_id="HR-001", fmt="text")
        assert "CONFIDENTIAL" in result["report"]

    def test_text_format_includes_parties(self) -> None:
        result = generate_report(case_id="HR-001", parties=PARTIES, fmt="text")
        assert "Alice Johnson" in result["report"]
        assert "Bob Manager" in result["report"]
        assert "Complainant" in result["report"]

    def test_text_format_includes_findings(self) -> None:
        result = generate_report(case_id="HR-001", findings=FINDINGS, fmt="text")
        assert "Unsolicited contact" in result["report"]
        assert "KEY FINDINGS" in result["report"]

    def test_text_format_includes_contradictions(self) -> None:
        result = generate_report(case_id="HR-001", contradictions=CONTRADICTIONS, fmt="text")
        assert "EVIDENTIARY CONTRADICTIONS" in result["report"]
        assert "Bob" in result["report"]

    def test_text_format_includes_timeline(self) -> None:
        events = [
            {"timestamp": "2024-03-10T09:00:00Z", "actor": "Bob", "text": "Meeting scheduled.", "source": "calendar"},
        ]
        result = generate_report(case_id="HR-001", timeline_events=events, fmt="text")
        assert "TIMELINE OF EVENTS" in result["report"]
        assert "Bob" in result["report"]

    def test_text_format_includes_conclusions_and_recommendations(self) -> None:
        result = generate_report(
            case_id="HR-001",
            conclusions="Evidence supports the complaint.",
            recommendations=["Issue formal warning to respondent", "Mandatory harassment training"],
            fmt="text",
        )
        assert "CONCLUSIONS" in result["report"]
        assert "Evidence supports the complaint." in result["report"]
        assert "RECOMMENDATIONS" in result["report"]
        assert "formal warning" in result["report"]

    def test_json_format(self) -> None:
        result = generate_report(case_id="HR-001", investigator="Jane", fmt="json")
        assert isinstance(result["sections"], dict)
        assert result["case_id"] == "HR-001"

    def test_section_count_reflects_populated_sections(self) -> None:
        empty = generate_report(case_id="HR-001", fmt="text")
        with_findings = generate_report(case_id="HR-001", findings=FINDINGS, fmt="text")
        assert with_findings["section_count"] > empty["section_count"]

    def test_custom_confidentiality_notice(self) -> None:
        result = generate_report(
            case_id="HR-001",
            confidentiality_notice="PRIVILEGED AND CONFIDENTIAL",
            fmt="text",
        )
        assert "PRIVILEGED AND CONFIDENTIAL" in result["report"]

    def test_investigator_appears_in_text(self) -> None:
        result = generate_report(case_id="HR-001", investigator="Jane Investigator", fmt="text")
        assert "Jane Investigator" in result["report"]


class TestInvestigationReportToolRun:
    def test_run_without_case_id(self) -> None:
        tool = InvestigationReportTool()
        result = tool.run(case_id="")
        assert result["available"] is False
        assert "case_id" in result["error"]

    def test_run_minimal(self) -> None:
        tool = InvestigationReportTool()
        result = tool.run(case_id="HR-001")
        assert result["available"] is True
        assert result["case_id"] == "HR-001"
        assert "report" in result

    def test_run_full_text_report(self) -> None:
        tool = InvestigationReportTool()
        result = tool.run(
            case_id="HR-2024-042",
            investigator="Jane Investigator",
            case_summary="Complaint of workplace harassment filed by Alice Johnson against Bob Manager.",
            parties=PARTIES,
            findings=FINDINGS,
            contradictions=CONTRADICTIONS,
            conclusions="Evidence supports the complainant's account.",
            recommendations=["Issue formal warning.", "Mandatory retraining."],
            format="text",
        )
        assert result["available"] is True
        assert "HR-2024-042" in result["report"]
        assert "Alice Johnson" in result["report"]
        assert "KEY FINDINGS" in result["report"]
        assert "EVIDENTIARY CONTRADICTIONS" in result["report"]
        assert result["section_count"] >= 4

    def test_run_json_format(self) -> None:
        tool = InvestigationReportTool()
        result = tool.run(case_id="HR-001", findings=FINDINGS, format="json")
        assert result["available"] is True
        assert isinstance(result["sections"], dict)
        assert "findings" in result["sections"]

    def test_generated_at_is_present(self) -> None:
        tool = InvestigationReportTool()
        result = tool.run(case_id="HR-001")
        assert "generated_at" in result
        assert result["generated_at"]  # non-empty
