"""Lightweight FastAPI smoke + telemetry coverage for ``app.webapp``."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import webapp


def test_webapp_module_calls_init_sentry_on_import(monkeypatch: pytest.MonkeyPatch) -> None:
    init_mock = MagicMock()
    monkeypatch.setattr("app.utils.sentry_sdk.init_sentry", init_mock)

    importlib.reload(webapp)

    init_mock.assert_called_once()


def test_health_response_returns_known_fields() -> None:
    response = webapp.get_health_response()

    assert hasattr(response, "ok")
    assert hasattr(response, "version")
    assert hasattr(response, "llm_configured")
    assert hasattr(response, "env")


def test_ok_route_is_registered() -> None:
    client = TestClient(webapp.app)
    resp = client.get("/ok")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "ok" in data
    assert "version" in data


def test_discovery_ui_route_is_registered() -> None:
    client = TestClient(webapp.app)
    resp = client.get("/ui")

    assert resp.status_code == 200
    assert "Workplace misconduct discovery" in resp.text


def test_discovery_preview_returns_no_retention_plan() -> None:
    client = TestClient(webapp.app)
    resp = client.post(
        "/api/discovery/investigations/preview",
        json={
            "title": "Executive complaint",
            "custodians": ["ceo@example.com"],
            "sources": [{"kind": "google_workspace", "label": "Google Workspace"}],
            "keyword_sets": [{"name": "terms", "terms": ["retaliation", "complaint"]}],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["keyword_count"] == 2
    assert data["export_target"] == "google_drive_csv"
    assert "no local evidence storage" in data["retention_mode"]


def test_discovery_preview_rejects_local_storage() -> None:
    client = TestClient(webapp.app)
    resp = client.post(
        "/api/discovery/investigations/preview",
        json={
            "title": "Executive complaint",
            "store_evidence_locally": True,
            "sources": [{"kind": "slack", "label": "Slack"}],
            "keyword_sets": [{"name": "terms", "terms": ["complaint"]}],
        },
    )

    assert resp.status_code == 422
