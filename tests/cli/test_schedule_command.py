"""Tests for the opensore schedule CLI commands."""

from __future__ import annotations

import pathlib

import pytest
from click.testing import CliRunner

from app.cli.commands.schedule import (
    add_schedule_command,
    list_schedules_command,
    remove_schedule_command,
    run_schedules_command,
)


@pytest.fixture()
def schedules_path(tmp_path: pathlib.Path, monkeypatch):
    import sys

    import app.cli.commands.schedule  # noqa: F401 — ensure submodule is in sys.modules

    # Use sys.modules to get the actual module, not the Click Group attribute
    # that __init__.py shadows the submodule name with.
    schedule_mod = sys.modules["app.cli.commands.schedule"]
    target = tmp_path / ".opensore" / "schedules.yaml"
    monkeypatch.setattr(schedule_mod, "_SCHEDULES_PATH", target)
    return target


def test_list_empty(schedules_path) -> None:
    runner = CliRunner()
    result = runner.invoke(list_schedules_command)
    assert result.exit_code == 0
    assert "No schedules" in result.output


def test_add_and_list(schedules_path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        add_schedule_command,
        ["--name", "HighDBLatency", "--service", "payments", "--interval", "15"],
    )
    assert result.exit_code == 0
    assert "Added" in result.output

    result2 = runner.invoke(list_schedules_command)
    assert "HighDBLatency" in result2.output
    assert "15" in result2.output


def test_add_duplicate_warns(schedules_path) -> None:
    runner = CliRunner()
    runner.invoke(add_schedule_command, ["--name", "DupeAlert"])
    result = runner.invoke(add_schedule_command, ["--name", "DupeAlert"])
    assert result.exit_code == 0
    assert "already exists" in result.output


def test_remove_existing(schedules_path) -> None:
    runner = CliRunner()
    runner.invoke(add_schedule_command, ["--name", "ToRemove"])
    result = runner.invoke(remove_schedule_command, ["ToRemove"])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_remove_nonexistent_exits_1(schedules_path) -> None:
    runner = CliRunner()
    result = runner.invoke(remove_schedule_command, ["NoSuchAlert"])
    assert result.exit_code == 1


def test_dry_run_does_not_modify_last_run(schedules_path) -> None:
    runner = CliRunner()
    runner.invoke(add_schedule_command, ["--name", "DryProbe", "--service", "api"])

    result = runner.invoke(run_schedules_command, ["--dry-run"])
    assert result.exit_code == 0
    assert "would investigate" in result.output

    # last_run should still be null
    import sys

    schedule_mod = sys.modules["app.cli.commands.schedule"]
    entries = schedule_mod._load_schedules()
    entry = next((e for e in entries if e["name"] == "DryProbe"), None)
    assert entry is not None
    assert entry.get("last_run") is None


def test_run_no_due_probes(schedules_path) -> None:
    import sys
    from datetime import UTC, datetime

    schedule_mod = sys.modules["app.cli.commands.schedule"]
    runner = CliRunner()
    runner.invoke(add_schedule_command, ["--name", "RecentlyRun", "--interval", "60"])

    # Mark as just-run using the patched path
    entries = schedule_mod._load_schedules()
    for e in entries:
        if e["name"] == "RecentlyRun":
            e["last_run"] = datetime.now(UTC).isoformat()
    schedule_mod._save_schedules(entries)

    result = runner.invoke(run_schedules_command)
    assert "No probes are due" in result.output


def test_run_disabled_schedule_skipped(schedules_path) -> None:
    runner = CliRunner()
    runner.invoke(add_schedule_command, ["--name", "DisabledProbe", "--disabled"])

    result = runner.invoke(run_schedules_command)
    assert result.exit_code == 0
    assert "No probes are due" in result.output
