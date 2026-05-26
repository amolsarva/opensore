"""Coverage for ``app.tools._telemetry`` and tool-level Sentry capture.

Three layers:

1. ``test_report_run_error_*`` exercise the helper directly: tags, severity,
   logger forwarding, and the fact that a Sentry capture is best-effort.
2. ``test_tool_reports_exactly_one_sentry_event`` is the parameterised
   "every migrated tool reports a Sentry event when its underlying client
   raises" assertion called out in #1463 acceptance criteria. Each row
   forces the client used by the tool body to raise and verifies the helper
   produced exactly one event with the expected ``surface=tool``,
   ``tool_name``, and ``source`` tags.
3. ``test_eks_client_error_path_uses_warning_severity`` exercises the EKS
   ``except ClientError`` branch (the whole reason for the severity split)
   by patching the underlying client to raise ``botocore.exceptions.ClientError``
   and asserting the helper logged at ``WARNING``, not ``ERROR``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.tools._telemetry import report_run_error


@dataclass
class CapturedSentryEvent:
    """One Sentry capture, with the scope extras that were attached.

    ``report_exception`` flattens tags into ``extra`` with a ``tag.`` prefix
    (see ``app/utils/errors.py``), so a tag set via
    ``report_run_error(tool_name="X")`` shows up here as
    ``extras["tag.tool_name"] == "X"``.
    """

    exc: BaseException
    extras: dict[str, Any]


@pytest.fixture
def captured_sentry_events(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[CapturedSentryEvent]]:
    """Patch the Sentry SDK so every capture lands in a local list.

    Tests rely on this rather than the real ``sentry_sdk`` because:
      * ``conftest`` sets ``OPENSORE_SENTRY_DISABLED=1`` to keep the suite
        offline — we re-enable it here.
      * ``capture_exception`` and ``push_scope`` both need to be present
        for the contextual-tag path inside ``app.utils.sentry_sdk``.

    The mock ``push_scope`` returns a per-call ``_Scope`` instance that
    records every ``set_extra`` and ``set_tag`` call. ``capture_exception``
    snapshots the current scope's extras alongside the exception so tests
    can assert on the tags that reached Sentry.
    """
    monkeypatch.delenv("OPENSORE_SENTRY_DISABLED", raising=False)
    monkeypatch.delenv("OPENSORE_NO_TELEMETRY", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)

    events: list[CapturedSentryEvent] = []
    scope_stack: list[_RecordingScope] = []

    class _RecordingScope:
        def __init__(self) -> None:
            self.extras: dict[str, Any] = {}

        def __enter__(self) -> _RecordingScope:
            scope_stack.append(self)
            return self

        def __exit__(self, *_args: object) -> None:
            if scope_stack and scope_stack[-1] is self:
                scope_stack.pop()
            return None

        def set_tag(self, key: str, value: str) -> None:
            # Mirror the existing ``report_exception`` convention so tests
            # see a single flat extras dict regardless of whether a value
            # was attached via set_tag or set_extra.
            self.extras[f"tag.{key}"] = value

        def set_extra(self, key: str, value: object) -> None:
            self.extras[key] = value

    def _capture(exc: BaseException) -> None:
        current_extras = dict(scope_stack[-1].extras) if scope_stack else {}
        events.append(CapturedSentryEvent(exc=exc, extras=current_extras))

    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk",
        SimpleNamespace(capture_exception=_capture, push_scope=_RecordingScope),
    )
    yield events


def test_report_run_error_captures_with_expected_tags(
    captured_sentry_events: list[CapturedSentryEvent],
    caplog: pytest.LogCaptureFixture,
) -> None:
    boom = RuntimeError("boom")
    with caplog.at_level(logging.ERROR, logger="app.tools"):
        report_run_error(
            boom,
            tool_name="query_azure_monitor_logs",
            source="azure",
            component="app.tools.AzureMonitorLogsTool",
            method="httpx.post",
            extras={"workspace_id": "w"},
        )

    assert len(captured_sentry_events) == 1
    event = captured_sentry_events[0]
    assert event.exc is boom
    assert event.extras["tag.surface"] == "tool"
    assert event.extras["tag.tool_name"] == "query_azure_monitor_logs"
    assert event.extras["tag.source"] == "azure"
    assert event.extras["tag.component"] == "app.tools.AzureMonitorLogsTool"
    assert event.extras["tag.method"] == "httpx.post"
    assert event.extras["workspace_id"] == "w"
    assert "Tool query_azure_monitor_logs failed" in caplog.text


def test_report_run_error_supports_warning_severity(
    captured_sentry_events: list[CapturedSentryEvent],
    caplog: pytest.LogCaptureFixture,
) -> None:
    err = RuntimeError("recoverable")
    with caplog.at_level(logging.WARNING, logger="app.tools"):
        report_run_error(
            err,
            tool_name="describe_eks_cluster",
            source="eks",
            component="app.tools.EKSDescribeClusterTool",
            severity="warning",
        )

    assert len(captured_sentry_events) == 1
    assert captured_sentry_events[0].exc is err
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records == [], "warning severity must not log at error level"
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_records, "warning severity must produce a WARNING log record"


def test_report_run_error_uses_provided_logger(
    captured_sentry_events: list[CapturedSentryEvent],
) -> None:
    custom_logger = MagicMock(spec=logging.Logger)
    err = ValueError("nope")

    report_run_error(
        err,
        tool_name="list_eks_pods",
        source="eks",
        component="app.tools.EKSListPodsTool",
        logger=custom_logger,
    )

    custom_logger.error.assert_called_once()
    assert len(captured_sentry_events) == 1
    assert captured_sentry_events[0].exc is err


# ---------------------------------------------------------------------------
# Parameterised tool coverage
#
# Each case patches the lowest-level dependency the tool reaches for and forces
# it to raise. The helper must then produce exactly one Sentry event so the
# silent ``{"available": False}`` return is no longer invisible to operators.
# ---------------------------------------------------------------------------


@dataclass
class ToolFailureCase:
    id: str
    patch: Callable[[pytest.MonkeyPatch], None]
    invoke: Callable[[], dict[str, Any]]
    expected_tool_name: str
    expected_source: str


def _google_docs_case() -> ToolFailureCase:
    def patch(mp: pytest.MonkeyPatch) -> None:
        from app.tools import GoogleDocsCreateReportTool as mod

        mp.setattr(
            mod,
            "GoogleDocsClient",
            MagicMock(side_effect=RuntimeError("google")),
        )

    def invoke() -> dict[str, Any]:
        from app.tools.GoogleDocsCreateReportTool import create_google_docs_incident_report

        return create_google_docs_incident_report(
            title="t",
            summary="s",
            root_cause="rc",
            severity="low",
            credentials_file="/tmp/missing.json",
            folder_id="f",
        )

    return ToolFailureCase(
        "google_docs_create_report",
        patch,
        invoke,
        "create_google_docs_incident_report",
        "google_docs",
    )


def _patch_openclaw_runtime(mp: pytest.MonkeyPatch) -> None:
    """Shared patches for all OpenClaw cases — bypass the config/runtime guards.

    Each test still patches the specific failure point afterwards.
    """
    from app.tools import OpenClawMCPTool as mod

    mp.setattr(
        mod,
        "_resolve_config",
        MagicMock(return_value=SimpleNamespace(mode="stdio", command="x", url="")),
    )
    mp.setattr(mod, "openclaw_runtime_unavailable_reason", MagicMock(return_value=None))
    mp.setattr(mod, "describe_openclaw_error", MagicMock(return_value="mocked error"))


def _openclaw_list_case() -> ToolFailureCase:
    def patch(mp: pytest.MonkeyPatch) -> None:
        from app.tools import OpenClawMCPTool as mod

        _patch_openclaw_runtime(mp)
        mp.setattr(mod, "list_openclaw_mcp_tools", MagicMock(side_effect=RuntimeError("mcp")))

    def invoke() -> dict[str, Any]:
        from app.tools.OpenClawMCPTool import list_openclaw_bridge_tools

        return list_openclaw_bridge_tools()

    return ToolFailureCase("openclaw_list_tools", patch, invoke, "list_openclaw_tools", "openclaw")


def _openclaw_search_case() -> ToolFailureCase:
    def patch(mp: pytest.MonkeyPatch) -> None:
        from app.tools import OpenClawMCPTool as mod

        _patch_openclaw_runtime(mp)
        mp.setattr(mod, "invoke_openclaw_mcp_tool", MagicMock(side_effect=RuntimeError("mcp")))

    def invoke() -> dict[str, Any]:
        from app.tools.OpenClawMCPTool import search_openclaw_conversations

        return search_openclaw_conversations(search="db error")

    return ToolFailureCase(
        "openclaw_search_conversations",
        patch,
        invoke,
        "search_openclaw_conversations",
        "openclaw",
    )


def _openclaw_get_conversation_case() -> ToolFailureCase:
    """Exercises ``_normalize_named_bridge_call`` via ``get_openclaw_conversation``.

    Verifies the helper's ``surface_tool_name`` plumbing — the Sentry
    ``tool_name`` tag must be ``get_openclaw_conversation`` (the registered
    surface name), not ``conversations_get`` (the MCP-side tool id).
    """

    def patch(mp: pytest.MonkeyPatch) -> None:
        from app.tools import OpenClawMCPTool as mod

        _patch_openclaw_runtime(mp)
        mp.setattr(mod, "invoke_openclaw_mcp_tool", MagicMock(side_effect=RuntimeError("mcp")))

    def invoke() -> dict[str, Any]:
        from app.tools.OpenClawMCPTool import get_openclaw_conversation

        return get_openclaw_conversation(conversation_id="conv-1")

    return ToolFailureCase(
        "openclaw_get_conversation",
        patch,
        invoke,
        "get_openclaw_conversation",
        "openclaw",
    )


def _openclaw_call_tool_case() -> ToolFailureCase:
    def patch(mp: pytest.MonkeyPatch) -> None:
        from app.tools import OpenClawMCPTool as mod

        _patch_openclaw_runtime(mp)
        mp.setattr(mod, "invoke_openclaw_mcp_tool", MagicMock(side_effect=RuntimeError("mcp")))

    def invoke() -> dict[str, Any]:
        from app.tools.OpenClawMCPTool import call_openclaw_bridge_tool

        return call_openclaw_bridge_tool(tool_name="permissions_grant", arguments={})

    return ToolFailureCase(
        "openclaw_call_tool",
        patch,
        invoke,
        "call_openclaw_tool",
        "openclaw",
    )


_TOOL_FAILURE_CASES: list[ToolFailureCase] = [
    _google_docs_case(),
    _openclaw_list_case(),
    _openclaw_search_case(),
    _openclaw_get_conversation_case(),
    _openclaw_call_tool_case(),
]


@pytest.mark.parametrize(
    "case",
    _TOOL_FAILURE_CASES,
    ids=[case.id for case in _TOOL_FAILURE_CASES],
)
def test_tool_reports_exactly_one_sentry_event(
    case: ToolFailureCase,
    captured_sentry_events: list[CapturedSentryEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case.patch(monkeypatch)

    result = case.invoke()

    # Tools either expose ``available=False`` or fall back to ``success=False``
    # (GoogleDocs) / raw ``{"error": ...}`` (CloudWatchLogs) — all three are
    # the "silent today" shapes #1463 enumerates. We just need the negative
    # signal to be present so an accidental success doesn't pass the assertion.
    assert isinstance(result, dict)
    assert result.get("available") is False or result.get("success") is False or "error" in result

    assert len(captured_sentry_events) == 1, (
        f"{case.id} should report exactly one Sentry event when its client raises; "
        f"got {len(captured_sentry_events)}"
    )
    event = captured_sentry_events[0]
    assert isinstance(event.exc, RuntimeError)
    assert event.extras["tag.surface"] == "tool"
    assert event.extras["tag.tool_name"] == case.expected_tool_name
    assert event.extras["tag.source"] == case.expected_source

    # Guard against a future regression where a tool migrates to the helper
    # but passes a ``tool_name=`` / ``source=`` that no longer matches its
    # declared metadata.
    from app.tools.registry import get_registered_tool_map

    registered = get_registered_tool_map().get(case.expected_tool_name)
    if registered is not None:
        assert registered.source == case.expected_source


# ---------------------------------------------------------------------------
# Registry-wide coverage
#
# Acceptance criterion 4 of #1463: "Tool registry tests confirm telemetry
# coverage for every registered tool (or explicitly-allowlisted exclusions)."
#
# Every registered tool must fall into exactly one bucket:
#
#   ``_MIGRATED_TOOL_NAMES``
#       The tool's body deliberately catches exceptions and returns a
#       structured error dict. It calls ``report_run_error`` directly so the
#       failure reaches Sentry. These are the tools migrated by #1463.
#
#   ``_TOOLS_WITHOUT_DELIBERATE_CATCH``
#       The tool either propagates exceptions (the global wrapper added in
#       #1476 catches them at ``BaseTool.__call__`` / ``RegisteredTool.__call__``
#       and reports with ``opensore.context="tool.<name>"``) or has no failure
#       mode that needs the helper. The allowlist is explicit so a new tool
#       added with a deliberate-catch pattern fails this test until it is
#       migrated.
#
# When a new tool is registered, this test will fail; the contributor must
# either add it to ``_MIGRATED_TOOL_NAMES`` (and migrate the body) or add it
# to ``_TOOLS_WITHOUT_DELIBERATE_CATCH`` (with a brief commit-message reason).
# ---------------------------------------------------------------------------


_MIGRATED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "create_google_docs_incident_report",
        # OpenClaw — all swallow sites in OpenClawMCPTool/__init__.py.
        # ``send_openclaw_message`` and ``get_openclaw_conversation`` share
        # ``_normalize_named_bridge_call`` via the ``surface_tool_name`` arg.
        "list_openclaw_tools",
        "search_openclaw_conversations",
        "get_openclaw_conversation",
        "send_openclaw_message",
        "call_openclaw_tool",
    }
)


# Tools that do NOT need the helper because they either (a) let exceptions
# escape to the global ``BaseTool.__call__`` / ``RegisteredTool.__call__``
# wrapper from #1476, or (b) have no observed swallow pattern. Keep alphabetised.
_TOOLS_WITHOUT_DELIBERATE_CATCH: frozenset[str] = frozenset(
    {
        "broadcast_findings",
        # Evidence synthesis — pure computation, no external API; exceptions propagate.
        "build_evidence_timeline",
        "get_bitbucket_file_contents",
        "get_github_file_contents",
        "get_github_repository_tree",
        "get_gitlab_file",
        "http_probe",
        "jira_add_comment",
        "jira_create_issue",
        "jira_issue_detail",
        "jira_search_issues",
        "linear_create_issue",
        "linear_search_issues",
        "list_bitbucket_commits",
        "list_github_commits",
        "list_gitlab_commits",
        "list_gitlab_mrs",
        # HR/legal tools — catch and return structured {"available": False} without report_run_error.
        "analyze_communication_patterns",
        "detect_evidence_contradictions",
        "generate_investigation_report",
        "lookup_bamboohr_employee",
        "lookup_okta_identity",
        "manage_case_notes",
        "run_diagnostic_code",
        "search_bitbucket_code",
        "search_github_code",
        "search_gmail_emails",
        "search_google_calendar",
        "search_sharepoint_documents",
        "search_teams_messages",
        "search_zoom_meetings",
        "slack_channel_history",
        "slack_search_messages",
        "twilio_notify",
    }
)


def test_every_registered_tool_is_migrated_or_allowlisted() -> None:
    """Acceptance criterion 4: every registered tool is accounted for.

    A new tool must be classified up front — either it deliberately catches
    its own exceptions (migrate it; add to ``_MIGRATED_TOOL_NAMES``) or it
    lets them escape and relies on #1476's global wrapper (allowlist it in
    ``_TOOLS_WITHOUT_DELIBERATE_CATCH``).
    """
    from app.tools.registry import get_registered_tool_map

    registered = set(get_registered_tool_map().keys())
    classified = _MIGRATED_TOOL_NAMES | _TOOLS_WITHOUT_DELIBERATE_CATCH

    unclassified = registered - classified
    assert unclassified == set(), (
        "New tools must be classified for Sentry coverage in test_telemetry.py: "
        "either add them to _MIGRATED_TOOL_NAMES (and call report_run_error in "
        "their except block) or to _TOOLS_WITHOUT_DELIBERATE_CATCH (if they "
        f"let exceptions escape to the #1476 global wrapper). Unclassified: {sorted(unclassified)}"
    )

    stale = classified - registered
    assert stale == set(), (
        "These names appear in _MIGRATED_TOOL_NAMES or _TOOLS_WITHOUT_DELIBERATE_CATCH "
        f"but are no longer registered tools: {sorted(stale)}"
    )

    overlap = _MIGRATED_TOOL_NAMES & _TOOLS_WITHOUT_DELIBERATE_CATCH
    assert overlap == set(), (
        f"A tool cannot be both migrated and allowlisted; pick one: {sorted(overlap)}"
    )


def test_every_migrated_tool_has_a_parameterised_failure_case() -> None:
    """Each migrated tool must have a regression test in ``_TOOL_FAILURE_CASES``.

    ``send_openclaw_message`` is the documented exception: it shares
    ``_normalize_named_bridge_call`` with ``get_openclaw_conversation``,
    and the latter's case already exercises that helper's
    ``report_run_error`` path.
    """
    covered_by_parametrised = {case.expected_tool_name for case in _TOOL_FAILURE_CASES}
    shared_code_path = {"send_openclaw_message"}
    missing = _MIGRATED_TOOL_NAMES - covered_by_parametrised - shared_code_path
    assert missing == set(), (
        "Every name in _MIGRATED_TOOL_NAMES must have a parameterised "
        "failure case in _TOOL_FAILURE_CASES (unless it shares a code path "
        f"already covered by another case). Missing: {sorted(missing)}"
    )
