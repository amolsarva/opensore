"""Workplace discovery CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from app.discovery.connectors import get_connector, run_google_oauth, run_slack_oauth
from app.discovery.credentials import list_sources, remove_source, upsert_source
from app.discovery.models import build_discovery_plan
from app.discovery.runner import load_discovery_request, run_local_discovery


@click.group(name="discovery")
def discovery() -> None:
    """Plan and run workplace misconduct discovery searches."""


@discovery.command(name="plan")
@click.argument("config", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the JSON plan to a file instead of stdout.",
)
def discovery_plan(config: Path, output: Path | None) -> None:
    """Render a no-evidence discovery search plan from CONFIG."""

    request = load_discovery_request(config)
    plan = build_discovery_plan(request)
    payload = json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True)
    if output is None:
        click.echo(payload)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{payload}\n", encoding="utf-8")
    click.echo(f"Wrote discovery plan: {output}")


@discovery.command(name="run")
@click.argument("config", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--source",
    "sources",
    multiple=True,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="CSV, JSON, JSONL, or NDJSON export file to search. Repeat for multiple exports.",
)
@click.option(
    "--out",
    "output_dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory for evidence CSV, hit report, and manifest.",
)
def discovery_run(config: Path, sources: tuple[Path, ...], output_dir: Path) -> None:
    """Run deterministic local keyword discovery over exported source files."""

    request = load_discovery_request(config)
    manifest = run_local_discovery(
        request=request,
        source_paths=list(sources),
        output_dir=output_dir,
    )
    click.echo(f"Wrote evidence CSV: {manifest.evidence_file}")
    click.echo(f"Wrote hit report: {manifest.hit_report_file}")
    click.echo(f"Wrote manifest: {manifest.manifest_file}")
    click.echo(f"Matched rows: {manifest.row_count}")


@discovery.command(name="connect")
@click.argument("source", type=click.Choice(["google_workspace", "slack"]))
def discovery_connect(source: str) -> None:
    """Connect a corporate workspace account via browser OAuth."""
    click.echo(f"Connecting {source}... This will open your browser.")
    try:
        if source == "google_workspace":
            record = run_google_oauth()
        else:
            record = run_slack_oauth()
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc
    upsert_source(record)
    click.echo(f"✓ Connected: {record['label']} (ID: {record['id']})")


@discovery.command(name="sources")
def discovery_sources() -> None:
    """List all connected workspace sources."""
    sources = list_sources()
    if not sources:
        click.echo("No sources connected. Run: opensore discovery connect google_workspace")
        return
    console = Console()
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Kind")
    table.add_column("Label")
    table.add_column("Connected")
    for record in sources:
        table.add_row(
            str(record.get("id", "")),
            str(record.get("kind", "")),
            str(record.get("label", "")),
            str(record.get("connected_at", "")),
        )
    console.print(table)


@discovery.command(name="disconnect")
@click.argument("source_id")
def discovery_disconnect(source_id: str) -> None:
    """Remove a connected workspace source."""
    removed = remove_source(source_id)
    if not removed:
        click.echo(f"Source not found: {source_id}", err=True)
        raise SystemExit(1)
    click.echo(f"Removed: {source_id}")


@discovery.command(name="verify-sources")
@click.argument("source_id", required=False, default=None)
def discovery_verify_sources(source_id: str | None) -> None:
    """Check connectivity for connected workspace sources."""
    from app.discovery.credentials import get_source

    if source_id is not None:
        record = get_source(source_id)
        if record is None:
            click.echo(f"Source not found: {source_id}", err=True)
            raise SystemExit(1)
        records = [record]
    else:
        records = list_sources()

    if not records:
        click.echo("No sources connected.")
        return

    for record in records:
        connector = get_connector(record)
        if connector is None:
            click.echo(f"✗ {record.get('id', '')} ({record.get('kind', '')}): unsupported kind")
            continue
        ok = connector.verify()
        status = "✓" if ok else "✗"
        click.echo(f"{status} {connector.source_id} ({connector.kind}): {connector.label}")
