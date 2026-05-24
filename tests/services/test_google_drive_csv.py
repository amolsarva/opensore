from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.discovery.models import DiscoveryEvidenceRow
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
    assert "no local evidence file" in result["retention_mode"]
