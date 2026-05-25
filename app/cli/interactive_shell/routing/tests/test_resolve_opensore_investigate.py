"""Deterministic routing for ``opensore investigate -i <file>`` quick-start input."""

from __future__ import annotations

from app.cli.interactive_shell.routing.resolve_cli_command.evaluator import (
    resolve_cli_command,
)
from app.cli.interactive_shell.routing.resolve_cli_command.matcher import (
    opensore_investigate_slash_text,
)
from app.cli.interactive_shell.routing.router import RouteKind, route_input
from app.cli.interactive_shell.runtime.session import ReplSession


def test_opensore_investigate_slash_text_maps_input_flag() -> None:
    assert (
        opensore_investigate_slash_text("opensore investigate -i alert.json")
        == "/investigate alert.json"
    )
    assert (
        opensore_investigate_slash_text(
            "opensore investigate --input tests/fixtures/openclaw_test_alert.json"
        )
        == "/investigate tests/fixtures/openclaw_test_alert.json"
    )
    assert (
        opensore_investigate_slash_text(
            'opensore investigate --input-file "tests/fixtures/alert payload.json"'
        )
        == "/investigate tests/fixtures/alert payload.json"
    )


def test_opensore_investigate_without_path_defaults_to_demo_alert() -> None:
    assert opensore_investigate_slash_text("opensore investigate") == "/investigate alert.json"


def test_resolve_cli_command_routes_opensore_investigate_as_slash() -> None:
    session = ReplSession()
    decision = resolve_cli_command("opensore investigate -i alert.json", session)
    assert decision is not None
    assert decision.route_kind == RouteKind.SLASH
    assert decision.command_text == "/investigate alert.json"
    assert "opensore_investigate" in decision.matched_signals


def test_route_input_does_not_send_opensore_investigate_to_llm_planner() -> None:
    decision = route_input("opensore investigate -i alert.json", ReplSession())
    assert decision.route_kind == RouteKind.SLASH
    assert decision.command_text == "/investigate alert.json"
