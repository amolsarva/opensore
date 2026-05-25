"""Tests for discovery source connectors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.discovery.connectors.custom_csv import CustomCsvConnector
from app.discovery.connectors.slack import SlackConnector


def test_custom_csv_connector_verify_nonexistent(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.csv"
    connector = CustomCsvConnector(missing)
    assert connector.verify() is False


def test_custom_csv_connector_verify_existing(tmp_path: Path) -> None:
    csv_file = tmp_path / "export.csv"
    csv_file.write_text("id,body\n1,hello\n", encoding="utf-8")
    connector = CustomCsvConnector(csv_file)
    assert connector.verify() is True


def test_google_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENSORE_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("OPENSORE_GOOGLE_CLIENT_SECRET", raising=False)

    from app.discovery.connectors.google_workspace import run_google_oauth

    with pytest.raises(RuntimeError, match="OPENSORE_GOOGLE_CLIENT_ID"):
        run_google_oauth()


def test_slack_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENSORE_SLACK_CLIENT_ID", raising=False)
    monkeypatch.delenv("OPENSORE_SLACK_CLIENT_SECRET", raising=False)

    from app.discovery.connectors.slack import run_slack_oauth

    with pytest.raises(RuntimeError, match="OPENSORE_SLACK_CLIENT_ID"):
        run_slack_oauth()


def test_slack_connector_verify_ok() -> None:
    record = {
        "id": "sl_test1234",
        "kind": "slack",
        "label": "Acme (alice)",
        "authed_user_token": "xoxp-fake-token",
    }
    connector = SlackConnector(record)
    mock_response = MagicMock()
    mock_response.get = MagicMock(
        side_effect=lambda key, default=None: True if key == "ok" else default
    )
    with patch.object(connector._client, "auth_test", return_value=mock_response):
        assert connector.verify() is True


def test_slack_connector_verify_fail() -> None:
    record = {
        "id": "sl_test5678",
        "kind": "slack",
        "label": "Acme (bob)",
        "authed_user_token": "xoxp-expired-token",
    }
    connector = SlackConnector(record)
    with patch.object(connector._client, "auth_test", side_effect=Exception("auth failed")):
        assert connector.verify() is False
