"""Evidence timeline builder tool — synthesizes multi-source evidence into a timeline."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.tools.base import BaseTool

_ISO_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})"  # date part required
    r"(?:[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)"  # optional time
    r"(Z|[+-]\d{2}:?\d{2})?)?",  # optional tz
)


def _parse_ts(value: str) -> datetime | None:
    """Parse an ISO-8601-ish timestamp or date string. Returns UTC datetime or None."""
    if not value:
        return None
    m = _ISO_RE.match(value.strip())
    if not m:
        return None
    date_part = m.group(1)
    time_part = m.group(2) or "00:00:00"
    tz_part = m.group(3) or "Z"
    tz_part = tz_part.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(f"{date_part}T{time_part}{tz_part}")
    except ValueError:
        try:
            dt = datetime.fromisoformat(f"{date_part}T00:00:00+00:00")
        except ValueError:
            return None
    return dt.astimezone(UTC)


def _actor_match(text: str, actors: list[str]) -> list[str]:
    """Return which actor names appear (case-insensitive) in text."""
    lower = text.lower()
    return [a for a in actors if a.lower() in lower]


def build_timeline(
    entries: list[dict[str, Any]],
    actors: list[str] | None = None,
    group_by_day: bool = True,
    max_entries: int = 200,
) -> dict[str, Any]:
    """Core timeline building logic, decoupled from the tool class for testability."""
    actors = actors or []
    parseable: list[tuple[datetime, dict[str, Any]]] = []
    unparseable: list[dict[str, Any]] = []

    for raw in entries[:max_entries]:
        ts_str = (
            raw.get("timestamp")
            or raw.get("created_at")
            or raw.get("received_at")
            or raw.get("date")
            or raw.get("occurred_at")
            or ""
        )
        dt = _parse_ts(str(ts_str))
        if dt is None:
            unparseable.append(raw)
            continue

        text = (
            raw.get("text")
            or raw.get("body_text")
            or raw.get("snippet")
            or raw.get("summary")
            or raw.get("description")
            or raw.get("title")
            or ""
        )
        source = raw.get("source", "unknown")
        actor = raw.get("from_display_name") or raw.get("from") or raw.get("author") or raw.get("actor") or ""
        mentioned_actors = _actor_match(f"{text} {actor}", actors)

        event: dict[str, Any] = {
            "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date": dt.strftime("%Y-%m-%d"),
            "source": source,
            "actor": actor,
            "text": text[:500],  # truncate long bodies
        }
        if mentioned_actors:
            event["mentioned_actors"] = mentioned_actors
        if raw.get("subject"):
            event["subject"] = raw["subject"]
        if raw.get("id"):
            event["id"] = raw["id"]
        if raw.get("web_url") or raw.get("url"):
            event["url"] = raw.get("web_url") or raw.get("url")

        parseable.append((dt, event))

    parseable.sort(key=lambda x: x[0])
    sorted_events = [ev for _, ev in parseable]

    if not group_by_day:
        return {
            "timeline": sorted_events,
            "total_events": len(sorted_events),
            "unparseable_count": len(unparseable),
            "actors_tracked": actors,
        }

    days: dict[str, list[dict[str, Any]]] = {}
    for ev in sorted_events:
        days.setdefault(ev["date"], []).append(ev)

    grouped = [
        {"date": day, "event_count": len(evs), "events": evs}
        for day, evs in sorted(days.items())
    ]

    involved_actors: set[str] = set()
    for ev in sorted_events:
        if ev.get("actor"):
            involved_actors.add(ev["actor"])

    return {
        "timeline": grouped,
        "total_events": len(sorted_events),
        "date_range": {
            "start": sorted_events[0]["date"] if sorted_events else None,
            "end": sorted_events[-1]["date"] if sorted_events else None,
        },
        "involved_actors": sorted(involved_actors),
        "actors_tracked": actors,
        "unparseable_count": len(unparseable),
        "sources_seen": sorted({ev["source"] for ev in sorted_events}),
    }


class EvidenceTimelineBuilderTool(BaseTool):
    """Synthesize multi-source evidence entries into a chronological timeline.

    Accepts raw evidence items from any tool output (emails, Teams messages,
    Jira issues, Slack messages, etc.) and produces a sorted, grouped timeline
    with actor tracking.  No external API calls are made — this is pure
    in-memory computation.
    """

    name = "build_evidence_timeline"
    source = "knowledge"
    description = (
        "Merge and sort evidence items from multiple sources into a chronological timeline. "
        "Accepts raw output entries from Gmail, Teams, Slack, Jira, or other tools and "
        "produces a structured day-by-day timeline with actor tracking for HR/legal review. "
        "Requires no credentials — operates entirely on data already gathered."
    )
    use_cases = [
        "Constructing a day-by-day incident timeline from emails, chats, and tickets",
        "Identifying gaps or overlaps in the evidence record for a specific date range",
        "Mapping which actors appear at each point in the timeline",
        "Preparing a chronological narrative for an HR investigation report",
        "Verifying the sequence of events claimed by parties in a complaint",
        "Ordering mixed-source evidence (email, Slack, Teams, Jira) into a single timeline",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "description": (
                    "List of evidence items to merge. Each item should have at least one "
                    "timestamp field (timestamp, created_at, received_at, date, occurred_at) "
                    "and a text field (text, body_text, snippet, summary, description, title). "
                    "Other optional fields: source, from_display_name/from/author/actor, "
                    "subject, id, web_url/url."
                ),
                "items": {"type": "object"},
            },
            "actors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names to track across the timeline (e.g. complainant, accused). "
                               "Events mentioning these names are flagged.",
            },
            "group_by_day": {
                "type": "boolean",
                "description": "Group timeline entries by calendar date (default: true). "
                               "Set false for a flat chronological list.",
                "default": True,
            },
            "max_entries": {
                "type": "integer",
                "description": "Maximum number of entries to process (default: 200)",
                "default": 200,
            },
        },
        "required": ["entries"],
    }
    outputs = {
        "timeline": "Chronological list of events, grouped by day if group_by_day=true",
        "total_events": "Number of events successfully placed on the timeline",
        "date_range": "Earliest and latest event dates",
        "involved_actors": "All actor names found across timeline events",
        "actors_tracked": "Actor names provided for highlighted tracking",
        "sources_seen": "Distinct source identifiers found in the entries",
        "unparseable_count": "Number of entries skipped due to missing/unparseable timestamps",
    }

    def is_available(self, _sources: dict) -> bool:
        return True  # pure computation, no credentials needed

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {"entries": [], "actors": [], "group_by_day": True, "max_entries": 200}

    def run(
        self,
        entries: list[dict[str, Any]] | None = None,
        actors: list[str] | None = None,
        group_by_day: bool = True,
        max_entries: int = 200,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not entries:
            return {
                "source": "knowledge",
                "available": True,
                "timeline": [],
                "total_events": 0,
                "unparseable_count": 0,
                "actors_tracked": actors or [],
                "message": "No entries provided.",
            }

        result = build_timeline(
            entries=entries,
            actors=actors or [],
            group_by_day=group_by_day,
            max_entries=max_entries,
        )
        result["source"] = "knowledge"
        result["available"] = True
        return result


build_evidence_timeline = EvidenceTimelineBuilderTool()
