"""Tests for the HR investigation case notes tool."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.tools.CaseNotesTool import (
    CaseNotesTool,
    add_note,
    delete_note,
    export_case,
    list_notes,
    manage_case_notes,
)
from app.tools.registry import get_registered_tool_map


@pytest.fixture()
def tmp_notes_dir(tmp_path: Path) -> str:
    return str(tmp_path / "notes")


class TestCaseNotesMetadata:
    def test_tool_registered(self) -> None:
        tool_map = get_registered_tool_map("investigation")
        assert "manage_case_notes" in tool_map

    def test_source_is_knowledge(self) -> None:
        assert manage_case_notes.source == "knowledge"

    def test_always_available(self) -> None:
        tool = CaseNotesTool()
        assert tool.is_available({})

    def test_input_schema_required_fields(self) -> None:
        required = manage_case_notes.input_schema.get("required", [])
        assert "action" in required
        assert "case_id" in required

    def test_action_enum(self) -> None:
        props = manage_case_notes.input_schema["properties"]
        assert "add" in props["action"]["enum"]
        assert "list" in props["action"]["enum"]
        assert "export" in props["action"]["enum"]


class TestAddNote:
    def test_add_note(self, tmp_notes_dir: str) -> None:
        result = add_note("HR-001", "First finding.", base_dir=tmp_notes_dir)
        assert "note_id" in result
        assert result["case_id"] == "HR-001"

    def test_note_persisted(self, tmp_notes_dir: str) -> None:
        add_note("HR-001", "A note.", category="finding", base_dir=tmp_notes_dir)
        case_file = Path(tmp_notes_dir) / "HR-001.json"
        assert case_file.exists()
        data = json.loads(case_file.read_text())
        assert len(data["notes"]) == 1
        assert data["notes"][0]["text"] == "A note."
        assert data["notes"][0]["category"] == "finding"

    def test_multiple_notes(self, tmp_notes_dir: str) -> None:
        add_note("HR-001", "Note 1", base_dir=tmp_notes_dir)
        add_note("HR-001", "Note 2", base_dir=tmp_notes_dir)
        result = list_notes("HR-001", base_dir=tmp_notes_dir)
        assert result["total"] == 2

    def test_note_with_tags_and_author(self, tmp_notes_dir: str) -> None:
        add_note(
            "HR-001",
            "Interview with Alice.",
            category="interview",
            author="Jane Investigator",
            tags=["Alice", "Witness"],
            base_dir=tmp_notes_dir,
        )
        result = list_notes("HR-001", base_dir=tmp_notes_dir)
        note = result["notes"][0]
        assert note["author"] == "Jane Investigator"
        assert "Alice" in note["tags"]


class TestListNotes:
    def test_list_empty_case(self, tmp_notes_dir: str) -> None:
        result = list_notes("HR-999", base_dir=tmp_notes_dir)
        assert result["total"] == 0
        assert result["notes"] == []

    def test_list_all_notes(self, tmp_notes_dir: str) -> None:
        add_note("HR-002", "General note", category="general", base_dir=tmp_notes_dir)
        add_note("HR-002", "Finding note", category="finding", base_dir=tmp_notes_dir)
        result = list_notes("HR-002", base_dir=tmp_notes_dir)
        assert result["total"] == 2

    def test_filter_by_category(self, tmp_notes_dir: str) -> None:
        add_note("HR-002", "General note", category="general", base_dir=tmp_notes_dir)
        add_note("HR-002", "Finding note", category="finding", base_dir=tmp_notes_dir)
        result = list_notes("HR-002", category="finding", base_dir=tmp_notes_dir)
        assert result["total"] == 1
        assert result["notes"][0]["category"] == "finding"


class TestDeleteNote:
    def test_delete_existing_note(self, tmp_notes_dir: str) -> None:
        add_result = add_note("HR-003", "To delete", base_dir=tmp_notes_dir)
        note_id = add_result["note_id"]
        del_result = delete_note("HR-003", note_id, base_dir=tmp_notes_dir)
        assert del_result["deleted"] is True
        list_result = list_notes("HR-003", base_dir=tmp_notes_dir)
        assert list_result["total"] == 0

    def test_delete_nonexistent_note(self, tmp_notes_dir: str) -> None:
        result = delete_note("HR-003", str(uuid.uuid4()), base_dir=tmp_notes_dir)
        assert result["deleted"] is False
        assert "not found" in result["error"].lower()

    def test_delete_one_of_many(self, tmp_notes_dir: str) -> None:
        r1 = add_note("HR-003", "Keep this", base_dir=tmp_notes_dir)
        r2 = add_note("HR-003", "Delete this", base_dir=tmp_notes_dir)
        delete_note("HR-003", r2["note_id"], base_dir=tmp_notes_dir)
        result = list_notes("HR-003", base_dir=tmp_notes_dir)
        assert result["total"] == 1
        assert result["notes"][0]["id"] == r1["note_id"]


class TestExportCase:
    def test_export_json(self, tmp_notes_dir: str) -> None:
        add_note("HR-004", "Finding A", category="finding", base_dir=tmp_notes_dir)
        result = export_case("HR-004", fmt="json", base_dir=tmp_notes_dir)
        assert result["format"] == "json"
        assert isinstance(result["content"], dict)
        assert "notes" in result["content"]

    def test_export_text(self, tmp_notes_dir: str) -> None:
        add_note("HR-004", "Finding A", category="finding", author="Jane", base_dir=tmp_notes_dir)
        result = export_case("HR-004", fmt="text", base_dir=tmp_notes_dir)
        assert result["format"] == "text"
        assert "Case: HR-004" in result["content"]
        assert "Finding A" in result["content"]
        assert "Jane" in result["content"]

    def test_export_empty_case_text(self, tmp_notes_dir: str) -> None:
        result = export_case("HR-EMPTY", fmt="text", base_dir=tmp_notes_dir)
        assert "Case: HR-EMPTY" in result["content"]


class TestCaseNotesToolRun:
    def test_run_add(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        result = tool.run(
            action="add",
            case_id="HR-010",
            text="Witness confirmed the incident.",
            category="interview",
            notes_dir=tmp_notes_dir,
        )
        assert result["available"] is True
        assert "note_id" in result

    def test_run_add_without_text(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        result = tool.run(action="add", case_id="HR-010", notes_dir=tmp_notes_dir)
        assert result["available"] is False
        assert "text" in result["error"]

    def test_run_without_case_id(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        result = tool.run(action="list", case_id="", notes_dir=tmp_notes_dir)
        assert result["available"] is False

    def test_run_list(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        tool.run(action="add", case_id="HR-010", text="Note 1", notes_dir=tmp_notes_dir)
        tool.run(action="add", case_id="HR-010", text="Note 2", notes_dir=tmp_notes_dir)
        result = tool.run(action="list", case_id="HR-010", notes_dir=tmp_notes_dir)
        assert result["available"] is True
        assert result["total"] == 2

    def test_run_get_filtered(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        tool.run(action="add", case_id="HR-010", text="General", category="general", notes_dir=tmp_notes_dir)
        tool.run(action="add", case_id="HR-010", text="Finding", category="finding", notes_dir=tmp_notes_dir)
        result = tool.run(action="get", case_id="HR-010", category="finding", notes_dir=tmp_notes_dir)
        assert result["available"] is True
        assert result["total"] == 1
        assert result["notes"][0]["text"] == "Finding"

    def test_run_export(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        tool.run(action="add", case_id="HR-010", text="Export test", notes_dir=tmp_notes_dir)
        result = tool.run(action="export", case_id="HR-010", format="text", notes_dir=tmp_notes_dir)
        assert result["available"] is True
        assert "Export test" in result["content"]

    def test_run_delete(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        add_result = tool.run(
            action="add", case_id="HR-010", text="Delete me", notes_dir=tmp_notes_dir
        )
        note_id = add_result["note_id"]
        del_result = tool.run(
            action="delete", case_id="HR-010", note_id=note_id, notes_dir=tmp_notes_dir
        )
        assert del_result["available"] is True
        assert del_result["deleted"] is True

    def test_run_delete_without_note_id(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        result = tool.run(action="delete", case_id="HR-010", notes_dir=tmp_notes_dir)
        assert result["available"] is False
        assert "note_id" in result["error"]

    def test_run_unknown_action(self, tmp_notes_dir: str) -> None:
        tool = CaseNotesTool()
        result = tool.run(action="fly", case_id="HR-010", notes_dir=tmp_notes_dir)
        assert result["available"] is False
        assert "Unknown action" in result["error"]
