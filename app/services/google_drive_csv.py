"""In-memory Google Drive CSV export for discovery investigations."""

from __future__ import annotations

import importlib
import io
import logging
from pathlib import Path
from typing import Any, cast

from app.discovery.models import DiscoveryEvidenceRow, discovery_evidence_csv

logger = logging.getLogger(__name__)

DISCOVERY_DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.file",)


def _handle_drive_error(exc: Exception, operation: str) -> dict[str, Any]:
    message = str(exc)
    if hasattr(exc, "resp"):
        status_code = getattr(exc.resp, "status", None)
        if status_code == 401:
            message = f"Google Drive authentication failed while {operation}."
        elif status_code == 403:
            message = f"Google Drive permission denied while {operation}."
        elif status_code == 404:
            message = f"Google Drive folder not found while {operation}."
        elif status_code:
            message = f"Google Drive HTTP {status_code} while {operation}: {exc}"
    logger.error("Google Drive CSV export error during %s: %s", operation, exc)
    return {"success": False, "error": message}


class GoogleDriveCsvExporter:
    """Write discovery CSV artifacts to Google Drive without local files."""

    def __init__(
        self,
        *,
        folder_id: str,
        credentials_file: str = "",
        credentials: Any | None = None,
        drive_service: Any | None = None,
    ) -> None:
        self.folder_id = folder_id.strip()
        self.credentials_file = credentials_file.strip()
        self.credentials = credentials
        self._drive_service = drive_service

    @property
    def is_configured(self) -> bool:
        if not self.folder_id:
            return False
        if self._drive_service is not None or self.credentials is not None:
            return True
        return bool(self.credentials_file and Path(self.credentials_file).exists())

    def _get_drive_service(self) -> Any:
        if self._drive_service is not None:
            return self._drive_service

        googleapiclient_discovery = cast(
            Any,
            importlib.import_module("googleapiclient.discovery"),
        )
        if self.credentials is not None:
            credentials = self.credentials
        else:
            service_account = cast(Any, importlib.import_module("google.oauth2.service_account"))
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=list(DISCOVERY_DRIVE_SCOPES),
            )

        self._drive_service = googleapiclient_discovery.build(
            "drive",
            "v3",
            credentials=credentials,
        )
        return self._drive_service

    def export_rows(
        self,
        *,
        filename: str,
        rows: list[DiscoveryEvidenceRow],
    ) -> dict[str, Any]:
        """Upload rows as a CSV file to the configured Drive folder.

        The CSV bytes are built in memory and passed directly to the Drive API.
        No temporary evidence file is written to the OpenSRE host.
        """

        if not self.is_configured:
            return {
                "success": False,
                "error": "Google Drive CSV export is not configured.",
            }

        try:
            googleapiclient_http = cast(Any, importlib.import_module("googleapiclient.http"))
            drive_service = self._get_drive_service()
            csv_text = discovery_evidence_csv(rows)
            media = googleapiclient_http.MediaIoBaseUpload(
                io.BytesIO(csv_text.encode("utf-8")),
                mimetype="text/csv",
                resumable=False,
            )
            metadata = {
                "name": filename if filename.endswith(".csv") else f"{filename}.csv",
                "mimeType": "text/csv",
                "parents": [self.folder_id],
            }
            created = (
                drive_service.files()
                .create(
                    body=metadata,
                    media_body=media,
                    fields="id,name,webViewLink",
                )
                .execute()
            )
            file_id = created.get("id", "")
            return {
                "success": True,
                "file_id": file_id,
                "name": created.get("name", metadata["name"]),
                "web_url": created.get(
                    "webViewLink",
                    f"https://drive.google.com/file/d/{file_id}/view" if file_id else "",
                ),
                "row_count": len(rows),
                "retention_mode": "in-memory CSV upload; no local evidence file written",
            }
        except Exception as exc:
            return _handle_drive_error(exc, "uploading discovery CSV")
