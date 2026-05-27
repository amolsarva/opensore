"""macOS browser history tool — reads Safari, Chrome, and Firefox history from local SQLite databases."""

from __future__ import annotations

from typing import Any

from app.services.macos_device.client import (
    read_chrome_history,
    read_firefox_history,
    read_safari_history,
)
from app.tools.base import BaseTool


class MacOSBrowserHistoryTool(BaseTool):
    """Read local macOS browser history for Safari, Chrome, and Firefox.

    Queries the SQLite history databases stored on disk. Requires Full Disk
    Access permission in System Settings → Privacy & Security for the terminal
    app. All access is read-only; source databases are never modified.
    """

    name = "read_macos_browser_history"
    source = "local_device"
    description = (
        "Read local macOS browser history from Safari, Chrome, and Firefox for HR/legal "
        "forensics. Returns visited URLs, page titles, and timestamps. Requires Full Disk "
        "Access in System Settings. Read-only; does not modify history databases."
    )
    use_cases = [
        "Finding evidence of communications with a specific domain (e.g., personal email, social media)",
        "Identifying when a subject visited a job-listing or competitor site before resignation",
        "Verifying whether an employee accessed prohibited or policy-violating websites",
        "Correlating browser activity timestamps with other evidence in an investigation",
        "Documenting web-based exfiltration activity (cloud storage uploads, file sharing)",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "browsers": {
                "type": "array",
                "items": {"type": "string", "enum": ["safari", "chrome", "firefox", "all"]},
                "description": "Which browsers to query. Defaults to all installed browsers.",
                "default": ["all"],
            },
            "domain_filter": {
                "type": "string",
                "description": "If provided, only return history entries whose URL contains this string.",
            },
            "after_iso": {
                "type": "string",
                "description": "ISO-8601 datetime; only return visits after this time (e.g. 2024-01-01T00:00:00Z).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of history entries to return per browser (default: 200).",
                "default": 200,
            },
        },
    }
    outputs = {
        "available": "Whether the tool could read at least one browser database",
        "entries": "List of history entries with browser, url, title, visited_at",
        "browser_counts": "Number of entries returned per browser",
        "total": "Total entries returned across all browsers",
    }

    def is_available(self, _sources: dict) -> bool:
        return True

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {"browsers": ["all"], "limit": 200}

    def run(
        self,
        browsers: list[str] | None = None,
        domain_filter: str | None = None,
        after_iso: str | None = None,
        limit: int = 200,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        browsers = browsers or ["all"]
        want_all = "all" in browsers

        entries: list[dict[str, Any]] = []
        counts: dict[str, int] = {}

        try:
            if want_all or "safari" in browsers:
                rows = read_safari_history(limit=limit, domain_filter=domain_filter, after_iso=after_iso)
                entries.extend(rows)
                counts["safari"] = len(rows)

            if want_all or "chrome" in browsers:
                rows = read_chrome_history(limit=limit, domain_filter=domain_filter, after_iso=after_iso)
                entries.extend(rows)
                counts["chrome"] = len(rows)

            if want_all or "firefox" in browsers:
                rows = read_firefox_history(limit=limit, domain_filter=domain_filter, after_iso=after_iso)
                entries.extend(rows)
                counts["firefox"] = len(rows)

            entries.sort(key=lambda e: e.get("visited_at", ""), reverse=True)

            return {
                "source": "local_device",
                "available": True,
                "entries": entries[:limit],
                "browser_counts": counts,
                "total": len(entries),
                "note": "Requires Full Disk Access in System Settings → Privacy & Security.",
            }
        except Exception as exc:
            return {"source": "local_device", "available": False, "error": str(exc)}


read_macos_browser_history = MacOSBrowserHistoryTool()
