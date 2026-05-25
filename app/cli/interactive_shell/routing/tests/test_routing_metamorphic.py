"""Metamorphic routing invariants for command and non-command paths."""

from __future__ import annotations

import pytest

from app.cli.interactive_shell.routing.policy_tags import RouteSignal
from app.cli.interactive_shell.routing.router import RouteKind, route_input
from app.cli.interactive_shell.runtime.session import ReplSession


@pytest.mark.parametrize(
    "prompt",
    [
        "help",
        " HELP ",
        "\thelp\t",
    ],
)
def test_help_alias_whitespace_and_case_variants_route_to_slash_help(prompt: str) -> None:
    decision = route_input(prompt, ReplSession())
    assert decision.route_kind is RouteKind.SLASH
    assert decision.command_text == "/help"
    assert decision.matched_signals == (RouteSignal.BARE_COMMAND_ALIAS.value,)


@pytest.mark.parametrize(
    "prompt",
    [
        "opensore investigate -i alert.json",
        "  OPENSORE investigate -i alert.json  ",
        "\topensore   investigate   -i   alert.json\t",
    ],
)
def test_opensore_investigate_variants_keep_deterministic_route(prompt: str) -> None:
    decision = route_input(prompt, ReplSession())
    assert decision.route_kind is RouteKind.SLASH
    assert decision.command_text is not None
    assert decision.command_text.startswith("/investigate")
    assert decision.matched_signals == (RouteSignal.OPENSORE_INVESTIGATE.value,)


@pytest.mark.parametrize(
    "prompt",
    [
        "check opensore health and show connected services",
        "CHECK OPENsRE HEALTH and SHOW connected SERVICES",
        "  check opensore health and show connected services  ",
    ],
)
def test_non_command_action_plan_variants_keep_cli_agent_signal(prompt: str) -> None:
    decision = route_input(prompt, ReplSession())
    assert decision.route_kind is RouteKind.CLI_AGENT
    assert RouteSignal.CLI_AGENT_ACTION_PLAN.value in decision.matched_signals
