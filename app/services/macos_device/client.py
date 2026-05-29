"""macOS local device forensics client.

Reads local artifacts that macOS stores on disk:
  - Browser history: Safari, Chrome, Firefox (SQLite databases)
  - iMessage history: ~/Library/Messages/chat.db (SQLite)
  - Keychain credentials: via the macOS ``security`` CLI (always prompts user)
  - Recent files: NSRecentDocumentsDictionary, Downloads, AirDrop

All SQLite access is read-only and never modifies the source databases.
Keychain access is deliberately gated behind macOS system prompts — no
silent credential extraction is possible or attempted.

NOTE: On macOS, Full Disk Access must be granted to the running terminal
application for SQLite access to browser databases to succeed.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _home() -> Path:
    return Path.home()


def _webkit_ts_to_iso(webkit_ts: float) -> str:
    """Convert WebKit/Safari timestamp (seconds since 2001-01-01) to ISO-8601."""
    epoch_offset = 978307200  # seconds between 1970-01-01 and 2001-01-01
    unix_ts = webkit_ts + epoch_offset
    return datetime.fromtimestamp(unix_ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chrome_ts_to_iso(chrome_ts: int) -> str:
    """Convert Chrome timestamp (microseconds since 1601-01-01) to ISO-8601."""
    epoch_offset = 11644473600  # seconds between 1601-01-01 and 1970-01-01
    unix_ts = chrome_ts / 1_000_000 - epoch_offset
    return datetime.fromtimestamp(unix_ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unix_us_to_iso(unix_us: int) -> str:
    """Convert Unix timestamp in microseconds to ISO-8601."""
    return datetime.fromtimestamp(unix_us / 1_000_000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _copy_db(path: Path) -> Path | None:
    """Copy a locked SQLite database to a temp file so we can read it safely.

    Returns the temp path, or None if the source does not exist.
    """
    if not path.exists():
        return None
    tmp = path.parent / (path.name + ".opensore_tmp")
    try:
        shutil.copy2(str(path), str(tmp))
        return tmp
    except (PermissionError, OSError):
        return None


def _safe_query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    """Run a read-only SQLite query and return rows, or [] on any error."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            cur = con.execute(sql, params)
            return [tuple(row) for row in cur.fetchall()]
        finally:
            con.close()
    except sqlite3.OperationalError:
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Safari
# ---------------------------------------------------------------------------

SAFARI_DB = _home() / "Library" / "Safari" / "History.db"


def read_safari_history(
    limit: int = 200,
    domain_filter: str | None = None,
    after_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Read Safari browsing history from the local SQLite database."""
    tmp = _copy_db(SAFARI_DB)
    if tmp is None:
        return []
    try:
        sql = """
            SELECT hv.title, hi.url, hv.visit_time
            FROM history_visits hv
            JOIN history_items hi ON hv.history_item = hi.id
            ORDER BY hv.visit_time DESC
            LIMIT ?
        """
        rows = _safe_query(tmp, sql, (limit * 3,))  # over-fetch for filtering
        results: list[dict[str, Any]] = []
        for row in rows:
            title, url, webkit_ts = row
            ts = _webkit_ts_to_iso(webkit_ts)
            if after_iso and ts < after_iso:
                continue
            if domain_filter and domain_filter.lower() not in (url or "").lower():
                continue
            results.append({"browser": "safari", "url": url or "", "title": title or "", "visited_at": ts})
            if len(results) >= limit:
                break
        return results
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


# ---------------------------------------------------------------------------
# Chrome / Chromium
# ---------------------------------------------------------------------------

def _chrome_history_paths() -> list[Path]:
    """Return candidate Chrome/Chromium history database paths."""
    base = _home() / "Library" / "Application Support"
    candidates = [
        base / "Google" / "Chrome" / "Default" / "History",
        base / "Google" / "Chrome" / "Profile 1" / "History",
        base / "Chromium" / "Default" / "History",
        base / "BraveSoftware" / "Brave-Browser" / "Default" / "History",
        base / "Microsoft Edge" / "Default" / "History",
    ]
    return [p for p in candidates if p.exists()]


def read_chrome_history(
    limit: int = 200,
    domain_filter: str | None = None,
    after_iso: str | None = None,
    browser_hint: str = "chrome",
) -> list[dict[str, Any]]:
    """Read Chrome/Chromium-family browsing history."""
    results: list[dict[str, Any]] = []
    for db_path in _chrome_history_paths():
        tmp = _copy_db(db_path)
        if tmp is None:
            continue
        try:
            sql = """
                SELECT u.title, u.url, v.visit_time
                FROM visits v
                JOIN urls u ON v.url = u.id
                ORDER BY v.visit_time DESC
                LIMIT ?
            """
            rows = _safe_query(tmp, sql, (limit * 3,))
            for row in rows:
                title, url, chrome_ts = row
                ts = _chrome_ts_to_iso(chrome_ts)
                if after_iso and ts < after_iso:
                    continue
                if domain_filter and domain_filter.lower() not in (url or "").lower():
                    continue
                results.append({"browser": browser_hint, "url": url or "", "title": title or "", "visited_at": ts})
                if len(results) >= limit:
                    break
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        if len(results) >= limit:
            break
    return results


# ---------------------------------------------------------------------------
# Firefox
# ---------------------------------------------------------------------------

def _firefox_history_paths() -> list[Path]:
    profiles_root = _home() / "Library" / "Application Support" / "Firefox" / "Profiles"
    if not profiles_root.exists():
        return []
    return list(profiles_root.glob("*/places.sqlite"))


def read_firefox_history(
    limit: int = 200,
    domain_filter: str | None = None,
    after_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Read Firefox browsing history."""
    results: list[dict[str, Any]] = []
    for db_path in _firefox_history_paths():
        tmp = _copy_db(db_path)
        if tmp is None:
            continue
        try:
            sql = """
                SELECT p.title, p.url, h.visit_date
                FROM moz_historyvisits h
                JOIN moz_places p ON h.place_id = p.id
                ORDER BY h.visit_date DESC
                LIMIT ?
            """
            rows = _safe_query(tmp, sql, (limit * 3,))
            for row in rows:
                title, url, visit_us = row
                ts = _unix_us_to_iso(visit_us) if visit_us else ""
                if after_iso and ts < after_iso:
                    continue
                if domain_filter and domain_filter.lower() not in (url or "").lower():
                    continue
                results.append({"browser": "firefox", "url": url or "", "title": title or "", "visited_at": ts})
                if len(results) >= limit:
                    break
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        if len(results) >= limit:
            break
    return results


# ---------------------------------------------------------------------------
# iMessage / Messages
# ---------------------------------------------------------------------------

MESSAGES_DB = _home() / "Library" / "Messages" / "chat.db"


def read_messages_history(
    contact_filter: str | None = None,
    limit: int = 200,
    after_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Read iMessage / SMS history from chat.db."""
    tmp = _copy_db(MESSAGES_DB)
    if tmp is None:
        return []
    try:
        sql = """
            SELECT
                m.text,
                m.date,
                m.is_from_me,
                h.id AS contact_id,
                c.display_name AS chat_name,
                m.service
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN chat c ON c.ROWID = cmj.chat_id
            ORDER BY m.date DESC
            LIMIT ?
        """
        rows = _safe_query(tmp, sql, (limit * 3,))
        results: list[dict[str, Any]] = []
        for row in rows:
            text, apple_ts, is_from_me, contact_id, chat_name, service = row
            # Apple's Messages DB stores nanoseconds since 2001-01-01
            ts = _webkit_ts_to_iso(apple_ts / 1_000_000_000) if apple_ts else ""
            if after_iso and ts < after_iso:
                continue
            if contact_filter and contact_filter.lower() not in (contact_id or "").lower() and contact_filter.lower() not in (chat_name or "").lower():
                continue
            results.append({
                "text": (text or "").strip(),
                "timestamp": ts,
                "direction": "sent" if is_from_me else "received",
                "contact": contact_id or "",
                "chat_name": chat_name or "",
                "service": service or "iMessage",
            })
            if len(results) >= limit:
                break
        return results
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


# ---------------------------------------------------------------------------
# Keychain / security CLI
# ---------------------------------------------------------------------------

def is_macos() -> bool:
    return sys.platform == "darwin"


def keychain_find_generic(
    service: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """Look up a generic keychain entry via the macOS ``security`` CLI.

    This ALWAYS triggers a macOS system password prompt — there is no way to
    read keychain secrets silently. Returns metadata only; actual passwords
    are never returned in plaintext by this function (the security CLI prints
    them to stdout only after the user approves the prompt in the GUI dialog).

    Returns a dict with keys: found (bool), service, account, error.
    """
    if not is_macos() or not shutil.which("security"):
        return {"found": False, "error": "macOS security CLI not available on this platform"}
    cmd = ["security", "find-generic-password", "-g"]
    if service:
        cmd += ["-s", service]
    if account:
        cmd += ["-a", account]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            out = proc.stdout + proc.stderr
            found_service = re.search(r'"svce"<blob>="([^"]+)"', out)
            found_account = re.search(r'"acct"<blob>="([^"]+)"', out)
            return {
                "found": True,
                "service": found_service.group(1) if found_service else service or "",
                "account": found_account.group(1) if found_account else account or "",
                "note": "Password was shown in the macOS security prompt dialog.",
            }
        return {"found": False, "error": f"security CLI exited {proc.returncode}: {proc.stderr.strip()[:200]}"}
    except subprocess.TimeoutExpired:
        return {"found": False, "error": "Keychain prompt timed out (30s). User may have cancelled."}
    except Exception as exc:
        return {"found": False, "error": str(exc)}


def keychain_list_services() -> list[str]:
    """List unique service names in the default keychain (no password required)."""
    if not is_macos() or not shutil.which("security"):
        return []
    try:
        proc = subprocess.run(
            ["security", "dump-keychain"],
            capture_output=True, text=True, timeout=30,
        )
        services = re.findall(r'"svce"<blob>="([^"]+)"', proc.stdout + proc.stderr)
        return sorted(set(services))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Recent files
# ---------------------------------------------------------------------------

def read_recent_files(limit: int = 50) -> list[dict[str, Any]]:
    """Return recently accessed files from macOS NSRecentDocuments plist and Downloads."""
    results: list[dict[str, Any]] = []

    # Downloads folder — simple mtime sort
    downloads = _home() / "Downloads"
    if downloads.exists():
        try:
            items = sorted(downloads.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for item in items[:limit]:
                stat = item.stat()
                ts = datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                results.append({
                    "source": "downloads",
                    "path": str(item),
                    "name": item.name,
                    "size_bytes": stat.st_size,
                    "modified_at": ts,
                })
        except PermissionError:
            pass

    # AirDrop received items (stored in Downloads for most users, also check AirDrop cache)
    airdrop_cache = _home() / "Library" / "com.apple.nsurlsessiond" / "Downloads"
    if airdrop_cache.exists():
        try:
            for item in list(airdrop_cache.iterdir())[:limit]:
                if item.is_file():
                    stat = item.stat()
                    ts = datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                    results.append({
                        "source": "airdrop_cache",
                        "path": str(item),
                        "name": item.name,
                        "size_bytes": stat.st_size,
                        "modified_at": ts,
                    })
        except PermissionError:
            pass

    # NSRecentDocuments via plist (best-effort)
    plist_path = (
        _home() / "Library" / "Application Support" / "com.apple.sharedfilelist"
        / "com.apple.LSSharedFileList.RecentDocuments.sfl2"
    )
    if plist_path.exists() and is_macos() and shutil.which("plutil"):
        try:
            proc = subprocess.run(
                ["plutil", "-convert", "json", "-o", "-", str(plist_path)],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                for entry in (data.get("items") or [])[:limit]:
                    name = entry.get("Name") or entry.get("name") or ""
                    if name:
                        results.append({"source": "recent_documents", "name": name, "path": "", "modified_at": ""})
        except Exception:
            pass

    return results[:limit]
