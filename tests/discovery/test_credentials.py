"""Tests for the discovery credential store (app/discovery/credentials.py)."""

from __future__ import annotations

from pathlib import Path

from app.discovery.credentials import (
    list_sources,
    new_source_id,
    remove_source,
    upsert_source,
)


def _make_record(record_id: str = "gs_abc12345", kind: str = "google_workspace") -> dict:
    return {
        "id": record_id,
        "kind": kind,
        "label": f"test-{record_id}@example.com",
        "connected_at": "2026-05-25T12:00:00Z",
    }


def test_list_sources_empty(tmp_path: Path) -> None:
    store = tmp_path / "discovery_sources.json"
    result = list_sources(store)
    assert result == []


def test_upsert_and_list(tmp_path: Path) -> None:
    store = tmp_path / "discovery_sources.json"
    record = _make_record("gs_aabbccdd")
    upsert_source(record, store)
    sources = list_sources(store)
    assert len(sources) == 1
    assert sources[0]["id"] == "gs_aabbccdd"
    assert sources[0]["kind"] == "google_workspace"


def test_upsert_is_idempotent(tmp_path: Path) -> None:
    store = tmp_path / "discovery_sources.json"
    record = _make_record("gs_idempotent")
    upsert_source(record, store)
    updated = dict(record, label="updated@example.com")
    upsert_source(updated, store)
    sources = list_sources(store)
    assert len(sources) == 1
    assert sources[0]["label"] == "updated@example.com"


def test_remove_source(tmp_path: Path) -> None:
    store = tmp_path / "discovery_sources.json"
    record = _make_record("gs_todelete")
    upsert_source(record, store)
    assert list_sources(store)
    removed = remove_source("gs_todelete", store)
    assert removed is True
    assert list_sources(store) == []


def test_remove_nonexistent_returns_false(tmp_path: Path) -> None:
    store = tmp_path / "discovery_sources.json"
    removed = remove_source("gs_doesnotexist", store)
    assert removed is False


def test_new_source_id_prefix() -> None:
    source_id = new_source_id("gs")
    assert source_id.startswith("gs_")
    assert len(source_id) == len("gs_") + 8

    sl_id = new_source_id("sl")
    assert sl_id.startswith("sl_")

    default_id = new_source_id()
    assert default_id.startswith("src_")
