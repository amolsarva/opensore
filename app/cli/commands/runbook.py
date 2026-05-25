"""``opensore runbook`` — view and manage auto-generated investigation runbooks."""

from __future__ import annotations

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

console = Console()


@click.group(name="runbook")
def runbook() -> None:
    """View and manage auto-generated investigation runbooks."""


@runbook.command(name="list")
@click.option(
    "--category",
    "-c",
    default=None,
    help="Filter by root cause category (e.g. database, memory, network).",
)
@click.option("--limit", "-n", default=20, show_default=True, help="Maximum rows to display.")
def list_runbooks_command(category: str | None, limit: int) -> None:
    """List recent runbooks stored in ~/.opensore/runbooks/."""
    from app.pipeline.runbook import list_runbooks

    entries = list_runbooks(category=category, limit=limit)
    if not entries:
        console.print(
            "[dim]No runbooks found. They are auto-generated after each investigation.[/dim]"
        )
        return

    table = Table(title="Investigation Runbooks", show_lines=False, expand=True)
    table.add_column("ID", style="cyan", no_wrap=True, width=14)
    table.add_column("Alert", style="white")
    table.add_column("Category", style="yellow")
    table.add_column("Confidence", justify="right", style="green")
    table.add_column("Generated", style="dim")

    for entry in entries:
        score = entry.get("validity_score") or 0.0
        table.add_row(
            entry.get("runbook_id", ""),
            entry.get("alert_name", ""),
            entry.get("root_cause_category", ""),
            f"{float(score):.0%}",
            entry.get("generated_at", "")[:16].replace("T", " "),
        )

    console.print(table)


@runbook.command(name="show")
@click.argument("runbook_id")
@click.option("--raw", is_flag=True, help="Print raw Markdown instead of rendered output.")
def show_runbook_command(runbook_id: str, raw: bool) -> None:
    """Display a specific runbook by ID."""
    from app.pipeline.runbook import load_runbook

    content = load_runbook(runbook_id)
    if content is None:
        console.print(f"[red]Runbook '{runbook_id}' not found.[/red]")
        raise SystemExit(1)

    if raw:
        click.echo(content)
    else:
        console.print(Markdown(content))


@runbook.command(name="generate")
@click.option(
    "--alert-name",
    required=True,
    help="Alert name to generate runbook for (e.g. 'HighMemoryUsage').",
)
@click.option("--root-cause", default="", help="Root cause description.")
@click.option("--category", default="unknown", help="Root cause category.")
@click.option(
    "--remediation",
    multiple=True,
    help="Remediation step (repeat for multiple: --remediation 'step 1' --remediation 'step 2').",
)
@click.option("--output", "-o", default=None, help="Write runbook to this file path.")
def generate_runbook_command(
    alert_name: str,
    root_cause: str,
    category: str,
    remediation: tuple[str, ...],
    output: str | None,
) -> None:
    """Manually generate a runbook from provided parameters."""
    from app.pipeline.runbook import generate_runbook

    state: dict = {
        "alert_name": alert_name,
        "root_cause": root_cause,
        "root_cause_category": category,
        "remediation_steps": list(remediation),
        "causal_chain": [],
        "validated_claims": [],
        "non_validated_claims": [],
        "validity_score": 0.0,
        "raw_alert": {},
        "evidence_entries": [],
    }

    result = generate_runbook(state)
    runbook_md = result["runbook_md"]

    if output:
        import pathlib

        pathlib.Path(output).write_text(runbook_md, encoding="utf-8")
        console.print(f"[green]Runbook written to {output}[/green]")
    else:
        console.print(Markdown(runbook_md))
        console.print(
            f"\n[dim]Saved as runbook ID [cyan]{result['runbook_id']}[/cyan] in {result['runbook_path']}[/dim]"
        )
