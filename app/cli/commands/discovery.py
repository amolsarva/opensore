"""Workplace discovery CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

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
