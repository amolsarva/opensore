from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.discovery.models import DiscoveryEvidenceRow, DiscoveryHitReportRow
from app.services.google_drive_csv import GoogleDriveCsvExporter


def test_exporter_requires_configuration() -> None:
    exporter = GoogleDriveCsvExporter(folder_id="")

    result = exporter.export_rows(filename="matter", rows=[])

    assert result["success"] is False
    assert "not configured" in result["error"]


def test_export_rows_uploads_in_memory_csv() -> None:
    drive_service = MagicMock()
    files = MagicMock()
    create = MagicMock()
    drive_service.files.return_value = files
    files.create.return_value = create
    create.execute.return_value = {
        "id": "file-123",
        "name": "matter.csv",
        "webViewLink": "https://drive.google.com/file/d/file-123/view",
    }

    media_cls = MagicMock(return_value="media")
    exporter = GoogleDriveCsvExporter(folder_id="folder-1", drive_service=drive_service)
    rows = [
        DiscoveryEvidenceRow(
            matter_title="Matter",
            source="slack",
            custodian="ceo@example.com",
            matched_keyword="complaint",
            context_excerpt="employee complaint context",
        )
    ]

    with patch("importlib.import_module") as import_module:
        import_module.return_value = MagicMock(MediaIoBaseUpload=media_cls)
        result = exporter.export_rows(filename="matter", rows=rows)

    assert result["success"] is True
    assert result["file_id"] == "file-123"
    assert result["row_count"] == 1
    files.create.assert_called_once()
    call_kwargs = files.create.call_args.kwargs
    assert call_kwargs["body"]["parents"] == ["folder-1"]
    assert call_kwargs["body"]["name"] == "matter.csv"
    assert call_kwargs["media_body"] == "media"
    assert media_cls.call_args.kwargs["mimetype"] == "text/csv"
    assert media_cls.call_args.kwargs["resumable"] is True
    assert "no local evidence file" in result["retention_mode"]


def test_export_package_uploads_evidence_hit_report_and_manifest_from_memory() -> None:
    drive_service = MagicMock()
    files = MagicMock()
    drive_service.files.return_value = files
    files.create.return_value.execute.side_effect = [
        {"id": "evidence-id", "name": "matter_evidence.csv"},
        {"id": "hits-id", "name": "matter_hit_report.csv"},
        {"id": "manifest-id", "name": "matter_manifest.json"},
    ]

    media_cls = MagicMock(return_value="media")
    exporter = GoogleDriveCsvExporter(folder_id="folder-1", drive_service=drive_service)

    with patch("importlib.import_module") as import_module:
        import_module.return_value = MagicMock(MediaIoBaseUpload=media_cls)
        result = exporter.export_package(
            basename="matter",
            evidence_rows=[
                DiscoveryEvidenceRow(
                    matter_title="Matter",
                    source="gmail",
                    matched_keyword="complaint",
                    context_excerpt="complaint context",
                )
            ],
            hit_report_rows=[
                DiscoveryHitReportRow(
                    source="gmail",
                    matched_keyword_set="terms",
                    matched_keyword="complaint",
                    hit_count=1,
                )
            ],
            manifest={"title": "Matter", "row_count": 1},
        )

    assert result["success"] is True
    assert result["row_count"] == 1
    assert [artifact["type"] for artifact in result["artifacts"]] == [
        "evidence_csv",
        "hit_report_csv",
        "manifest_json",
    ]
    assert files.create.call_count == 3
    uploaded_names = [call.kwargs["body"]["name"] for call in files.create.call_args_list]
    assert uploaded_names == [
        "matter_evidence.csv",
        "matter_hit_report.csv",
        "matter_manifest.json",
    ]
    assert "no local evidence files" in result["retention_mode"]


def test_upload_text_artifact_retries_transient_drive_errors() -> None:
    class DriveError(Exception):
        def __init__(self, status: int) -> None:
            super().__init__(f"status {status}")
            self.resp = type("Response", (), {"status": status})()

    drive_service = MagicMock()
    files = MagicMock()
    drive_service.files.return_value = files
    files.create.return_value.execute.side_effect = [
        DriveError(503),
        {"id": "manifest-id", "name": "manifest.json"},
    ]

    exporter = GoogleDriveCsvExporter(folder_id="folder-1", drive_service=drive_service)
    media_cls = MagicMock(return_value="media")

    with patch("importlib.import_module") as import_module:
        import_module.return_value = MagicMock(MediaIoBaseUpload=media_cls)
        result = exporter.upload_text_artifact(
            filename="manifest.json",
            body='{"ok": true}',
            mimetype="application/json",
            retry_attempts=2,
        )

    assert result["success"] is True
    assert result["file_id"] == "manifest-id"
    assert files.create.call_count == 2
