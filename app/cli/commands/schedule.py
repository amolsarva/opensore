"""``opensore schedule`` — manage periodic investigation probes.

Schedules are stored in ~/.opensore/schedules.yaml as a list of probe configs:

    - name: HighDBLatency
      service: payments-api
      severity: warning
      interval_minutes: 15
      description: Periodic DB latency health probe
      enabled: true
      last_run: null

``opensore schedule run`` loads all enabled entries and runs any that are due,
then updates ``last_run`` in the YAML. Designed to be invoked from a cron job:

    */15 * * * * opensore schedule run --quiet
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from typing import Any

import click
import yaml
from rich.console import Console
from rich.table import Table

console = Console()

_SCHEDULES_PATH = pathlib.Path.home() / ".opensore" / "schedules.yaml"


def _load_schedules() -> list[dict[str, Any]]:
    if not _SCHEDULES_PATH.exists():
        return []
    try:
        data = yaml.safe_load(_SCHEDULES_PATH.read_text(encoding="utf-8"))
        return list(data) if isinstance(data, list) else []
    except Exception:
        return []


def _save_schedules(schedules: list[dict[str, Any]]) -> None:
    _SCHEDULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SCHEDULES_PATH.write_text(
        yaml.dump(schedules, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def _is_due(entry: dict[str, Any]) -> bool:
    interval_minutes = int(entry.get("interval_minutes") or 60)
    last_run_str = entry.get("last_run")
    if not last_run_str:
        return True
    try:
        last_run = datetime.fromisoformat(str(last_run_str))
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - last_run).total_seconds() / 60
        return elapsed >= interval_minutes
    except Exception:
        return True


@click.group(name="schedule")
def schedule() -> None:
    """Manage periodic investigation probes."""


@schedule.command(name="list")
def list_schedules_command() -> None:
    """List all configured investigation schedules."""
    entries = _load_schedules()
    if not entries:
        console.print(
            "[dim]No schedules configured. Use [cyan]opensore schedule add[/cyan] to create one.[/dim]"
        )
        return

    table = Table(title="Investigation Schedules", show_lines=False, expand=True)
    table.add_column("Name", style="cyan")
    table.add_column("Service", style="white")
    table.add_column("Interval", justify="right", style="green")
    table.add_column("Enabled", justify="center")
    table.add_column("Last Run", style="dim")

    for entry in entries:
        last = str(entry.get("last_run") or "never")[:19].replace("T", " ")
        enabled = "[green]✓[/green]" if entry.get("enabled", True) else "[red]✗[/red]"
        table.add_row(
            entry.get("name", ""),
            entry.get("service", ""),
            f"{entry.get('interval_minutes', 60)}m",
            enabled,
            last,
        )
    console.print(table)


@schedule.command(name="add")
@click.option("--name", required=True, help="Alert name to probe (e.g. HighMemoryUsage).")
@click.option("--service", default="", help="Service name for context.")
@click.option("--severity", default="warning", help="Alert severity.")
@click.option(
    "--interval",
    "interval_minutes",
    default=60,
    show_default=True,
    help="Check interval in minutes.",
)
@click.option("--description", default="", help="Description of what this probe checks.")
@click.option("--disabled", is_flag=True, help="Add schedule in disabled state.")
def add_schedule_command(
    name: str,
    service: str,
    severity: str,
    interval_minutes: int,
    description: str,
    disabled: bool,
) -> None:
    """Add a periodic investigation probe to the schedule."""
    entries = _load_schedules()
    for entry in entries:
        if entry.get("name") == name:
            console.print(
                f"[yellow]Schedule '{name}' already exists. Use [cyan]opensore schedule edit[/cyan] to update it.[/yellow]"
            )
            return

    entries.append(
        {
            "name": name,
            "service": service,
            "severity": severity,
            "interval_minutes": interval_minutes,
            "description": description,
            "enabled": not disabled,
            "last_run": None,
        }
    )
    _save_schedules(entries)
    console.print(f"[green]Added schedule: {name} (every {interval_minutes}m)[/green]")


@schedule.command(name="remove")
@click.argument("name")
def remove_schedule_command(name: str) -> None:
    """Remove a schedule by alert name."""
    entries = _load_schedules()
    before = len(entries)
    entries = [e for e in entries if e.get("name") != name]
    if len(entries) == before:
        console.print(f"[red]No schedule named '{name}' found.[/red]")
        raise SystemExit(1)
    _save_schedules(entries)
    console.print(f"[green]Removed schedule: {name}[/green]")


@schedule.command(name="enable")
@click.argument("name")
@click.option("--disable", "enable", flag_value=False, help="Disable the schedule instead.")
@click.option("--enable", "enable", flag_value=True, default=True)
def toggle_schedule_command(name: str, enable: bool) -> None:
    """Enable or disable a schedule."""
    entries = _load_schedules()
    for entry in entries:
        if entry.get("name") == name:
            entry["enabled"] = enable
            _save_schedules(entries)
            state = "enabled" if enable else "disabled"
            console.print(f"[green]Schedule '{name}' {state}.[/green]")
            return
    console.print(f"[red]No schedule named '{name}' found.[/red]")
    raise SystemExit(1)


@schedule.command(name="run")
@click.option("--dry-run", is_flag=True, help="Show which probes would fire without running them.")
@click.option("--quiet", is_flag=True, help="Suppress output (suitable for cron).")
@click.option("--force", is_flag=True, help="Run all enabled probes regardless of interval.")
def run_schedules_command(dry_run: bool, quiet: bool, force: bool) -> None:
    """Run all due investigation probes.

    Designed to be called from a cron job:

        */15 * * * * opensore schedule run --quiet
    """
    entries = _load_schedules()
    due = [e for e in entries if e.get("enabled", True) and (force or _is_due(e))]

    if not due:
        if not quiet:
            console.print("[dim]No probes are due.[/dim]")
        return

    if not quiet:
        console.print(f"Running {len(due)} probe(s)…")

    from app.pipeline.pipeline import run_investigation
    from app.state import make_initial_state

    for entry in due:
        name = entry.get("name", "Probe")
        service = entry.get("service", "")
        severity = entry.get("severity", "warning")
        description = entry.get("description", "")

        raw_alert: dict[str, Any] = {
            "name": name,
            "service": service,
            "severity": severity,
            "description": description or f"Scheduled probe: {name}",
            "source": "schedule",
        }

        if dry_run:
            if not quiet:
                console.print(f"  [dim][dry-run] would investigate: {name}[/dim]")
            continue

        try:
            state = make_initial_state(raw_alert)
            result = run_investigation(state)
            root_cause = str(result.get("root_cause") or "")
            entry["last_run"] = datetime.now(UTC).isoformat()
            if not quiet:
                console.print(
                    f"  [green]✓[/green] {name}: {root_cause[:80] or 'investigation complete'}"
                )
        except Exception as exc:
            if not quiet:
                console.print(f"  [red]✗[/red] {name}: {exc}")

    if not dry_run:
        _save_schedules(entries)
        if not quiet:
            console.print(f"[dim]Updated last_run for {len(due)} probe(s).[/dim]")
