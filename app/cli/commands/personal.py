"""Personal-agent setup helpers."""

from __future__ import annotations

import json
import platform
import shutil

import click
from rich.console import Console
from rich.table import Table

from app.config import get_configured_llm_provider, get_llm_provider_api_key
from app.integrations.store import get_integration

_console = Console(highlight=False)


def _status(ok: bool, detail: str) -> dict[str, str]:
    return {"status": "ok" if ok else "missing", "detail": detail}


def _check_mac() -> dict[str, str]:
    system = platform.system()
    if system != "Darwin":
        return _status(False, f"detected {system}; iMessage automation requires macOS")
    return _status(True, f"macOS {platform.mac_ver()[0] or 'detected'}")


def _check_uv() -> dict[str, str]:
    uv = shutil.which("uv")
    detail = uv or "install uv with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    return _status(bool(uv), detail)


def _check_llm() -> dict[str, str]:
    provider = get_configured_llm_provider()
    from app.integrations.llm_cli.registry import get_cli_provider_registration

    cli_reg = get_cli_provider_registration(provider)
    if cli_reg is not None:
        probe = cli_reg.adapter_factory().detect()
        ok = bool(probe.installed and probe.logged_in is True)
        return _status(ok, f"{provider}: {probe.detail}")

    expected_key, api_key = get_llm_provider_api_key(provider)
    if expected_key and not api_key:
        return _status(False, f"{provider}: missing {expected_key}")
    return _status(True, provider)


def _check_integration(service: str, missing_detail: str) -> dict[str, str]:
    record = get_integration(service)
    if record is None:
        return _status(False, missing_detail)
    return _status(True, f"{service} configured")


def _check_imessage() -> dict[str, str]:
    if get_integration("imessage") is not None:
        return _status(
            False,
            "identity policy exists, but the native iMessage channel adapter is not implemented",
        )
    return _status(
        False,
        "not implemented yet; use OpenClaw/Beeper/BlueBubbles bridge work from the roadmap",
    )


def _personal_checks() -> dict[str, dict[str, str]]:
    return {
        "mac": _check_mac(),
        "uv": _check_uv(),
        "llm": _check_llm(),
        "whatsapp": _check_integration(
            "whatsapp", "run: uv run opensre integrations setup whatsapp"
        ),
        "imessage": _check_imessage(),
        "openclaw": _check_integration(
            "openclaw", "optional bridge: uv run opensre integrations setup openclaw"
        ),
    }


@click.group("personal")
def personal() -> None:
    """Personal agent setup for Mac, LLMs, WhatsApp, and iMessage."""


@personal.command("doctor")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
def doctor(json_output: bool) -> None:
    """Check readiness for the personal messaging-agent path."""
    checks = _personal_checks()
    if json_output:
        click.echo(json.dumps(checks, indent=2))
        return

    table = Table(title="OpenSRE Personal Agent Readiness")
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail")
    for name, result in checks.items():
        ok = result["status"] == "ok"
        table.add_row(name, "ok" if ok else "missing", result["detail"])
    _console.print(table)
    _console.print()
    _console.print("Fast path:")
    _console.print("  uv run opensre onboard")
    _console.print("  uv run opensre integrations setup whatsapp")
    _console.print("  uv run opensre messaging pair --platform whatsapp")
    _console.print()
    _console.print("Roadmap: docs/personal-agent-roadmap.mdx")


@personal.command("plan")
def plan() -> None:
    """Print the shortest path from this repo to a personal OpenClaw-like agent."""
    items: list[tuple[str, str]] = [
        ("1", "Mac installer and first-run doctor"),
        ("2", "Cheap-model preset picker for Gemini, OpenAI, Claude, OpenRouter, and Ollama"),
        ("3", "WhatsApp inbound webhook loop with pairing, allowlists, and transcript storage"),
        ("4", "iMessage bridge integration for macOS through Messages automation or a bridge"),
        ("5", "Persistent conversation memory and per-contact permissions"),
        ("6", "Safe action system with approval prompts for sending, deleting, and purchasing"),
        ("7", "OpenClaw-style gateway that normalizes messages from every channel"),
    ]
    table = Table(title="Personal Agent Build Plan")
    table.add_column("#", no_wrap=True)
    table.add_column("Feature")
    for number, item in items:
        table.add_row(number, item)
    _console.print(table)


def command() -> click.Group:
    return personal
