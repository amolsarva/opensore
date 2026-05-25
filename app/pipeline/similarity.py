"""Incident similarity engine — find past runbooks that match the current alert.

Uses TF-IDF-style keyword scoring against the runbook index and stored documents.
No LLM calls: fast, deterministic, and works offline.

Called automatically at the end of each investigation; results appear in the
investigation state as ``similar_incidents`` (list of matches with scores).
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "up",
        "about",
        "into",
        "through",
        "during",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "not",
        "no",
        "nor",
        "due",
        "after",
        "before",
        "when",
        "while",
        "if",
        "then",
        "than",
    }
)


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9_\-]{1,}", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS]


def _tf(tokens: list[str]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = max(len(tokens), 1)
    return {term: count / total for term, count in counts.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[t] * b[t] for t in common)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if not mag_a or not mag_b:
        return 0.0
    return dot / (mag_a * mag_b)


def _runbook_to_text(entry: dict[str, Any], content: str) -> str:
    parts = [
        entry.get("alert_name", ""),
        entry.get("root_cause_category", ""),
        content[:2000],
    ]
    return " ".join(p for p in parts if p)


def find_similar_incidents(
    alert_name: str,
    root_cause: str,
    root_cause_category: str,
    top_k: int = 3,
    min_score: float = 0.10,
    exclude_runbook_id: str = "",
) -> list[dict[str, Any]]:
    """Return the top-k most similar past incidents from the runbook index.

    Args:
        alert_name: Name of the current alert.
        root_cause: Root cause text from the current investigation.
        root_cause_category: Category from the current investigation.
        top_k: Maximum number of similar incidents to return.
        min_score: Minimum cosine similarity to include a match.
        exclude_runbook_id: ID of the current runbook (to avoid self-match).

    Returns:
        List of dicts with runbook_id, alert_name, root_cause_category,
        similarity_score, generated_at, and a brief excerpt.
    """
    try:
        from app.pipeline.runbook import list_runbooks, load_runbook
    except ImportError:
        return []

    query_text = f"{alert_name} {root_cause} {root_cause_category}"
    query_tf = _tf(_tokenize(query_text))
    if not query_tf:
        return []

    entries = list_runbooks(limit=200)
    if not entries:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in entries:
        rid = entry.get("runbook_id", "")
        if rid == exclude_runbook_id:
            continue
        try:
            content = load_runbook(rid) or ""
        except Exception:
            content = ""
        doc_text = _runbook_to_text(entry, content)
        doc_tf = _tf(_tokenize(doc_text))
        score = _cosine(query_tf, doc_tf)
        if score >= min_score:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, entry in scored[:top_k]:
        rid = entry.get("runbook_id", "")
        excerpt = ""
        try:
            content = load_runbook(rid) or ""
            lines = [
                ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("#")
            ]
            excerpt = " ".join(lines[:3])[:200]
        except Exception:
            pass
        results.append(
            {
                "runbook_id": rid,
                "alert_name": entry.get("alert_name", ""),
                "root_cause_category": entry.get("root_cause_category", ""),
                "similarity_score": round(score, 3),
                "generated_at": entry.get("generated_at", "")[:16].replace("T", " "),
                "excerpt": excerpt,
            }
        )

    return results


def enrich_with_similar_incidents(state: dict[str, Any]) -> dict[str, Any]:
    """Wrapper called from the investigation pipeline.

    Returns state updates: ``similar_incidents`` list.
    """
    try:
        similar = find_similar_incidents(
            alert_name=str(state.get("alert_name") or ""),
            root_cause=str(state.get("root_cause") or ""),
            root_cause_category=str(state.get("root_cause_category") or "unknown"),
            exclude_runbook_id=str(state.get("runbook_id") or ""),
        )
        if similar:
            logger.info(
                "[similarity] found %d similar past incidents (top score: %.2f)",
                len(similar),
                similar[0]["similarity_score"],
            )
        return {"similar_incidents": similar}
    except Exception as exc:
        logger.warning("[similarity] enrichment failed (non-fatal): %s", exc)
        return {"similar_incidents": []}
