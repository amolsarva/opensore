"""Evidence contradiction detector — flags inconsistencies across statements and evidence."""

from __future__ import annotations

import re
from typing import Any

from app.tools.base import BaseTool

_DATE_RE = re.compile(
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?)\b",
    re.IGNORECASE,
)

_NEGATION_WORDS = frozenset(
    ["never", "not", "didn't", "did not", "wasn't", "was not", "denied", "deny", "denies",
     "no", "none", "nobody", "nothing", "cannot", "can't", "couldn't", "wouldn't",
     "haven't", "hadn't", "hasn't"]
)

_PRESENT_WORDS = frozenset(
    ["yes", "did", "was", "were", "met", "attended", "saw", "confirmed", "admitted",
     "agreed", "acknowledged", "told", "sent", "received", "spoke", "called"]
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _extract_dates(text: str) -> list[str]:
    return [m.group(0).lower() for m in _DATE_RE.finditer(text)]


def _has_negation(text: str) -> bool:
    lower = text.lower()
    return any(f" {w} " in f" {lower} " or lower.startswith(w + " ") for w in _NEGATION_WORDS)


def _has_affirmation(text: str) -> bool:
    lower = text.lower()
    return any(f" {w} " in f" {lower} " or lower.startswith(w + " ") for w in _PRESENT_WORDS)


def _overlap_ratio(a: str, b: str) -> float:
    """Jaccard overlap between word sets of two strings."""
    words_a = set(re.findall(r"\b\w{4,}\b", a.lower()))
    words_b = set(re.findall(r"\b\w{4,}\b", b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def detect_contradictions(
    statements: list[dict[str, Any]],
    actors: list[str] | None = None,
    similarity_threshold: float = 0.15,
) -> dict[str, Any]:
    """Compare statements across actors and evidence for logical contradictions.

    Each statement dict should have:
        - ``text``: the statement or evidence text (required)
        - ``actor``: who made this statement (optional)
        - ``source``: evidence source (optional)
        - ``timestamp`` / ``date``: when the statement was made (optional)
        - ``id``: identifier for referencing (optional)

    Returns contradiction pairs, date conflicts, and negation conflicts.
    """
    actors = actors or []
    flagged: list[dict[str, Any]] = []
    date_conflicts: list[dict[str, Any]] = []
    negation_conflicts: list[dict[str, Any]] = []

    for i, stmt_a in enumerate(statements):
        text_a = _normalize(stmt_a.get("text", ""))
        dates_a = _extract_dates(text_a)
        neg_a = _has_negation(text_a)
        aff_a = _has_affirmation(text_a)
        actor_a = stmt_a.get("actor", "")

        for stmt_b in statements[i + 1:]:
            actor_b = stmt_b.get("actor", "")

            # Skip statements by the same actor (intra-actor contradictions are handled separately)
            if actor_a and actor_b and actor_a == actor_b:
                continue

            text_b = _normalize(stmt_b.get("text", ""))
            dates_b = _extract_dates(text_b)
            neg_b = _has_negation(text_b)
            aff_b = _has_affirmation(text_b)

            overlap = _overlap_ratio(text_a, text_b)
            if overlap < similarity_threshold:
                continue

            # Negation conflict: one affirms, the other denies — on similar topic
            if (neg_a and aff_b) or (neg_b and aff_a):
                negation_conflicts.append({
                    "type": "negation_conflict",
                    "statement_a": _stmt_ref(stmt_a),
                    "statement_b": _stmt_ref(stmt_b),
                    "overlap_score": round(overlap, 3),
                    "note": "One statement affirms while the other denies on a similar topic.",
                })

            # Date conflict: both mention dates but different ones
            if dates_a and dates_b and not set(dates_a) & set(dates_b):
                date_conflicts.append({
                    "type": "date_conflict",
                    "statement_a": {**_stmt_ref(stmt_a), "dates_mentioned": dates_a},
                    "statement_b": {**_stmt_ref(stmt_b), "dates_mentioned": dates_b},
                    "overlap_score": round(overlap, 3),
                    "note": "Statements share context but reference different dates.",
                })

    # Intra-actor contradictions: same actor contradicts themselves
    actor_statements: dict[str, list[dict[str, Any]]] = {}
    for stmt in statements:
        actor = stmt.get("actor", "")
        if actor:
            actor_statements.setdefault(actor, []).append(stmt)

    for actor, stmts in actor_statements.items():
        for i, s_a in enumerate(stmts):
            for s_b in stmts[i + 1:]:
                text_a = _normalize(s_a.get("text", ""))
                text_b = _normalize(s_b.get("text", ""))
                overlap = _overlap_ratio(text_a, text_b)
                if overlap >= similarity_threshold:
                    neg_a = _has_negation(text_a)
                    neg_b = _has_negation(text_b)
                    aff_a = _has_affirmation(text_a)
                    aff_b = _has_affirmation(text_b)
                    if (neg_a and aff_b) or (neg_b and aff_a):
                        flagged.append({
                            "type": "self_contradiction",
                            "actor": actor,
                            "statement_a": _stmt_ref(s_a),
                            "statement_b": _stmt_ref(s_b),
                            "overlap_score": round(overlap, 3),
                            "note": f"{actor} appears to contradict themselves across statements.",
                        })

    all_contradictions = negation_conflicts + date_conflicts + flagged
    return {
        "contradictions": all_contradictions,
        "total_contradictions": len(all_contradictions),
        "negation_conflicts": len(negation_conflicts),
        "date_conflicts": len(date_conflicts),
        "self_contradictions": len(flagged),
        "statements_analyzed": len(statements),
        "actors_analyzed": list(actor_statements.keys()),
    }


def _stmt_ref(stmt: dict[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {"text_preview": stmt.get("text", "")[:150]}
    for field in ("id", "actor", "source", "timestamp", "date"):
        if stmt.get(field):
            ref[field] = stmt[field]
    return ref


class ContradictionDetectorTool(BaseTool):
    """Detect logical contradictions and inconsistencies across evidence statements.

    Compares statement texts for negation conflicts (one affirms, another denies
    on the same topic), date conflicts (same context, different dates), and
    self-contradictions (same actor contradicting themselves across statements).
    Pure in-memory computation — no credentials required.
    """

    name = "detect_evidence_contradictions"
    source = "knowledge"
    description = (
        "Analyze a set of evidence statements for logical contradictions: negation conflicts "
        "(one party affirms what another denies), date discrepancies (same topic, different dates), "
        "and self-contradictions (an actor contradicting their own prior statements). "
        "Operates on text collected from emails, chats, interviews, or case notes. "
        "No credentials required."
    )
    use_cases = [
        "Identifying whether a subject's account of events contradicts witness statements",
        "Detecting inconsistencies in meeting attendance claims across multiple sources",
        "Flagging date discrepancies between a complainant's timeline and documentation",
        "Finding cases where an accused denies actions that are confirmed by other parties",
        "Spotting self-contradictions in an employee's multiple written or verbal statements",
        "Cross-referencing claims from different interviews to surface inconsistencies",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "statements": {
                "type": "array",
                "description": (
                    "List of statement/evidence items to compare. Each should have 'text' "
                    "(required) and optionally 'actor', 'source', 'timestamp'/'date', 'id'."
                ),
                "items": {"type": "object"},
            },
            "actors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Actor names to focus contradiction analysis on (optional filter).",
            },
            "similarity_threshold": {
                "type": "number",
                "description": "Minimum word-overlap Jaccard score to consider statements related (default: 0.15)",
                "default": 0.15,
            },
        },
        "required": ["statements"],
    }
    outputs = {
        "contradictions": "List of contradiction findings with type, statements, and explanation",
        "total_contradictions": "Total number of contradictions found",
        "negation_conflicts": "Count of affirm-vs-deny conflicts across actors",
        "date_conflicts": "Count of date discrepancy conflicts",
        "self_contradictions": "Count of same-actor self-contradictions",
        "statements_analyzed": "Number of statements processed",
    }

    def is_available(self, _sources: dict) -> bool:
        return True

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {"statements": [], "actors": [], "similarity_threshold": 0.15}

    def run(
        self,
        statements: list[dict[str, Any]] | None = None,
        actors: list[str] | None = None,
        similarity_threshold: float = 0.15,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not statements:
            return {
                "source": "knowledge",
                "available": True,
                "contradictions": [],
                "total_contradictions": 0,
                "negation_conflicts": 0,
                "date_conflicts": 0,
                "self_contradictions": 0,
                "statements_analyzed": 0,
                "message": "No statements provided.",
            }

        result = detect_contradictions(
            statements=statements,
            actors=actors or [],
            similarity_threshold=similarity_threshold,
        )
        result["source"] = "knowledge"
        result["available"] = True
        return result


detect_evidence_contradictions = ContradictionDetectorTool()
