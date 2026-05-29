"""Tests for the Communication Pattern Analyzer tool."""

from __future__ import annotations

from app.tools.CommunicationPatternTool import (
    CommunicationPatternTool,
    analyze_communication_patterns,
    analyze_patterns,
)
from app.tools.registry import get_registered_tool_map


def _msg(ts: str, actor: str = "Alice", text: str = "Hi") -> dict:
    return {"timestamp": ts, "from_display_name": actor, "body_text": text}


class TestPatternToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "analyze_communication_patterns" in tool_map

    def test_source_is_knowledge(self) -> None:
        assert analyze_communication_patterns.source == "knowledge"

    def test_always_available(self) -> None:
        tool = CommunicationPatternTool()
        assert tool.is_available({})

    def test_input_schema_requires_messages(self) -> None:
        assert "messages" in analyze_communication_patterns.input_schema.get("required", [])


class TestAnalyzePatterns:
    def test_empty_messages(self) -> None:
        result = analyze_patterns([])
        assert result["total_messages"] == 0
        assert result["after_hours_flag"] is False

    def test_counts_total_messages(self) -> None:
        msgs = [_msg("2024-03-15T10:00:00Z") for _ in range(5)]
        result = analyze_patterns(msgs)
        assert result["total_messages"] == 5

    def test_detects_after_hours_messages(self) -> None:
        msgs = [
            _msg("2024-03-15T22:00:00Z"),  # 10pm UTC — after hours
            _msg("2024-03-15T23:30:00Z"),  # 11:30pm UTC — after hours
            _msg("2024-03-15T10:00:00Z"),  # 10am UTC — business hours
        ]
        result = analyze_patterns(msgs, after_hours_threshold=0.3)
        assert result["after_hours_count"] == 2
        assert result["after_hours_flag"] is True

    def test_weekend_messages_counted(self) -> None:
        msgs = [
            _msg("2024-03-16T10:00:00Z"),  # Saturday
            _msg("2024-03-17T11:00:00Z"),  # Sunday
            _msg("2024-03-18T10:00:00Z"),  # Monday
        ]
        result = analyze_patterns(msgs)
        assert result["weekend_messages"] == 2

    def test_weekly_volume_grouping(self) -> None:
        msgs = [
            _msg("2024-03-11T10:00:00Z"),
            _msg("2024-03-12T10:00:00Z"),
            _msg("2024-03-18T10:00:00Z"),  # next week
        ]
        result = analyze_patterns(msgs)
        assert len(result["weekly_volume"]) == 2
        assert sum(result["weekly_volume"].values()) == 3

    def test_actor_volume(self) -> None:
        msgs = [
            _msg("2024-03-15T10:00:00Z", actor="Alice"),
            _msg("2024-03-15T11:00:00Z", actor="Alice"),
            _msg("2024-03-15T12:00:00Z", actor="Bob"),
        ]
        result = analyze_patterns(msgs)
        assert result["actor_volume"]["Alice"] == 2
        assert result["actor_volume"]["Bob"] == 1

    def test_silence_gap_detected(self) -> None:
        msgs = [
            _msg("2024-03-01T10:00:00Z"),
            _msg("2024-03-15T10:00:00Z"),  # 14-day gap
        ]
        result = analyze_patterns(msgs, silence_gap_days=7)
        assert len(result["gaps"]) == 1
        assert result["gaps"][0]["gap_days"] == 14

    def test_no_gap_below_threshold(self) -> None:
        msgs = [
            _msg("2024-03-01T10:00:00Z"),
            _msg("2024-03-03T10:00:00Z"),  # 2-day gap
        ]
        result = analyze_patterns(msgs, silence_gap_days=7)
        assert result["gaps"] == []

    def test_focus_actor_filter(self) -> None:
        msgs = [
            _msg("2024-03-15T10:00:00Z", actor="Alice"),
            _msg("2024-03-15T11:00:00Z", actor="Bob"),
            _msg("2024-03-15T22:00:00Z", actor="Alice"),  # after hours
        ]
        result = analyze_patterns(msgs, focus_actors=["Alice"], after_hours_threshold=0.3)
        assert result["total_messages"] == 2
        assert "Bob" not in result["actor_volume"]

    def test_no_anomaly_all_business_hours(self) -> None:
        msgs = [_msg(f"2024-03-1{i}T10:00:00Z") for i in range(1, 6)]
        result = analyze_patterns(msgs, after_hours_threshold=0.3)
        assert result["after_hours_flag"] is False
        assert "No anomalous patterns detected." in result["patterns"]

    def test_busiest_hour(self) -> None:
        msgs = [
            _msg("2024-03-15T10:00:00Z"),
            _msg("2024-03-15T10:30:00Z"),
            _msg("2024-03-15T10:45:00Z"),
            _msg("2024-03-15T14:00:00Z"),
        ]
        result = analyze_patterns(msgs)
        assert result["busiest_hour"] == 10

    def test_date_range_reported(self) -> None:
        msgs = [
            _msg("2024-03-01T10:00:00Z"),
            _msg("2024-03-20T10:00:00Z"),
        ]
        result = analyze_patterns(msgs)
        assert result["date_range"]["start"] == "2024-03-01"
        assert result["date_range"]["end"] == "2024-03-20"

    def test_volume_spike_detected(self) -> None:
        # 1 message/week for 4 weeks, then 20 messages in one week
        msgs = [_msg(f"2024-0{m}-{d:02d}T10:00:00Z") for m, d in [(1, 5), (1, 12), (1, 19), (1, 26)]]
        spike_msgs = [_msg(f"2024-02-{5 + i:02d}T10:00:00Z") for i in range(20)]
        result = analyze_patterns(msgs + spike_msgs)
        assert result["volume_spikes"]

    def test_after_hours_messages_include_preview(self) -> None:
        msgs = [_msg("2024-03-15T22:00:00Z", text="Can we talk privately?")]
        result = analyze_patterns(msgs, after_hours_threshold=0.1)
        assert result["after_hours_messages"][0]["preview"] == "Can we talk privately?"

    def test_unparseable_timestamps_skipped(self) -> None:
        msgs = [
            {"timestamp": "not-a-date", "from_display_name": "Alice"},
            _msg("2024-03-15T10:00:00Z"),
        ]
        result = analyze_patterns(msgs)
        assert result["total_messages"] == 1


class TestCommunicationPatternToolRun:
    def test_run_empty(self) -> None:
        tool = CommunicationPatternTool()
        result = tool.run(messages=[])
        assert result["available"] is True
        assert result["total_messages"] == 0

    def test_run_none(self) -> None:
        tool = CommunicationPatternTool()
        result = tool.run()
        assert result["available"] is True

    def test_run_detects_after_hours(self) -> None:
        tool = CommunicationPatternTool()
        msgs = [
            _msg("2024-03-15T22:00:00Z", actor="Bob"),
            _msg("2024-03-15T23:00:00Z", actor="Bob"),
            _msg("2024-03-15T10:00:00Z", actor="Bob"),
        ]
        result = tool.run(messages=msgs, after_hours_threshold=0.5)
        assert result["available"] is True
        assert result["after_hours_count"] == 2

    def test_source_is_knowledge(self) -> None:
        tool = CommunicationPatternTool()
        result = tool.run(messages=[_msg("2024-03-15T10:00:00Z")])
        assert result["source"] == "knowledge"
