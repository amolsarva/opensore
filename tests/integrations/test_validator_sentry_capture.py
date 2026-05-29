"""AST checks: every migrated broad-except in app/integrations calls report_validation_failure.

Issue #1470 acceptance criterion: every listed validator must invoke
``report_validation_failure`` on its broad ``except Exception`` block, with
tags carrying ``integration`` and ``method`` so Sentry events are filterable
by vendor.

This test parses each integration module and asserts, for every listed
``(function, line)`` pair, that:

1. The function's broad ``except Exception`` handler contains a call to
   ``report_validation_failure``.
2. The ``integration=`` and ``method=`` keyword arguments are string literals
   matching the expected tag values.

Two intentional exceptions are excluded — both are inner-loop ``except`` blocks
that ``continue`` or ``raise``; their failures already reach Sentry via the
outer except (or are deliberate version-detection fallbacks):

- ``mysql.get_replication_status`` inner ``stmt_err`` (MySQL <8.0.22 fallback)
- ``mariadb.get_replication_status`` inner ``stmt_err`` (analogous)
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MigrationCase:
    module_path: str  # repo-relative file path
    function: str  # outer function name (may include "."-separated nested suffix)
    integration: str  # expected tag.integration
    method: str  # expected tag.method


CASES: tuple[MigrationCase, ...] = (
    # github_mcp
    MigrationCase(
        "app/integrations/github_mcp.py",
        "validate_github_mcp_config",
        "github_mcp",
        "validate_github_mcp_config",
    ),
    # openclaw
    MigrationCase(
        "app/integrations/openclaw.py",
        "validate_openclaw_config",
        "openclaw",
        "validate_openclaw_config",
    ),
    # gitlab
    MigrationCase(
        "app/integrations/gitlab.py", "validate_gitlab_config", "gitlab", "validate_gitlab_config"
    ),
    # bitbucket
    MigrationCase(
        "app/integrations/bitbucket.py",
        "validate_bitbucket_config",
        "bitbucket",
        "validate_bitbucket_config",
    ),
    MigrationCase("app/integrations/bitbucket.py", "list_commits", "bitbucket", "list_commits"),
    MigrationCase(
        "app/integrations/bitbucket.py", "get_file_contents", "bitbucket", "get_file_contents"
    ),
    MigrationCase("app/integrations/bitbucket.py", "search_code", "bitbucket", "search_code"),
    # adjacent
    MigrationCase(
        "app/integrations/daily_update.py",
        "summarize_highlights",
        "daily_update",
        "summarize_highlights",
    ),
    MigrationCase(
        "app/integrations/llm_cli/kimi.py",
        "_check_kimi_auth_fallback",
        "kimi",
        "_check_kimi_auth_fallback",
    ),
)


def _walk_funcs(tree: ast.AST) -> Iterator[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            yield node


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for fn in _walk_funcs(tree):
        if fn.name == name:
            return fn
    return None


def _broad_except_handlers(fn: ast.FunctionDef) -> list[ast.ExceptHandler]:
    """Return the *outermost* ``except Exception`` handlers in the function body.

    Skips handlers that are themselves nested inside another broad-except — a
    `report_validation_failure` placed in an inner handler wouldn't compensate
    for a missing call in the outer one, which is the false-positive Greptile
    flagged in PR #1869.
    """
    all_handlers: list[ast.ExceptHandler] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.ExceptHandler):
            t = node.type
            if isinstance(t, ast.Name) and t.id == "Exception":
                all_handlers.append(node)

    nested: set[int] = set()
    for outer in all_handlers:
        for descendant in ast.walk(outer):
            if descendant is outer:
                continue
            if isinstance(descendant, ast.ExceptHandler):
                t = descendant.type
                if isinstance(t, ast.Name) and t.id == "Exception":
                    nested.add(id(descendant))

    return [h for h in all_handlers if id(h) not in nested]


def _calls_to(handler: ast.ExceptHandler, func_name: str) -> list[ast.Call]:
    """Find ``func_name(...)`` calls inside an except handler body.

    Does not descend into nested ``except`` handler bodies — a call inside a
    nested broad-except does not satisfy coverage of the outer one.
    """
    matches: list[ast.Call] = []
    stack: list[ast.AST] = list(handler.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.ExceptHandler):
            # Don't descend into another except's body; its calls aren't ours.
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == func_name
        ):
            matches.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return matches


def _kwarg_str(call: ast.Call, key: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda c: f"{Path(c.module_path).stem}::{c.function}",
)
def test_broad_except_calls_report_validation_failure(case: MigrationCase) -> None:
    source = (_REPO_ROOT / case.module_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _find_function(tree, case.function)
    assert fn is not None, f"function {case.function} not found in {case.module_path}"

    handlers = _broad_except_handlers(fn)
    assert handlers, f"no `except Exception` handlers in {case.module_path}::{case.function}"

    matching_calls: list[ast.Call] = []
    for h in handlers:
        for call in _calls_to(h, "report_validation_failure"):
            integration = _kwarg_str(call, "integration")
            method = _kwarg_str(call, "method")
            if integration == case.integration and method == case.method:
                matching_calls.append(call)

    assert matching_calls, (
        f"{case.module_path}::{case.function} has no `report_validation_failure` call "
        f"with integration={case.integration!r} and method={case.method!r}"
    )
    # Each tagged (integration, method) pair should appear exactly once per function
    # to prevent accidental double-capture in the same except block.
    assert len(matching_calls) == 1, (
        f"{case.module_path}::{case.function} reports the same "
        f"(integration={case.integration!r}, method={case.method!r}) "
        f"{len(matching_calls)} times; expected exactly once"
    )


def test_every_migrated_module_imports_the_helper() -> None:
    """Sanity guard: every file we touched should import report_validation_failure."""
    seen_modules = {case.module_path for case in CASES}
    for module_path in seen_modules:
        source = (_REPO_ROOT / module_path).read_text(encoding="utf-8")
        assert (
            "from app.integrations._validation_helpers import report_validation_failure" in source
        ), f"{module_path} migration is incomplete: missing import of report_validation_failure"


def test_broad_except_handlers_skips_nested_handlers() -> None:
    """The helper must ignore broad-except handlers nested inside another broad-except.

    Otherwise a `report_validation_failure` call in the inner handler would
    falsely satisfy the assertion when the outer handler is uncovered (the
    false-positive path flagged by Greptile on PR #1869).
    """
    source = """
def f():
    try:
        do_thing()
    except Exception:
        try:
            cleanup()
        except Exception:
            report_validation_failure(err, integration="x", method="f")
"""
    tree = ast.parse(source)
    fn = _find_function(tree, "f")
    assert fn is not None
    handlers = _broad_except_handlers(fn)
    assert len(handlers) == 1, "should return only the outer handler"
    # The call exists only in the inner handler; helper must not surface it.
    assert _calls_to(handlers[0], "report_validation_failure") == []


def test_broad_except_handlers_finds_handler_inside_normal_control_flow() -> None:
    """Handlers inside for/while/if are still surfaced — only nested-except is excluded.

    Airflow's per-DAG-run capture lives inside a ``for`` loop's try block; the
    helper must not regress that case.
    """
    source = """
def f():
    for x in items:
        try:
            work(x)
        except Exception:
            report_validation_failure(err, integration="x", method="f")
            continue
"""
    tree = ast.parse(source)
    fn = _find_function(tree, "f")
    assert fn is not None
    handlers = _broad_except_handlers(fn)
    assert len(handlers) == 1
    assert _calls_to(handlers[0], "report_validation_failure")
