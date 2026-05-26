"""Tests for the Evidence Timeline Builder tool."""

from __future__ import annotations

from app.tools.EvidenceTimelineTool import (
    EvidenceTimelineBuilderTool,
    build_evidence_timeline,
    build_timeline,
)
from app.tools.registry import get_registered_tool_map


class TestTimelineToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "build_evidence_timeline" in tool_map

    def test_source_is_knowledge(self) -> None:
        assert build_evidence_timeline.source == "knowledge"

    def test_always_available(self) -> None:
        tool = EvidenceTimelineBuilderTool()
        assert tool.is_available({})
        assert tool.is_available({"anything": "here"})

    def test_input_schema_has_entries(self) -> None:
        schema = build_evidence_timeline.input_schema
        assert "entries" in schema.get("required", [])
        assert "actors" in schema["properties"]
        assert "group_by_day" in schema["properties"]

    def test_use_cases_are_investigation_focused(self) -> None:
        assert any("timeline" in uc.lower() for uc in build_evidence_timeline.use_cases)


class TestBuildTimeline:
    def test_empty_entries(self) -> None:
        result = build_timeline([])
        assert result["total_events"] == 0
        assert result["timeline"] == []

    def test_single_entry(self) -> None:
        entries = [
            {
                "timestamp": "2024-03-15T10:00:00Z",
                "source": "slack",
                "text": "Meeting tomorrow?",
                "from_display_name": "Alice",
            }
        ]
        result = build_timeline(entries)
        assert result["total_events"] == 1
        assert result["date_range"]["start"] == "2024-03-15"
        assert result["date_range"]["end"] == "2024-03-15"

    def test_chronological_sorting(self) -> None:
        entries = [
            {"timestamp": "2024-03-20T12:00:00Z", "text": "Later", "source": "email"},
            {"timestamp": "2024-03-15T08:00:00Z", "text": "Earlier", "source": "email"},
            {"timestamp": "2024-03-17T09:00:00Z", "text": "Middle", "source": "jira"},
        ]
        result = build_timeline(entries, group_by_day=False)
        dates = [ev["date"] for ev in result["timeline"]]
        assert dates == ["2024-03-15", "2024-03-17", "2024-03-20"]

    def test_group_by_day(self) -> None:
        entries = [
            {"timestamp": "2024-03-15T08:00:00Z", "text": "Morning msg", "source": "slack"},
            {"timestamp": "2024-03-15T14:00:00Z", "text": "Afternoon msg", "source": "slack"},
            {"timestamp": "2024-03-16T09:00:00Z", "text": "Next day", "source": "email"},
        ]
        result = build_timeline(entries, group_by_day=True)
        assert len(result["timeline"]) == 2
        march_15 = result["timeline"][0]
        assert march_15["date"] == "2024-03-15"
        assert march_15["event_count"] == 2

    def test_actor_tracking(self) -> None:
        entries = [
            {
                "timestamp": "2024-03-15T10:00:00Z",
                "text": "I need to report Bob's behavior",
                "from_display_name": "Alice Johnson",
                "source": "email",
            },
            {
                "timestamp": "2024-03-16T11:00:00Z",
                "text": "HR received a complaint",
                "from_display_name": "HR Team",
                "source": "jira",
            },
        ]
        result = build_timeline(entries, actors=["Bob", "Alice Johnson"])
        assert "Alice Johnson" in result["involved_actors"]
        assert result["actors_tracked"] == ["Bob", "Alice Johnson"]
        flat = [ev for day in result["timeline"] for ev in day["events"]]
        alice_ev = next(ev for ev in flat if ev["actor"] == "Alice Johnson")
        assert "Alice Johnson" in alice_ev.get("mentioned_actors", [])

    def test_unparseable_entries_counted(self) -> None:
        entries = [
            {"timestamp": "2024-03-15T10:00:00Z", "text": "Valid", "source": "slack"},
            {"timestamp": "not-a-date", "text": "Invalid timestamp", "source": "email"},
            {"text": "No timestamp at all", "source": "jira"},
        ]
        result = build_timeline(entries)
        assert result["total_events"] == 1
        assert result["unparseable_count"] == 2

    def test_fallback_timestamp_fields(self) -> None:
        entries = [
            {"created_at": "2024-04-01T09:00:00Z", "body_text": "Teams msg", "source": "teams"},
            {"received_at": "2024-04-02T10:00:00Z", "snippet": "Email snippet", "source": "email"},
            {"date": "2024-04-03", "description": "Jira comment", "source": "jira"},
        ]
        result = build_timeline(entries, group_by_day=False)
        assert result["total_events"] == 3
        assert result["timeline"][0]["source"] == "teams"
        assert result["timeline"][1]["source"] == "email"
        assert result["timeline"][2]["source"] == "jira"

    def test_sources_seen(self) -> None:
        entries = [
            {"timestamp": "2024-03-15T10:00:00Z", "text": "A", "source": "slack"},
            {"timestamp": "2024-03-15T11:00:00Z", "text": "B", "source": "email"},
            {"timestamp": "2024-03-15T12:00:00Z", "text": "C", "source": "slack"},
        ]
        result = build_timeline(entries)
        assert result["sources_seen"] == ["email", "slack"]

    def test_max_entries_limit(self) -> None:
        entries = [
            {
                "timestamp": f"2024-03-{str(i % 28 + 1).zfill(2)}T10:00:00Z",
                "text": f"Entry {i}",
                "source": "slack",
            }
            for i in range(100)
        ]
        result = build_timeline(entries, max_entries=10)
        assert result["total_events"] == 10

    def test_url_preserved(self) -> None:
        entries = [
            {
                "timestamp": "2024-03-15T10:00:00Z",
                "text": "A message",
                "source": "teams",
                "web_url": "https://teams.microsoft.com/l/message/abc",
            }
        ]
        result = build_timeline(entries, group_by_day=False)
        assert result["timeline"][0]["url"] == "https://teams.microsoft.com/l/message/abc"

    def test_text_truncation(self) -> None:
        entries = [
            {
                "timestamp": "2024-03-15T10:00:00Z",
                "text": "x" * 1000,
                "source": "email",
            }
        ]
        result = build_timeline(entries, group_by_day=False)
        assert len(result["timeline"][0]["text"]) == 500

    def test_subject_preserved_for_emails(self) -> None:
        entries = [
            {
                "timestamp": "2024-03-15T10:00:00Z",
                "subject": "FW: Complaint regarding incident",
                "snippet": "Please review the attached report",
                "source": "email",
            }
        ]
        result = build_timeline(entries, group_by_day=False)
        ev = result["timeline"][0]
        assert ev["subject"] == "FW: Complaint regarding incident"
        assert ev["text"] == "Please review the attached report"


class TestEvidenceTimelineToolRun:
    def test_run_empty_entries(self) -> None:
        tool = EvidenceTimelineBuilderTool()
        result = tool.run(entries=[])
        assert result["available"] is True
        assert result["total_events"] == 0
        assert "No entries provided" in result["message"]

    def test_run_none_entries(self) -> None:
        tool = EvidenceTimelineBuilderTool()
        result = tool.run()
        assert result["available"] is True
        assert result["total_events"] == 0

    def test_run_with_real_data(self) -> None:
        entries = [
            {
                "created_at": "2024-05-10T08:00:00Z",
                "body_text": "I want to report a concern about my manager.",
                "from_display_name": "Sarah Chen",
                "source": "email",
            },
            {
                "timestamp": "2024-05-10T09:30:00Z",
                "body_text": "HR opened a case for Sarah's complaint.",
                "from_display_name": "HR Department",
                "source": "jira",
                "id": "HR-1234",
            },
            {
                "timestamp": "2024-05-12T11:00:00Z",
                "body_text": "Interview notes: Sarah described three incidents.",
                "from_display_name": "Jane Investigator",
                "source": "google_docs",
            },
        ]
        tool = EvidenceTimelineBuilderTool()
        result = tool.run(entries=entries, actors=["Sarah Chen"], group_by_day=True)
        assert result["available"] is True
        assert result["total_events"] == 3
        assert result["date_range"]["start"] == "2024-05-10"
        assert result["date_range"]["end"] == "2024-05-12"
        assert "Sarah Chen" in result["involved_actors"]
        assert len(result["timeline"]) == 2  # 2 days

    def test_run_flat_mode(self) -> None:
        entries = [
            {"timestamp": "2024-03-15T10:00:00Z", "text": "Alpha", "source": "slack"},
            {"timestamp": "2024-03-15T11:00:00Z", "text": "Beta", "source": "teams"},
        ]
        tool = EvidenceTimelineBuilderTool()
        result = tool.run(entries=entries, group_by_day=False)
        assert result["available"] is True
        assert isinstance(result["timeline"], list)
        assert result["timeline"][0]["text"] == "Alpha"
        assert result["timeline"][1]["text"] == "Beta"
