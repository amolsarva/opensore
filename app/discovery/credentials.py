"""File-based credential store for discovery workspace source connectors.

Credentials are stored at ~/.config/opensore/discovery_sources.json.
All mutations use a filelock + atomic write so concurrent CLI invocations
cannot corrupt the store.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from filelock import FileLock, Timeout

from app.constants import DISCOVERY_SOURCES_PATH

_VERSION = 1
_LOCK_TIMEOUT_SECONDS = 10.0


class DiscoveryStoreLockTimeout(TimeoutError):
    """Raised when the discovery sources store lock cannot be acquired in time."""


def _effective_path(path: Path | None) -> Path:
    return path if path is not None else DISCOVERY_SOURCES_PATH


def _lock_path(store_path: Path) -> Path:
    return store_path.with_suffix(".lock")


def _load_store(store_path: Path) -> dict[str, Any]:
    if not store_path.exists():
        return {"version": _VERSION, "sources": []}
    try:
        text = store_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (json.JSONDecodeError, OSError):
        return {"version": _VERSION, "sources": []}
    if not isinstance(data, dict) or "sources" not in data:
        return {"version": _VERSION, "sources": []}
    return data


def _atomic_write(dest: Path, data: dict[str, Any]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2) + "\n"
    fd: int | None = None
    tmp_path_str: str | None = None
    try:
        fd, tmp_path_str = tempfile.mkstemp(
            dir=dest.parent,
            prefix=dest.name + ".tmp",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path_str, dest)
    except Exception:
        if tmp_path_str:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path_str)
        raise
    with contextlib.suppress(OSError):
        dest.chmod(0o600)


def list_sources(path: Path | None = None) -> list[dict[str, Any]]:
    """Return all stored source records."""
    store_path = _effective_path(path)
    data = _load_store(store_path)
    sources = data.get("sources", [])
    return [s for s in sources if isinstance(s, dict)]


def get_source(source_id: str, path: Path | None = None) -> dict[str, Any] | None:
    """Return the source record with the given ID, or None if not found."""
    for record in list_sources(path):
        if record.get("id") == source_id:
            return record
    return None


def upsert_source(record: dict[str, Any], path: Path | None = None) -> None:
    """Add or replace a source record by its ``id`` field using an atomic write."""
    store_path = _effective_path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(_lock_path(store_path)), timeout=_LOCK_TIMEOUT_SECONDS)
    try:
        with lock:
            data = _load_store(store_path)
            sources: list[dict[str, Any]] = [
                s for s in data.get("sources", []) if s.get("id") != record.get("id")
            ]
            sources.append(record)
            data["sources"] = sources
            _atomic_write(store_path, data)
    except Timeout as exc:
        raise DiscoveryStoreLockTimeout(
            f"Discovery sources store locked: {_lock_path(store_path)}"
        ) from exc


def remove_source(source_id: str, path: Path | None = None) -> bool:
    """Remove the source with the given ID. Returns True if a record was removed."""
    store_path = _effective_path(path)
    if not store_path.exists():
        return False
    store_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(_lock_path(store_path)), timeout=_LOCK_TIMEOUT_SECONDS)
    try:
        with lock:
            data = _load_store(store_path)
            before = len(data.get("sources", []))
            data["sources"] = [s for s in data.get("sources", []) if s.get("id") != source_id]
            after = len(data["sources"])
            if after < before:
                _atomic_write(store_path, data)
                return True
            return False
    except Timeout as exc:
        raise DiscoveryStoreLockTimeout(
            f"Discovery sources store locked: {_lock_path(store_path)}"
        ) from exc


def new_source_id(prefix: str = "src") -> str:
    """Return a short unique source ID with the given prefix."""
    return f"{prefix}_{uuid4().hex[:8]}"


def utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string ending in Z."""
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
