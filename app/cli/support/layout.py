"""Rich landing and help renderers for the OpenSore CLI."""

from __future__ import annotations

from collections.abc import Sequence

import click
from rich.console import Console
from rich.text import Text

from app.cli.interactive_shell.ui.banner import build_ready_panel
from app.cli.interactive_shell.ui.theme import BRAND, DIM, TEXT

_LANDING_EXAMPLES: tuple[tuple[str, str], ...] = (
    (
        'opensore "investigate high latency in checkout-api"',
        "Start the interactive agent with a prompt",
    ),
    ("opensore onboard", "Configure LLM provider and integrations"),
    ("opensore investigate -i evidence.json", "Run an investigation against evidence"),
    ("opensore deploy ec2", "Deploy investigation server on AWS EC2"),
    ("opensore remote --url <ip> health", "Check a remote deployed agent"),
    ("opensore remote ops status", "Inspect hosted service status (Railway)"),
    ("opensore tests", "Browse and run inventoried tests"),
    ("opensore integrations list", "Show configured integrations"),
    ("opensore guardrails rules", "List configured guardrail rules"),
    ("opensore health", "Check integration and agent setup status"),
    ("opensore doctor", "Run a full environment diagnostic"),
    ("opensore update", "Update to the latest version"),
    ("opensore version", "Print detailed version, Python and OS info"),
)

_SHORT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("--json, -j", "Emit machine-readable JSON output."),
    ("--verbose", "Print extra diagnostic information."),
    ("--debug", "Print debug-level logs and traces."),
    ("--yes, -y", "Auto-confirm all interactive prompts."),
    ("--version", "Show the version and exit."),
    ("-h, --help", "Show this message and exit."),
)


def _commands_from_group(group: click.Group) -> tuple[tuple[str, str], ...]:
    ctx = click.Context(group)
    rows = []
    for name in group.list_commands(ctx):
        cmd = group.get_command(ctx, name)
        if cmd is not None and not cmd.hidden:
            rows.append((name, cmd.get_short_help_str(limit=200)))
    return tuple(rows)


def _render_usage(console: Console) -> None:
    console.print(
        Text.assemble(
            ("  Usage: "),
            ("opensore", f"bold {TEXT}"),
            (" [OPTIONS] [COMMAND] [ARGS]..."),
        )
    )
    console.print(
        Text.assemble(
            ("  ", ""),
            ("No COMMAND", DIM),
            (": start the interactive shell when stdin/stdout are TTYs.", DIM),
        )
    )


def _render_rows(
    console: Console,
    *,
    title: str,
    rows: Sequence[tuple[str, str]],
    width: int,
) -> None:
    console.print(Text.assemble((f"  {title}:", f"bold {TEXT}")))
    for label, description in rows:
        console.print(
            Text.assemble(("    ", ""), (f"{label:<{width}}", f"bold {BRAND}"), description)
        )


def render_help(group: click.Group) -> None:
    """Render the root help view, deriving the command list from the live Click group."""
    console = Console(highlight=False)
    commands = _commands_from_group(group)
    console.print()
    console.print(build_ready_panel(console))
    console.print()
    _render_usage(console)
    console.print()
    _render_rows(console, title="Commands", rows=commands, width=16)
    console.print()
    _render_rows(console, title="Options", rows=_SHORT_OPTIONS, width=16)
    console.print()


def render_landing() -> None:
    """Render the root landing page shown with no subcommand."""
    console = Console(highlight=False)
    console.print()
    console.print(build_ready_panel(console))
    console.print(
        Text.assemble(
            ("  ", ""),
            "AI-assisted workplace incident investigation for legal, HR, and compliance teams",
        )
    )
    console.print()
    _render_usage(console)
    console.print()
    _render_rows(console, title="Quick start", rows=_LANDING_EXAMPLES, width=42)
    console.print()
    _render_rows(console, title="Options", rows=_SHORT_OPTIONS, width=42)
    console.print()


class RichGroup(click.Group):
    """Click group with a custom Rich-powered help screen."""

    def format_help(self, ctx: click.Context, _formatter: click.HelpFormatter) -> None:
        assert isinstance(ctx.command, click.Group)
        render_help(ctx.command)
