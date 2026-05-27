"""macOS recent files tool — Downloads folder, AirDrop cache, and NSRecentDocuments."""

from __future__ import annotations

from typing import Any

from app.services.macos_device.client import read_recent_files
from app.tools.base import BaseTool


class MacOSRecentFilesTool(BaseTool):
    """List recently accessed files from a macOS device.

    Reads the Downloads folder, AirDrop cache, and NSRecentDocuments
    shared file list. No special permissions required for Downloads;
    Full Disk Access may be needed for some paths.
    """

    name = "read_macos_recent_files"
    source = "local_device"
    description = (
        "List recently accessed and downloaded files on a macOS device including the Downloads "
        "folder, AirDrop received items, and the NSRecentDocuments list. Useful for identifying "
        "data exfiltration artifacts or recently handled sensitive documents."
    )
    use_cases = [
        "Identifying files recently downloaded to a device during a data exfiltration investigation",
        "Finding AirDrop received items that may contain improperly transferred documents",
        "Documenting recently opened files as part of a device audit",
        "Establishing a timeline of file activity around a specific incident date",
        "Checking for suspicious executable downloads or installer packages",
    ]
    input_schema = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of recent files to return (default: 50).",
                "default": 50,
            },
        },
    }
    outputs = {
        "available": "Whether the tool could read recent file information",
        "files": "List of recent file entries with source, path, name, size_bytes, modified_at",
        "total": "Total files returned",
    }

    def is_available(self, _sources: dict) -> bool:
        return True

    def extract_params(self, _sources: dict) -> dict[str, Any]:
        return {"limit": 50}

    def run(
        self,
        limit: int = 50,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        try:
            files = read_recent_files(limit=limit)
            return {
                "source": "local_device",
                "available": True,
                "files": files,
                "total": len(files),
            }
        except Exception as exc:
            return {"source": "local_device", "available": False, "error": str(exc)}


read_macos_recent_files = MacOSRecentFilesTool()
