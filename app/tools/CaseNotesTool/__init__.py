"""HR investigation case notes tool — add, list, and export structured investigation notes."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.tools.base import BaseTool

NoteAction = Literal["add", "list", "get", "export", "delete"]

_DEFAULT_NOTES_DIR = Path.home() / ".opensore" / "case_notes"


def _notes_dir(base_dir: str | None = None) -> Path:
    return Path(base_dir) if base_dir else _DEFAULT_NOTES_DIR


def _case_file(case_id: str, base_dir: str | None = None) -> Path:
    return _notes_dir(base_dir) / f"{case_id}.json"


def _load_case(case_id: str, base_dir: str | None = None) -> dict[str, Any]:
    path = _case_file(case_id, base_dir)
    if not path.exists():
        return {
            "case_id": case_id,
            "created_at": datetime.now(UTC).isoformat(),
            "notes": [],
        }
    return json.loads(path.read_text())


def _save_case(case: dict[str, Any], base_dir: str | None = None) -> None:
    path = _case_file(case["case_id"], base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(case, indent=2))


def add_note(
    case_id: str,
    text: str,
    category: str = "general",
    author: str = "",
    tags: list[str] | None = None,
    base_dir: str | None = None,
) -> dict[str, Any]:
    case = _load_case(case_id, base_dir)
    note: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "category": category,
        "text": text,
    }
    if author:
        note["author"] = author
    if tags:
        note["tags"] = tags
    case["notes"].append(note)
    case["updated_at"] = note["created_at"]
    _save_case(case, base_dir)
    return {"note_id": note["id"], "case_id": case_id, "created_at": note["created_at"]}


def list_notes(
    case_id: str,
    category: str | None = None,
    base_dir: str | None = None,
) -> dict[str, Any]:
    case = _load_case(case_id, base_dir)
    notes = case["notes"]
    if category:
        notes = [n for n in notes if n.get("category") == category]
    return {
        "case_id": case_id,
        "notes": notes,
        "total": len(notes),
        "created_at": case.get("created_at", ""),
        "updated_at": case.get("updated_at", ""),
    }


def export_case(
    case_id: str,
    fmt: str = "json",
    base_dir: str | None = None,
) -> dict[str, Any]:
    case = _load_case(case_id, base_dir)
    if fmt == "text":
        lines = [f"Case: {case_id}", f"Created: {case.get('created_at', '')}", ""]
        for i, note in enumerate(case["notes"], 1):
            lines.append(f"[{i}] {note.get('created_at', '')} | {note.get('category', 'general')}")
            if note.get("author"):
                lines.append(f"    Author: {note['author']}")
            if note.get("tags"):
                lines.append(f"    Tags: {', '.join(note['tags'])}")
            lines.append(f"    {note.get('text', '')}")
            lines.append("")
        return {"case_id": case_id, "format": "text", "content": "\n".join(lines)}
    return {"case_id": case_id, "format": "json", "content": case}


def delete_note(
    case_id: str,
    note_id: str,
    base_dir: str | None = None,
) -> dict[str, Any]:
    case = _load_case(case_id, base_dir)
    original_count = len(case["notes"])
    case["notes"] = [n for n in case["notes"] if n.get("id") != note_id]
    if len(case["notes"]) == original_count:
        return {"deleted": False, "case_id": case_id, "note_id": note_id, "error": "Note not found."}
    case["updated_at"] = datetime.now(UTC).isoformat()
    _save_case(case, base_dir)
    return {"deleted": True, "case_id": case_id, "note_id": note_id}


class CaseNotesTool(BaseTool):
    """Add, list, and export structured investigation notes stored locally.

    Notes are persisted as JSON files under ``~/.opensore/case_notes/<case_id>.json``
    (or a custom ``notes_dir``). No credentials required.  Use to maintain a
    structured record of findings, observations, and follow-up items during
    an HR/legal investigation.
    """

    name = "manage_case_notes"
    source = "knowledge"
    description = (
        "Add, list, get, export, or delete structured notes for an HR/legal investigation case. "
        "Notes are stored locally as JSON and support categorization (finding, interview, "
        "action_item, timeline, general), tagging, and text export. No credentials required. "
        "Use to maintain a running record of evidence findings and investigative observations."
    )
    use_cases = [
        "Recording key findings from each tool run during an investigation",
        "Capturing interview summaries and witness statements as structured notes",
        "Tracking action items and follow-up steps during a case",
        "Exporting all case notes as a human-readable text summary for a report",
        "Tagging notes with actor names for later filtering",
        "Maintaining a persistent investigation record across multiple sessions",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "get", "export", "delete"],
                "description": (
                    "Operation to perform: "
                    "'add' — add a note; "
                    "'list' — list all notes for a case; "
                    "'get' — list notes filtered by category; "
                    "'export' — export all notes as JSON or text; "
                    "'delete' — remove a specific note by ID."
                ),
            },
            "case_id": {
                "type": "string",
                "description": "Investigation case identifier (e.g. 'HR-2024-042')",
            },
            "text": {
                "type": "string",
                "description": "Note text (required for 'add')",
            },
            "category": {
                "type": "string",
                "enum": ["general", "finding", "interview", "action_item", "timeline"],
                "description": "Note category (default: 'general')",
                "default": "general",
            },
            "author": {
                "type": "string",
                "description": "Name of the investigator adding the note",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for the note (e.g. actor names, topics)",
            },
            "note_id": {
                "type": "string",
                "description": "UUID of an existing note (required for 'delete')",
            },
            "format": {
                "type": "string",
                "enum": ["json", "text"],
                "description": "Export format (default: 'json'). Use 'text' for a human-readable summary.",
                "default": "json",
            },
            "notes_dir": {
                "type": "string",
                "description": "Override directory for note storage (default: ~/.opensore/case_notes)",
            },
        },
        "required": ["action", "case_id"],
    }
    outputs = {
        "note_id": "UUID of the newly created note (for 'add')",
        "notes": "List of notes (for 'list' and 'get')",
        "total": "Count of notes returned",
        "content": "Exported case data (for 'export')",
        "deleted": "Boolean indicating whether a note was deleted",
    }

    def is_available(self, _sources: dict) -> bool:
        return True  # no credentials required

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {
            "action": "list",
            "case_id": "",
            "text": "",
            "category": "general",
            "author": "",
            "tags": [],
            "note_id": "",
            "format": "json",
            "notes_dir": "",
        }

    def run(
        self,
        action: str = "list",
        case_id: str = "",
        text: str = "",
        category: str = "general",
        author: str = "",
        tags: list[str] | None = None,
        note_id: str = "",
        format: str = "json",  # noqa: A002
        notes_dir: str = "",
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not case_id:
            return {"source": "knowledge", "available": False, "error": "case_id is required."}

        base = notes_dir or None

        try:
            if action == "add":
                if not text:
                    return {
                        "source": "knowledge",
                        "available": False,
                        "error": "text is required for 'add' action.",
                    }
                result = add_note(
                    case_id=case_id,
                    text=text,
                    category=category,
                    author=author,
                    tags=tags or [],
                    base_dir=base,
                )
            elif action in ("list", "get"):
                cat = category if action == "get" else None
                result = list_notes(case_id=case_id, category=cat, base_dir=base)
            elif action == "export":
                result = export_case(case_id=case_id, fmt=format, base_dir=base)
            elif action == "delete":
                if not note_id:
                    return {
                        "source": "knowledge",
                        "available": False,
                        "error": "note_id is required for 'delete' action.",
                    }
                result = delete_note(case_id=case_id, note_id=note_id, base_dir=base)
            else:
                return {
                    "source": "knowledge",
                    "available": False,
                    "error": f"Unknown action '{action}'. Use: add, list, get, export, delete.",
                }
        except Exception as exc:
            return {"source": "knowledge", "available": False, "error": str(exc)}

        result["source"] = "knowledge"
        result["available"] = True
        return result


manage_case_notes = CaseNotesTool()
