"""Communication pattern analyzer — detects anomalous messaging behavior in evidence."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from app.tools.base import BaseTool

_ISO_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})"
    r"(?:[T ](\d{2}:\d{2}(?::\d{2})?)"
    r"(Z|[+-]\d{2}:?\d{2})?)?",
)


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    m = _ISO_RE.match(value.strip())
    if not m:
        return None
    date_part = m.group(1)
    time_part = m.group(2) or "00:00:00"
    tz_part = (m.group(3) or "Z").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(f"{date_part}T{time_part}{tz_part}").astimezone(UTC)
    except ValueError:
        return None


def _business_hour(dt: datetime, start_hour: int = 9, end_hour: int = 18) -> bool:
    """Return True if datetime falls within business hours (UTC) on a weekday."""
    if dt.weekday() >= 5:  # Sat=5, Sun=6
        return False
    return start_hour <= dt.hour < end_hour


def _week_label(dt: datetime) -> str:
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-W%W")


def analyze_patterns(
    messages: list[dict[str, Any]],
    focus_actors: list[str] | None = None,
    business_start_hour: int = 9,
    business_end_hour: int = 18,
    after_hours_threshold: float = 0.3,
    silence_gap_days: int = 7,
) -> dict[str, Any]:
    """Analyze message data for anomalous communication patterns.

    Args:
        messages: List of message dicts with timestamp/created_at and optionally
                  from_display_name/from/actor, body_text/text, source.
        focus_actors: If provided, only analyze messages involving these actors.
        business_start_hour: Start of business day (UTC hour, default 9).
        business_end_hour: End of business day (UTC hour, default 18).
        after_hours_threshold: Ratio of after-hours messages that triggers a flag (default 0.3).
        silence_gap_days: Days without messages that counts as a significant gap (default 7).
    """
    focus_actors = [a.lower() for a in (focus_actors or [])]

    parsed: list[tuple[datetime, dict[str, Any]]] = []
    for msg in messages:
        ts_str = (
            msg.get("timestamp") or msg.get("created_at") or msg.get("received_at") or ""
        )
        dt = _parse_dt(str(ts_str))
        if dt is None:
            continue
        actor = (
            msg.get("from_display_name") or msg.get("from") or msg.get("actor") or ""
        ).strip()
        if focus_actors and actor.lower() not in focus_actors:
            continue
        parsed.append((dt, {**msg, "_actor": actor, "_dt": dt}))

    if not parsed:
        return {
            "total_messages": 0,
            "after_hours_count": 0,
            "after_hours_ratio": 0.0,
            "after_hours_flag": False,
            "weekly_volume": {},
            "actor_volume": {},
            "gaps": [],
            "busiest_hour": None,
            "weekend_messages": 0,
            "patterns": [],
        }

    parsed.sort(key=lambda x: x[0])
    total = len(parsed)

    after_hours: list[dict[str, Any]] = []
    weekend_count = 0
    weekly: Counter[str] = Counter()
    actor_vol: Counter[str] = Counter()
    hour_vol: Counter[int] = Counter()

    for dt, msg in parsed:
        if not _business_hour(dt, business_start_hour, business_end_hour):
            after_hours.append(msg)
        if dt.weekday() >= 5:
            weekend_count += 1
        weekly[_week_label(dt)] += 1
        actor = msg["_actor"]
        if actor:
            actor_vol[actor] += 1
        hour_vol[dt.hour] += 1

    after_ratio = len(after_hours) / total

    # Detect volume spikes (week with >2x average)
    if weekly:
        avg_weekly = sum(weekly.values()) / len(weekly)
        spikes = [w for w, cnt in weekly.items() if cnt > max(2, avg_weekly * 2)]
    else:
        avg_weekly = 0.0
        spikes = []

    # Detect silence gaps
    gaps: list[dict[str, Any]] = []
    prev_dt = parsed[0][0]
    for dt, _ in parsed[1:]:
        delta = dt - prev_dt
        if delta.days >= silence_gap_days:
            gaps.append({
                "start": prev_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "gap_days": delta.days,
            })
        prev_dt = dt

    # Build pattern observations
    patterns: list[str] = []
    if after_ratio >= after_hours_threshold:
        patterns.append(
            f"{len(after_hours)} of {total} messages ({after_ratio:.0%}) sent outside business hours "
            f"({business_start_hour}:00–{business_end_hour}:00 UTC)."
        )
    if weekend_count:
        patterns.append(
            f"{weekend_count} messages sent on weekends."
        )
    if spikes:
        patterns.append(
            f"Volume spike(s) detected in weeks: {', '.join(spikes)} "
            f"(avg {avg_weekly:.1f} msgs/week)."
        )
    if gaps:
        patterns.append(
            f"{len(gaps)} silence gap(s) of {silence_gap_days}+ days detected."
        )
    if not patterns:
        patterns.append("No anomalous patterns detected.")

    busiest_hour = hour_vol.most_common(1)[0][0] if hour_vol else None

    return {
        "total_messages": total,
        "after_hours_count": len(after_hours),
        "after_hours_ratio": round(after_ratio, 3),
        "after_hours_flag": after_ratio >= after_hours_threshold,
        "after_hours_messages": [
            {
                "timestamp": m["_dt"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "actor": m["_actor"],
                "preview": (m.get("body_text") or m.get("text") or "")[:100],
            }
            for m in after_hours
        ],
        "weekend_messages": weekend_count,
        "weekly_volume": dict(sorted(weekly.items())),
        "volume_spikes": spikes,
        "actor_volume": dict(actor_vol.most_common()),
        "gaps": gaps,
        "busiest_hour": busiest_hour,
        "date_range": {
            "start": parsed[0][0].strftime("%Y-%m-%d"),
            "end": parsed[-1][0].strftime("%Y-%m-%d"),
        },
        "patterns": patterns,
    }


class CommunicationPatternTool(BaseTool):
    """Analyze communication metadata for anomalous patterns in HR/legal investigations.

    Processes message timestamps from any source (Slack, Teams, email, etc.)
    to detect after-hours messaging, volume spikes, weekend activity, and
    suspicious silence gaps. Pure in-memory computation — no credentials needed.
    """

    name = "analyze_communication_patterns"
    source = "knowledge"
    description = (
        "Detect anomalous communication patterns in message metadata collected during "
        "an HR/legal investigation. Identifies after-hours messaging, volume spikes, "
        "weekend activity, and suspicious silence gaps. Accepts output from any message-retrieval "
        "tool (Slack, Teams, Gmail, etc.). No credentials required."
    )
    use_cases = [
        "Detecting whether messages between parties were predominantly sent outside business hours",
        "Identifying a sudden spike in private messaging volume before or after an incident",
        "Finding suspicious silence gaps in communication that may indicate evidence deletion",
        "Mapping the busiest communication hours to establish a behavioral baseline",
        "Comparing communication frequency before and after a complaint was filed",
        "Documenting weekend or late-night messaging patterns in a harassment investigation",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "description": "Message items with timestamp/created_at and optional actor/from fields.",
                "items": {"type": "object"},
            },
            "focus_actors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "If provided, only analyze messages from/by these actors.",
            },
            "business_start_hour": {
                "type": "integer",
                "description": "Start of business day in UTC hour (default: 9)",
                "default": 9,
            },
            "business_end_hour": {
                "type": "integer",
                "description": "End of business day in UTC hour (default: 18)",
                "default": 18,
            },
            "after_hours_threshold": {
                "type": "number",
                "description": "Fraction of after-hours messages that triggers an anomaly flag (default: 0.3)",
                "default": 0.3,
            },
            "silence_gap_days": {
                "type": "integer",
                "description": "Days without messages that counts as a significant gap (default: 7)",
                "default": 7,
            },
        },
        "required": ["messages"],
    }
    outputs = {
        "total_messages": "Total number of messages analyzed",
        "after_hours_count": "Messages sent outside business hours",
        "after_hours_flag": "True if after-hours ratio exceeds threshold",
        "weekly_volume": "Message count per calendar week",
        "actor_volume": "Message count per actor",
        "gaps": "Silence gaps exceeding silence_gap_days",
        "patterns": "Human-readable list of detected anomalous patterns",
    }

    def is_available(self, _sources: dict) -> bool:
        return True

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {
            "messages": [],
            "focus_actors": [],
            "business_start_hour": 9,
            "business_end_hour": 18,
            "after_hours_threshold": 0.3,
            "silence_gap_days": 7,
        }

    def run(
        self,
        messages: list[dict[str, Any]] | None = None,
        focus_actors: list[str] | None = None,
        business_start_hour: int = 9,
        business_end_hour: int = 18,
        after_hours_threshold: float = 0.3,
        silence_gap_days: int = 7,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not messages:
            return {
                "source": "knowledge",
                "available": True,
                "total_messages": 0,
                "patterns": ["No messages provided."],
                "message": "No messages to analyze.",
            }

        result = analyze_patterns(
            messages=messages,
            focus_actors=focus_actors or [],
            business_start_hour=business_start_hour,
            business_end_hour=business_end_hour,
            after_hours_threshold=after_hours_threshold,
            silence_gap_days=silence_gap_days,
        )
        result["source"] = "knowledge"
        result["available"] = True
        return result


analyze_communication_patterns = CommunicationPatternTool()
