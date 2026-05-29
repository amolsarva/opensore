"""Unit tests for the incident similarity engine."""

from __future__ import annotations

from unittest.mock import patch

from app.pipeline.similarity import (
    _cosine,
    _tf,
    _tokenize,
    enrich_with_similar_incidents,
    find_similar_incidents,
)

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def test_tokenize_basic() -> None:
    tokens = _tokenize("High DB latency on payments service")
    assert "payments" in tokens
    assert "latency" in tokens
    assert "on" not in tokens  # stop word
    assert "high" in tokens


def test_tokenize_filters_short_tokens() -> None:
    tokens = _tokenize("a DB is up")
    assert "db" in tokens
    assert "a" not in tokens
    assert "is" not in tokens
    assert "up" not in tokens


def test_tokenize_lowercases() -> None:
    tokens = _tokenize("PAYMENTS SERVICE ERROR")
    assert "payments" in tokens
    assert "PAYMENTS" not in tokens


# ---------------------------------------------------------------------------
# TF
# ---------------------------------------------------------------------------


def test_tf_sums_to_one() -> None:
    tokens = ["a", "b", "a", "c"]
    tf = _tf(tokens)
    assert abs(sum(tf.values()) - 1.0) < 1e-9


def test_tf_empty_returns_empty() -> None:
    assert _tf([]) == {}


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def test_cosine_identical_vectors_returns_one() -> None:
    v = {"a": 0.5, "b": 0.5}
    assert abs(_cosine(v, v) - 1.0) < 1e-9


def test_cosine_disjoint_vectors_returns_zero() -> None:
    a = {"x": 1.0}
    b = {"y": 1.0}
    assert _cosine(a, b) == 0.0


def test_cosine_empty_vector_returns_zero() -> None:
    assert _cosine({}, {"a": 1.0}) == 0.0


def test_cosine_partial_overlap() -> None:
    a = {"a": 0.5, "b": 0.5}
    b = {"a": 0.5, "c": 0.5}
    score = _cosine(a, b)
    assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# find_similar_incidents — uses temp runbook dir
# ---------------------------------------------------------------------------


def _make_state(alert_name: str, root_cause: str, category: str) -> dict:
    return {
        "alert_name": alert_name,
        "root_cause": root_cause,
        "root_cause_category": category,
        "causal_chain": [],
        "remediation_steps": [],
        "validated_claims": [],
        "non_validated_claims": [],
        "validity_score": 0.7,
        "raw_alert": {},
        "evidence_entries": [],
    }


def test_find_similar_empty_index_returns_empty(tmp_path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        result = find_similar_incidents("HighDBLatency", "connection pool exhausted", "database")
    assert result == []


def test_find_similar_exact_match_scores_high(tmp_path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        from app.pipeline.runbook import generate_runbook

        generate_runbook(
            _make_state(
                "HighDBLatency",
                "Connection pool exhausted on payments RDS instance",
                "database",
            )
        )
        generate_runbook(
            _make_state("MemoryLeak", "RSS grew unbounded in worker process", "memory")
        )

        results = find_similar_incidents(
            alert_name="HighDBLatency",
            root_cause="connection pool exhausted payments database",
            root_cause_category="database",
            min_score=0.01,
        )

    assert len(results) >= 1
    top = results[0]
    assert "HighDBLatency" in top["alert_name"] or top["similarity_score"] > 0.1
    for r in results:
        assert "runbook_id" in r
        assert "similarity_score" in r
        assert "alert_name" in r


def test_find_similar_excludes_current_runbook(tmp_path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        from app.pipeline.runbook import generate_runbook

        result = generate_runbook(
            _make_state("HighDBLatency", "connection pool exhausted on RDS", "database")
        )
        current_id = result["runbook_id"]

        generate_runbook(_make_state("MemoryPressure", "OOM killer triggered on worker", "memory"))

        similar = find_similar_incidents(
            alert_name="HighDBLatency",
            root_cause="connection pool exhausted",
            root_cause_category="database",
            exclude_runbook_id=current_id,
            min_score=0.001,
        )

    runbook_ids = [s["runbook_id"] for s in similar]
    assert current_id not in runbook_ids


def test_find_similar_top_k_limit(tmp_path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        from app.pipeline.runbook import generate_runbook

        for i in range(5):
            generate_runbook(_make_state(f"Alert{i}", f"cause {i} database failure", "database"))

        results = find_similar_incidents(
            "NewAlert", "database connection failure", "database", top_k=2, min_score=0.001
        )

    assert len(results) <= 2


# ---------------------------------------------------------------------------
# enrich_with_similar_incidents (pipeline wrapper)
# ---------------------------------------------------------------------------


def test_enrich_returns_similar_incidents_key(tmp_path) -> None:
    with patch("app.pipeline.runbook._RUNBOOK_DIR", tmp_path):
        state = {
            "alert_name": "TestAlert",
            "root_cause": "disk full on host",
            "root_cause_category": "disk",
            "runbook_id": None,
        }
        updates = enrich_with_similar_incidents(state)

    assert "similar_incidents" in updates
    assert isinstance(updates["similar_incidents"], list)


def test_enrich_does_not_raise_on_empty_state() -> None:
    updates = enrich_with_similar_incidents({})
    assert "similar_incidents" in updates
