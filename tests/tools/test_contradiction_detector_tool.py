"""Tests for the Evidence Contradiction Detector tool."""

from __future__ import annotations

from app.tools.ContradictionDetectorTool import (
    ContradictionDetectorTool,
    detect_contradictions,
    detect_evidence_contradictions,
)
from app.tools.registry import get_registered_tool_map


class TestContradictionToolMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "detect_evidence_contradictions" in tool_map

    def test_source_is_knowledge(self) -> None:
        assert detect_evidence_contradictions.source == "knowledge"

    def test_always_available(self) -> None:
        tool = ContradictionDetectorTool()
        assert tool.is_available({})

    def test_input_schema_requires_statements(self) -> None:
        assert "statements" in detect_evidence_contradictions.input_schema.get("required", [])

    def test_use_cases_are_investigation_focused(self) -> None:
        assert any("contradict" in uc.lower() for uc in detect_evidence_contradictions.use_cases)


class TestDetectContradictions:
    def test_empty_statements(self) -> None:
        result = detect_contradictions([])
        assert result["total_contradictions"] == 0
        assert result["statements_analyzed"] == 0

    def test_no_contradiction_unrelated_statements(self) -> None:
        stmts = [
            {"text": "The cat sat on the mat.", "actor": "Alice"},
            {"text": "Revenue grew 20% this quarter.", "actor": "Bob"},
        ]
        result = detect_contradictions(stmts)
        assert result["total_contradictions"] == 0

    def test_negation_conflict_detected(self) -> None:
        stmts = [
            {
                "text": "I never met with Bob during the project review meeting.",
                "actor": "Alice",
                "id": "s1",
            },
            {
                "text": "Alice and I met during the project review meeting.",
                "actor": "Bob",
                "id": "s2",
            },
        ]
        result = detect_contradictions(stmts, similarity_threshold=0.1)
        assert result["negation_conflicts"] >= 1
        assert result["total_contradictions"] >= 1
        conflict = result["contradictions"][0]
        assert conflict["type"] == "negation_conflict"

    def test_date_conflict_detected(self) -> None:
        stmts = [
            {
                "text": "The incident occurred during the team meeting on 2024-03-10.",
                "actor": "Alice",
            },
            {
                "text": "The incident occurred during the team meeting on 2024-03-15.",
                "actor": "Bob",
            },
        ]
        result = detect_contradictions(stmts, similarity_threshold=0.1)
        assert result["date_conflicts"] >= 1
        conflict = next(c for c in result["contradictions"] if c["type"] == "date_conflict")
        assert "2024-03-10" in str(conflict["statement_a"]["dates_mentioned"])
        assert "2024-03-15" in str(conflict["statement_b"]["dates_mentioned"])

    def test_self_contradiction_detected(self) -> None:
        stmts = [
            {
                "text": "I was not present at the meeting when the discussion happened.",
                "actor": "Alice",
                "id": "s1",
            },
            {
                "text": "I was present and attended the meeting when the discussion happened.",
                "actor": "Alice",
                "id": "s2",
            },
        ]
        result = detect_contradictions(stmts, similarity_threshold=0.1)
        assert result["self_contradictions"] >= 1
        self_c = next(c for c in result["contradictions"] if c["type"] == "self_contradiction")
        assert self_c["actor"] == "Alice"

    def test_statements_analyzed_count(self) -> None:
        stmts = [
            {"text": "Statement one.", "actor": "A"},
            {"text": "Statement two.", "actor": "B"},
            {"text": "Statement three.", "actor": "C"},
        ]
        result = detect_contradictions(stmts)
        assert result["statements_analyzed"] == 3

    def test_actors_analyzed_reported(self) -> None:
        stmts = [
            {"text": "I did attend the meeting.", "actor": "Alice"},
            {"text": "I did not attend the meeting.", "actor": "Bob"},
        ]
        result = detect_contradictions(stmts)
        assert "Alice" in result["actors_analyzed"]
        assert "Bob" in result["actors_analyzed"]

    def test_similarity_threshold_controls_sensitivity(self) -> None:
        stmts = [
            {"text": "I met with Alice yesterday.", "actor": "Bob"},
            {"text": "Bob never met with me.", "actor": "Alice"},
        ]
        tight = detect_contradictions(stmts, similarity_threshold=0.9)
        loose = detect_contradictions(stmts, similarity_threshold=0.05)
        # At very tight threshold nothing should match
        assert tight["total_contradictions"] == 0
        # At very loose threshold at least one conflict expected
        assert loose["total_contradictions"] >= 1

    def test_statement_ref_includes_id(self) -> None:
        stmts = [
            {"text": "I never saw the report.", "actor": "Alice", "id": "stmt-001"},
            {"text": "Alice saw and reviewed the report.", "actor": "Bob", "id": "stmt-002"},
        ]
        result = detect_contradictions(stmts, similarity_threshold=0.05)
        if result["contradictions"]:
            conflict = result["contradictions"][0]
            assert "id" in conflict["statement_a"] or "id" in conflict["statement_b"]

    def test_no_false_positive_agreement(self) -> None:
        stmts = [
            {"text": "The meeting was held on Monday at noon in conference room B.", "actor": "Alice"},
            {"text": "The meeting was held on Monday at noon in conference room B.", "actor": "Bob"},
        ]
        result = detect_contradictions(stmts, similarity_threshold=0.1)
        # Identical statements should not generate contradictions
        assert result["negation_conflicts"] == 0
        assert result["self_contradictions"] == 0


class TestContradictionToolRun:
    def test_run_empty(self) -> None:
        tool = ContradictionDetectorTool()
        result = tool.run(statements=[])
        assert result["available"] is True
        assert result["total_contradictions"] == 0
        assert "No statements provided" in result["message"]

    def test_run_none(self) -> None:
        tool = ContradictionDetectorTool()
        result = tool.run()
        assert result["available"] is True
        assert result["total_contradictions"] == 0

    def test_run_detects_conflict(self) -> None:
        tool = ContradictionDetectorTool()
        result = tool.run(
            statements=[
                {"text": "I was never in that meeting with Alice.", "actor": "Bob"},
                {"text": "Bob attended the meeting with Alice.", "actor": "HR Investigator"},
            ],
            similarity_threshold=0.05,
        )
        assert result["available"] is True
        assert result["total_contradictions"] >= 1

    def test_source_is_knowledge(self) -> None:
        tool = ContradictionDetectorTool()
        result = tool.run(statements=[{"text": "Test", "actor": "A"}])
        assert result["source"] == "knowledge"
