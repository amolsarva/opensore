"""In-memory Google Drive CSV export for discovery investigations."""

from __future__ import annotations

import csv
import importlib
import io
import json
import logging
from pathlib import Path
from typing import Any, cast

from app.discovery.models import (
    DiscoveryEvidenceRow,
    DiscoveryHitReportRow,
    discovery_evidence_csv,
)

logger = logging.getLogger(__name__)

DISCOVERY_DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.file",)
_TRANSIENT_DRIVE_STATUSES = {429, 500, 502, 503, 504}


def _drive_status(exc: Exception) -> int | None:
    if not hasattr(exc, "resp"):
        return None
    status = getattr(exc.resp, "status", None)
    if isinstance(status, int):
        return status
    return None


def _handle_drive_error(exc: Exception, operation: str) -> dict[str, Any]:
    message = str(exc)
    if status_code := _drive_status(exc):
        if status_code == 401:
            message = f"Google Drive authentication failed while {operation}."
        elif status_code == 403:
            message = f"Google Drive permission denied while {operation}."
        elif status_code == 404:
            message = f"Google Drive folder not found while {operation}."
        else:
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
        retry_attempts: int = 1,
    ) -> dict[str, Any]:
        """Upload rows as a CSV file to the configured Drive folder.

        The CSV bytes are built in memory and passed directly to the Drive API.
        No temporary evidence file is written to the OpenSore host.
        """

        csv_text = discovery_evidence_csv(rows)
        artifact_name = filename if filename.endswith(".csv") else f"{filename}.csv"
        result = self.upload_text_artifact(
            filename=artifact_name,
            body=csv_text,
            mimetype="text/csv",
            retry_attempts=retry_attempts,
        )
        if result.get("success"):
            result["row_count"] = len(rows)
            result["retention_mode"] = "in-memory CSV upload; no local evidence file written"
        return result

    def export_package(
        self,
        *,
        basename: str,
        evidence_rows: list[DiscoveryEvidenceRow],
        hit_report_rows: list[DiscoveryHitReportRow],
        manifest: dict[str, Any],
        retry_attempts: int = 1,
    ) -> dict[str, Any]:
        """Upload a complete discovery package to Drive without local artifact files."""

        artifacts: list[dict[str, Any]] = []
        uploads = [
            (
                "evidence_csv",
                f"{basename}_evidence.csv",
                discovery_evidence_csv(evidence_rows),
                "text/csv",
            ),
            (
                "hit_report_csv",
                f"{basename}_hit_report.csv",
                _hit_report_csv(hit_report_rows),
                "text/csv",
            ),
            (
                "manifest_json",
                f"{basename}_manifest.json",
                f"{json_dumps(manifest)}\n",
                "application/json",
            ),
        ]

        for artifact_type, filename, body, mimetype in uploads:
            result = self.upload_text_artifact(
                filename=filename,
                body=body,
                mimetype=mimetype,
                retry_attempts=retry_attempts,
            )
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Google Drive package export failed."),
                    "failed_artifact": artifact_type,
                    "artifacts": artifacts,
                    "retention_mode": "in-memory artifact upload; no local evidence files written",
                }
            artifacts.append({"type": artifact_type, **result})

        return {
            "success": True,
            "artifacts": artifacts,
            "row_count": len(evidence_rows),
            "retention_mode": "in-memory artifact upload; no local evidence files written",
        }

    def upload_text_artifact(
        self,
        *,
        filename: str,
        body: str,
        mimetype: str,
        retry_attempts: int = 1,
    ) -> dict[str, Any]:
        """Upload one text artifact to Drive from memory with transient retry semantics."""

        if not self.is_configured:
            return {
                "success": False,
                "error": "Google Drive CSV export is not configured.",
            }

        attempts = max(1, retry_attempts)
        try:
            googleapiclient_http = cast(Any, importlib.import_module("googleapiclient.http"))
            drive_service = self._get_drive_service()
            metadata = {
                "name": filename,
                "mimeType": mimetype,
                "parents": [self.folder_id],
            }
            created: dict[str, Any] = {}
            for attempt in range(1, attempts + 1):
                media = googleapiclient_http.MediaIoBaseUpload(
                    io.BytesIO(body.encode("utf-8")),
                    mimetype=mimetype,
                    resumable=True,
                )
                try:
                    created = (
                        drive_service.files()
                        .create(
                            body=metadata,
                            media_body=media,
                            fields="id,name,webViewLink",
                        )
                        .execute()
                    )
                    break
                except Exception as exc:
                    if attempt >= attempts or _drive_status(exc) not in _TRANSIENT_DRIVE_STATUSES:
                        raise
                    logger.warning(
                        "Retrying Google Drive artifact upload after transient failure: %s",
                        exc,
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
                "mimetype": mimetype,
                "byte_count": len(body.encode("utf-8")),
            }
        except Exception as exc:
            return _handle_drive_error(exc, "uploading discovery artifact")


def _hit_report_csv(rows: list[DiscoveryHitReportRow]) -> str:
    output = io.StringIO()
    fieldnames = ["source", "custodian", "matched_keyword_set", "matched_keyword", "hit_count"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row.model_dump(mode="json"))
    return output.getvalue()


def json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True)
