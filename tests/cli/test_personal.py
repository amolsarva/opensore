"""Tests for personal-agent setup helpers."""

from __future__ import annotations

import json
from importlib import import_module

from click.testing import CliRunner

from app.cli.commands.personal import personal

personal_module = import_module("app.cli.commands.personal")


def test_personal_doctor_json_reports_expected_checks(monkeypatch) -> None:
    monkeypatch.setattr(
        personal_module,
        "_personal_checks",
        lambda: {
            "mac": {"status": "ok", "detail": "macOS"},
            "llm": {"status": "missing", "detail": "missing key"},
        },
    )

    result = CliRunner().invoke(personal, ["doctor", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["mac"]["status"] == "ok"
    assert data["llm"]["detail"] == "missing key"


def test_personal_plan_prints_gateway_goal() -> None:
    result = CliRunner().invoke(personal, ["plan"])

    assert result.exit_code == 0
    assert "OpenClaw-style gateway" in result.output
