"""Investigation report generator — assembles structured HR/legal investigation reports."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.tools.base import BaseTool

_SECTION_ORDER = [
    "executive_summary",
    "parties",
    "complaint_summary",
    "methodology",
    "findings",
    "timeline",
    "contradictions",
    "conclusions",
    "recommendations",
]


def _format_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except (ValueError, AttributeError):
        return iso


def _indent(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def generate_report(
    case_id: str,
    investigator: str = "",
    case_summary: str = "",
    parties: list[dict[str, Any]] | None = None,
    findings: list[dict[str, Any]] | None = None,
    timeline_events: list[dict[str, Any]] | None = None,
    contradictions: list[dict[str, Any]] | None = None,
    conclusions: str = "",
    recommendations: list[str] | None = None,
    report_date: str = "",
    confidentiality_notice: str = "CONFIDENTIAL — ATTORNEY-CLIENT PRIVILEGED",
    fmt: str = "text",
) -> dict[str, Any]:
    """Generate a structured investigation report.

    All inputs are optional — include what has been gathered. The report
    is assembled in a consistent structure regardless of which sections
    are populated.
    """
    generated_at = report_date or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    display_date = _format_date(generated_at)

    sections: dict[str, Any] = {}

    # Executive summary
    exec_lines = [f"Case ID: {case_id}", f"Date: {display_date}"]
    if investigator:
        exec_lines.append(f"Investigator: {investigator}")
    if case_summary:
        exec_lines.append(f"\n{case_summary}")
    sections["executive_summary"] = "\n".join(exec_lines)

    # Parties
    if parties:
        party_lines = []
        for p in parties:
            role = p.get("role", "Party")
            name = p.get("name", "Unknown")
            title = p.get("title", "")
            dept = p.get("department", "")
            line = f"  {role}: {name}"
            if title:
                line += f", {title}"
            if dept:
                line += f" ({dept})"
            party_lines.append(line)
        sections["parties"] = "\n".join(party_lines)

    # Findings
    if findings:
        finding_lines = []
        for i, f in enumerate(findings, 1):
            label = f.get("label", f"Finding {i}")
            text = f.get("text", "")
            source = f.get("source", "")
            date = f.get("date", "")
            header = f"  [{i}] {label}"
            if date:
                header += f" ({date})"
            finding_lines.append(header)
            if text:
                finding_lines.append(f"      {text}")
            if source:
                finding_lines.append(f"      Source: {source}")
        sections["findings"] = "\n".join(finding_lines)

    # Timeline
    if timeline_events:
        tl_lines = []
        for ev in timeline_events:
            ts = ev.get("timestamp") or ev.get("date", "")
            actor = ev.get("actor", "")
            text = ev.get("text", "")[:200]
            source = ev.get("source", "")
            line = f"  {ts}"
            if actor:
                line += f"  [{actor}]"
            if source:
                line += f"  ({source})"
            line += f"\n    {text}"
            tl_lines.append(line)
        sections["timeline"] = "\n".join(tl_lines)

    # Contradictions
    if contradictions:
        c_lines = []
        for c in contradictions:
            ctype = c.get("type", "conflict").replace("_", " ").title()
            note = c.get("note", "")
            a_actor = (c.get("statement_a") or {}).get("actor", "")
            b_actor = (c.get("statement_b") or {}).get("actor", "")
            a_text = (c.get("statement_a") or {}).get("text_preview", "")[:100]
            b_text = (c.get("statement_b") or {}).get("text_preview", "")[:100]
            c_lines.append(f"  [{ctype}] {note}")
            if a_actor:
                c_lines.append(f"    {a_actor}: \"{a_text}...\"")
            if b_actor:
                c_lines.append(f"    {b_actor}: \"{b_text}...\"")
        sections["contradictions"] = "\n".join(c_lines)

    # Conclusions
    if conclusions:
        sections["conclusions"] = f"  {conclusions}"

    # Recommendations
    if recommendations:
        rec_lines = [f"  {i + 1}. {r}" for i, r in enumerate(recommendations)]
        sections["recommendations"] = "\n".join(rec_lines)

    if fmt == "json":
        return {
            "case_id": case_id,
            "generated_at": generated_at,
            "investigator": investigator,
            "confidentiality_notice": confidentiality_notice,
            "sections": sections,
        }

    # Text format
    header_map = {
        "executive_summary": "EXECUTIVE SUMMARY",
        "parties": "PARTIES",
        "findings": "KEY FINDINGS",
        "timeline": "TIMELINE OF EVENTS",
        "contradictions": "EVIDENTIARY CONTRADICTIONS",
        "conclusions": "CONCLUSIONS",
        "recommendations": "RECOMMENDATIONS",
    }

    lines = [
        confidentiality_notice,
        "=" * 60,
        f"INVESTIGATION REPORT — Case {case_id}",
        "=" * 60,
        "",
    ]

    for key in _SECTION_ORDER:
        if key not in sections:
            continue
        title = header_map.get(key, key.replace("_", " ").upper())
        lines.append(title)
        lines.append("-" * len(title))
        lines.append(sections[key])
        lines.append("")

    text_report = "\n".join(lines)

    return {
        "case_id": case_id,
        "generated_at": generated_at,
        "investigator": investigator,
        "format": "text",
        "report": text_report,
        "sections": sections,
        "section_count": len(sections),
    }


class InvestigationReportTool(BaseTool):
    """Generate a structured HR/legal investigation report from gathered evidence.

    Assembles findings, timeline, contradictions, and conclusions into a
    formatted report suitable for HR review or legal proceedings.
    Pure computation — no credentials required.
    """

    name = "generate_investigation_report"
    source = "knowledge"
    description = (
        "Assemble a structured HR/legal investigation report from gathered evidence. "
        "Accepts findings, timeline events, contradictions, parties, and conclusions, "
        "and produces a formatted report in text or JSON. Suitable for HR review, "
        "legal disclosure, or case closure documentation. No credentials required."
    )
    use_cases = [
        "Generating a final investigation report after all evidence has been gathered",
        "Producing a structured summary of findings for HR leadership review",
        "Creating a timeline-anchored report for legal counsel",
        "Documenting contradictions and their evidentiary basis in a report",
        "Generating a preliminary report at the midpoint of a long investigation",
        "Formatting findings into a consistent structure for cross-case comparison",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "case_id": {
                "type": "string",
                "description": "Investigation case identifier (e.g. 'HR-2024-042')",
            },
            "investigator": {"type": "string", "description": "Name of the lead investigator"},
            "case_summary": {
                "type": "string",
                "description": "1-3 sentence summary of the complaint and investigation scope",
            },
            "parties": {
                "type": "array",
                "description": "List of parties with 'role', 'name', 'title', 'department'",
                "items": {"type": "object"},
            },
            "findings": {
                "type": "array",
                "description": "Key findings, each with 'label', 'text', 'source', 'date'",
                "items": {"type": "object"},
            },
            "timeline_events": {
                "type": "array",
                "description": "Chronological events from build_evidence_timeline or manual entry",
                "items": {"type": "object"},
            },
            "contradictions": {
                "type": "array",
                "description": "Contradictions from detect_evidence_contradictions",
                "items": {"type": "object"},
            },
            "conclusions": {
                "type": "string",
                "description": "Investigator's overall conclusions",
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Recommended actions or next steps",
            },
            "format": {
                "type": "string",
                "enum": ["text", "json"],
                "description": "Output format (default: 'text')",
                "default": "text",
            },
            "confidentiality_notice": {
                "type": "string",
                "description": "Header confidentiality notice (default: 'CONFIDENTIAL — ATTORNEY-CLIENT PRIVILEGED')",
            },
        },
        "required": ["case_id"],
    }
    outputs = {
        "report": "Full text report (when format=text)",
        "sections": "Dict of named sections (always included)",
        "section_count": "Number of sections populated",
        "generated_at": "ISO-8601 timestamp when the report was generated",
    }

    def is_available(self, _sources: dict) -> bool:
        return True

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {
            "case_id": "",
            "investigator": "",
            "case_summary": "",
            "parties": [],
            "findings": [],
            "timeline_events": [],
            "contradictions": [],
            "conclusions": "",
            "recommendations": [],
            "format": "text",
        }

    def run(
        self,
        case_id: str = "",
        investigator: str = "",
        case_summary: str = "",
        parties: list[dict[str, Any]] | None = None,
        findings: list[dict[str, Any]] | None = None,
        timeline_events: list[dict[str, Any]] | None = None,
        contradictions: list[dict[str, Any]] | None = None,
        conclusions: str = "",
        recommendations: list[str] | None = None,
        format: str = "text",  # noqa: A002
        confidentiality_notice: str = "CONFIDENTIAL — ATTORNEY-CLIENT PRIVILEGED",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not case_id:
            return {
                "source": "knowledge",
                "available": False,
                "error": "case_id is required.",
            }

        result = generate_report(
            case_id=case_id,
            investigator=investigator,
            case_summary=case_summary,
            parties=parties or [],
            findings=findings or [],
            timeline_events=timeline_events or [],
            contradictions=contradictions or [],
            conclusions=conclusions,
            recommendations=recommendations or [],
            fmt=format,
            confidentiality_notice=confidentiality_notice,
        )
        result["source"] = "knowledge"
        result["available"] = True
        return result


generate_investigation_report = InvestigationReportTool()
