from __future__ import annotations

import asyncio
import collections
import shutil
import sys
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Named tuple matching shutil.disk_usage's return shape — constructed without
# touching the real filesystem, so tests are fully isolated from host disk state.
_DiskUsage = collections.namedtuple("usage", ["total", "used", "free"])
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.remote import server as remote_server
from app.remote.server import (
    DeepHealthCheck,
    InvestigateRequest,
    _check_disk_health,
    _check_llm_connectivity,
    _check_memory_health,
    _imds_get,
    _imds_token,
    _lifespan,
    investigate,
    investigate_stream,
)
from app.remote.stream import StreamEvent


class _UrlopenResponse:
    def __init__(self, body: str) -> None:
        self._body = body

    def __enter__(self) -> _UrlopenResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode("utf-8")


@pytest.fixture
def remote_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    monkeypatch.setattr(remote_server, "INVESTIGATIONS_DIR", tmp_path)
    return TestClient(remote_server.app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("post", "/investigate", {"json": {"raw_alert": {"alert_name": "High CPU"}}}),
        ("post", "/investigate/stream", {"json": {"raw_alert": {"alert_name": "High CPU"}}}),
        ("get", "/investigations", {}),
        ("get", "/investigations/example", {}),
    ],
)
@pytest.mark.parametrize("configured_key", [None, "", "   "])
def test_protected_remote_endpoints_fail_closed_without_configured_api_key(
    monkeypatch: pytest.MonkeyPatch,
    remote_client: TestClient,
    configured_key: str | None,
    method: str,
    path: str,
    kwargs: dict[str, Any],
) -> None:
    monkeypatch.setattr(remote_server, "_AUTH_KEY", configured_key)

    response = getattr(remote_client, method)(path, **kwargs)

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


def test_protected_remote_endpoint_requires_matching_api_key(
    monkeypatch: pytest.MonkeyPatch,
    remote_client: TestClient,
) -> None:
    monkeypatch.setattr(remote_server, "_AUTH_KEY", "secret-key")

    missing_response = remote_client.get("/investigations")
    wrong_response = remote_client.get("/investigations", headers={"x-api-key": "wrong"})
    valid_response = remote_client.get("/investigations", headers={"x-api-key": "secret-key"})

    assert missing_response.status_code == 403
    assert wrong_response.status_code == 403
    assert valid_response.status_code == 200
    assert valid_response.json() == []


@pytest.mark.parametrize("path", ["/ok", "/version", "/health/deep"])
@pytest.mark.parametrize("configured_key", [None, "secret-key"])
def test_health_endpoints_do_not_require_api_key(
    monkeypatch: pytest.MonkeyPatch,
    remote_client: TestClient,
    path: str,
    configured_key: str | None,
) -> None:
    monkeypatch.setattr(remote_server, "_AUTH_KEY", configured_key)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    response = remote_client.get(path)

    assert response.status_code == 200


def test_investigate_captures_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_errors: list[BaseException] = []
    expected_error = RuntimeError("pipeline exploded")

    def fake_execute_investigation(**_kwargs: Any) -> tuple[dict[str, Any], str, str, str]:
        raise expected_error

    monkeypatch.setattr(remote_server, "_execute_investigation", fake_execute_investigation)
    monkeypatch.setattr(remote_server, "capture_exception", captured_errors.append)

    with pytest.raises(HTTPException) as exc_info:
        investigate(InvestigateRequest(raw_alert={"alert_name": "PayloadAlert"}))

    assert exc_info.value.status_code == 500
    assert captured_errors == [expected_error]


def test_execute_investigation_tracks_remote_http_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    track_calls: list[tuple[str, str]] = []

    class _TrackContext:
        def __enter__(self) -> None:
            return None

        def __exit__(self, exc_type, exc, tb) -> bool:
            _ = (exc_type, exc, tb)
            return False

    def fake_track(*, entrypoint, trigger_mode, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        track_calls.append((entrypoint.value, trigger_mode.value))
        return _TrackContext()

    monkeypatch.setattr("app.remote.server.track_investigation", fake_track)
    monkeypatch.setattr(
        "app.cli.investigation.resolve_investigation_context",
        lambda **_kwargs: ("alert-name", "pipeline-name", "critical"),
    )
    cli_calls: list[dict[str, Any]] = []

    def fake_run_investigation_cli(**kwargs: Any) -> dict[str, Any]:
        cli_calls.append(kwargs)
        return {"root_cause": "ok"}

    monkeypatch.setattr(
        "app.cli.investigation.run_investigation_cli",
        fake_run_investigation_cli,
    )

    result, alert_name, pipeline_name, severity = remote_server._execute_investigation(
        raw_alert={"description": "cpu spike"},
        alert_name="Production CPU Spike",
        pipeline_name=None,
        severity=None,
    )

    assert result == {"root_cause": "ok"}
    assert (alert_name, pipeline_name, severity) == ("alert-name", "pipeline-name", "critical")
    assert track_calls == [("remote_http", "service_runtime")]
    assert cli_calls == [
        {
            "raw_alert": {"description": "cpu spike"},
            "investigation_metadata": ("alert-name", "pipeline-name", "critical"),
        }
    ]


@pytest.mark.anyio
async def test_investigate_stream_persists_state_on_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: dict[str, Any] = {}
    astream_calls: list[dict[str, Any]] = []

    async def fake_astream_investigation(*args: object, **kwargs: object):
        astream_calls.append(dict(kwargs))
        yield StreamEvent(
            "events",
            data={"data": {"output": {"root_cause": "Schema mismatch", "report": "Fix upstream"}}},
            kind="on_chain_end",
        )
        await asyncio.sleep(0)
        yield StreamEvent("events", data={"data": {}}, kind="on_tool_start")

    def fake_persist_streamed_result(**kwargs: Any) -> None:
        persisted.update(kwargs)

    monkeypatch.setattr("app.config.LLMSettings.from_env", object)
    monkeypatch.setattr(
        "app.cli.investigation.resolve_investigation_context",
        lambda **_kwargs: ("test-alert", "etl_daily_orders", "critical"),
    )
    monkeypatch.setattr(
        "app.pipeline.runners.astream_investigation",
        fake_astream_investigation,
    )
    monkeypatch.setattr(
        "app.remote.server._persist_streamed_result",
        fake_persist_streamed_result,
    )

    response = await investigate_stream(
        InvestigateRequest(raw_alert={"alert_name": "PayloadAlert"})
    )
    iterator = response.body_iterator

    first_chunk = await anext(iterator)
    assert first_chunk

    await iterator.aclose()
    await asyncio.sleep(0)

    assert persisted["alert_name"] == "test-alert"
    assert persisted["pipeline_name"] == "etl_daily_orders"
    assert persisted["severity"] == "critical"
    assert persisted["state"]["root_cause"] == "Schema mismatch"
    assert persisted["state"]["report"] == "Fix upstream"
    assert len(astream_calls) == 1
    call0 = astream_calls[0]
    assert call0["investigation_metadata"] == ("test-alert", "etl_daily_orders", "critical")
    assert call0["raw_alert"].get("alert_name") == "PayloadAlert"


@pytest.mark.anyio
async def test_investigate_stream_captures_streaming_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_errors: list[BaseException] = []
    captured_failures: list[str] = []
    expected_error = RuntimeError("stream failed")

    astream_calls: list[dict[str, Any]] = []

    async def fake_astream_investigation(*args: object, **kwargs: object):
        astream_calls.append(dict(kwargs))
        raise expected_error
        yield StreamEvent("events", data={})

    monkeypatch.setattr("app.config.LLMSettings.from_env", object)
    monkeypatch.setattr(
        "app.cli.investigation.resolve_investigation_context",
        lambda **_kwargs: ("test-alert", "etl_daily_orders", "critical"),
    )
    monkeypatch.setattr(
        "app.pipeline.runners.astream_investigation",
        fake_astream_investigation,
    )
    monkeypatch.setattr(remote_server, "capture_exception", captured_errors.append)
    monkeypatch.setattr(
        remote_server,
        "capture_investigation_failed",
        lambda *, tracker, failure_type=None: (
            captured_failures.append(failure_type or ""),
            tracker,
        )[0],
    )
    monkeypatch.setattr(remote_server, "_persist_streamed_result", lambda **_kwargs: None)

    response = await investigate_stream(
        InvestigateRequest(raw_alert={"alert_name": "PayloadAlert"})
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert any("event: error" in chunk for chunk in chunks)
    assert captured_errors == [expected_error]
    assert captured_failures == ["RuntimeError"]
    assert len(astream_calls) == 1
    assert astream_calls[0]["investigation_metadata"] == (
        "test-alert",
        "etl_daily_orders",
        "critical",
    )
    assert astream_calls[0]["raw_alert"].get("alert_name") == "PayloadAlert"


@pytest.mark.anyio
async def test_lifespan_raises_helpful_error_on_permission_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unwritable = MagicMock()
    unwritable.mkdir.side_effect = PermissionError("Permission denied: '/opt/opensore'")
    unwritable.__str__ = lambda _: "/opt/opensore/investigations"
    unwritable.parent.__str__ = lambda _: "/opt/opensore"

    monkeypatch.setattr(remote_server, "INVESTIGATIONS_DIR", unwritable)

    with pytest.raises(RuntimeError, match="Cannot create investigations directory"):
        async with _lifespan(object()):
            pass


# ---------------------------------------------------------------------------
# _id_to_iso tests
# ---------------------------------------------------------------------------


def test_id_to_iso_converts_valid_id_to_utc_iso_string() -> None:
    # Valid format: YYYYMMDD_HHMMSS_slug
    inv_id = "20260430_120001_alert-name"
    iso_string = remote_server._id_to_iso(inv_id)
    # Should convert to standard ISO format with +00:00 (UTC)
    assert iso_string == "2026-04-30T12:00:01+00:00"


@pytest.mark.parametrize(
    "malformed_id",
    [
        "",
        "invalid",
        "20260430-120001-alert",  # wrong separator
        "abc_def_ghi",  # non-numeric date part
    ],
)
def test_id_to_iso_returns_empty_string_for_malformed_input(malformed_id: str) -> None:
    # Function should fail quietly and return an empty string, not crash
    assert remote_server._id_to_iso(malformed_id) == ""


# ---------------------------------------------------------------------------
# _check_disk_health tests
# ---------------------------------------------------------------------------


def test_check_disk_health_returns_passed_when_below_warn_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disk usage below 85% should return status='passed'."""
    # 50 GiB used out of 100 GiB total = 50%
    fake_usage = _DiskUsage(total=100 * 1024**3, used=50 * 1024**3, free=50 * 1024**3)
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: fake_usage)

    result = _check_disk_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Disk"
    assert result.status == "passed"
    assert "50% used" in result.detail
    assert "50GiB / 100GiB" in result.detail


def test_check_disk_health_returns_warn_when_at_or_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disk usage at or above 85% should return status='warn'."""
    # 90 GiB used out of 100 GiB total = 90%
    fake_usage = _DiskUsage(total=100 * 1024**3, used=90 * 1024**3, free=10 * 1024**3)
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: fake_usage)

    result = _check_disk_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Disk"
    assert result.status == "warn"
    assert "90% used" in result.detail
    assert "90GiB / 100GiB" in result.detail


def test_check_disk_health_returns_missing_when_total_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When disk_usage reports total=0 (e.g. some container environments),
    status should be 'missing' rather than raising a ZeroDivisionError."""
    fake_usage = _DiskUsage(total=0, used=0, free=0)
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: fake_usage)

    result = _check_disk_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Disk"
    assert result.status == "missing"
    assert "Unable to determine disk size" in result.detail


def test_imds_token_returns_none_on_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_url_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise_url_error)
    remote_server._REPORTED_REMOTE_EVENTS.clear()

    assert _imds_token() is None


def test_imds_token_returns_none_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(*args: object, **kwargs: object) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", _raise_timeout)

    assert _imds_token() is None


def test_imds_token_returns_none_on_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", _raise_os_error)

    assert _imds_token() is None


def test_imds_get_returns_none_on_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_url_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise_url_error)
    remote_server._REPORTED_REMOTE_EVENTS.clear()

    assert _imds_get("latest/meta-data/instance-id", token="test-token") is None


def test_imds_token_reports_failure_once(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_url_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise_url_error)
    remote_server._REPORTED_REMOTE_EVENTS.clear()

    with patch("app.remote.server.report_remote_exception") as report:
        assert _imds_token() is None
        assert _imds_token() is None

    report.assert_called_once()
    assert report.call_args.kwargs["component"] == "server"
    assert report.call_args.kwargs["event"] == "imds_token_fetch_failed"
    assert report.call_args.kwargs["severity"] == "info"


def test_imds_token_reports_again_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: list[object] = [
        urllib.error.URLError("connection refused"),
        urllib.error.URLError("connection refused"),
        _UrlopenResponse("test-token"),
        urllib.error.URLError("connection refused"),
    ]

    def _urlopen(*args: object, **kwargs: object) -> object:
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    remote_server._REPORTED_REMOTE_EVENTS.clear()

    with patch("app.remote.server.report_remote_exception") as report:
        assert _imds_token() is None
        assert _imds_token() is None
        assert _imds_token() == "test-token"
        assert _imds_token() is None

    assert report.call_count == 2
    assert report.call_args.kwargs["event"] == "imds_token_fetch_failed"


def test_imds_get_reports_failure_once(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_url_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise_url_error)
    remote_server._REPORTED_REMOTE_EVENTS.clear()

    with patch("app.remote.server.report_remote_exception") as report:
        assert _imds_get("latest/meta-data/instance-id", token="test-token") is None
        assert _imds_get("latest/meta-data/instance-id", token="test-token") is None

    report.assert_called_once()
    assert report.call_args.kwargs["component"] == "server"
    assert report.call_args.kwargs["event"] == "imds_metadata_fetch_failed"
    assert report.call_args.kwargs["severity"] == "info"


def test_imds_get_reports_again_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: list[object] = [
        urllib.error.URLError("connection refused"),
        urllib.error.URLError("connection refused"),
        _UrlopenResponse("i-123"),
        urllib.error.URLError("connection refused"),
    ]

    def _urlopen(*args: object, **kwargs: object) -> object:
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    remote_server._REPORTED_REMOTE_EVENTS.clear()

    with patch("app.remote.server.report_remote_exception") as report:
        assert _imds_get("latest/meta-data/instance-id", token="test-token") is None
        assert _imds_get("latest/meta-data/instance-id", token="test-token") is None
        assert _imds_get("latest/meta-data/instance-id", token="test-token") == "i-123"
        assert _imds_get("latest/meta-data/instance-id", token="test-token") is None

    assert report.call_count == 2
    assert report.call_args.kwargs["event"] == "imds_metadata_fetch_failed"


def test_check_llm_connectivity_reports_bedrock_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeBoto3:
        @staticmethod
        def client(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("bedrock down")

    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3)
    remote_server._REPORTED_REMOTE_EVENTS.clear()

    with patch("app.remote.server.report_remote_exception") as report:
        result = _check_llm_connectivity()

    assert result.status == "failed"
    assert "bedrock down" in result.detail
    report.assert_called_once()
    assert report.call_args.kwargs["component"] == "server"
    assert report.call_args.kwargs["event"] == "llm_connectivity_check_failed"
    assert report.call_args.kwargs["severity"] == "warning"


def test_check_llm_connectivity_reports_again_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[object] = [
        RuntimeError("bedrock down"),
        RuntimeError("bedrock down"),
        None,
        RuntimeError("bedrock down"),
    ]

    class _FakeBedrock:
        def __init__(self, response: object) -> None:
            self._response = response

        def list_foundation_models(self, **_kwargs: object) -> None:
            if isinstance(self._response, BaseException):
                raise self._response

    class _FakeBoto3:
        @staticmethod
        def client(*_args: object, **_kwargs: object) -> object:
            return _FakeBedrock(responses.pop(0))

    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3)
    remote_server._INSTANCE_METADATA["region"] = "us-east-1"
    remote_server._REPORTED_REMOTE_EVENTS.clear()

    with patch("app.remote.server.report_remote_exception") as report:
        assert _check_llm_connectivity().status == "failed"
        assert _check_llm_connectivity().status == "failed"
        assert _check_llm_connectivity().status == "passed"
        assert _check_llm_connectivity().status == "failed"

    assert report.call_count == 2
    assert report.call_args.kwargs["event"] == "llm_connectivity_check_failed"


def test_imds_get_returns_none_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(*args: object, **kwargs: object) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", _raise_timeout)

    assert _imds_get("latest/meta-data/instance-id", token="test-token") is None


def test_imds_get_returns_none_on_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", _raise_os_error)

    assert _imds_get("latest/meta-data/instance-id", token="test-token") is None


def test_check_memory_health_returns_passed_when_below_warn_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeHealthyMeminfoPath:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def exists(self) -> bool:
            return True

        def read_text(self, **_kwargs: object) -> str:
            return "NoiseWithoutSeparator\nMemTotal:       102400 kB\nMemAvailable:    51200 kB\n"

    monkeypatch.setattr("app.remote.server.Path", _FakeHealthyMeminfoPath)
    result = _check_memory_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Memory"
    assert result.status == "passed"
    assert "50% used" in result.detail
    assert "50MiB / 100MiB" in result.detail


def test_check_memory_health_returns_warn_when_at_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeHighUsageMeminfoPath:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def exists(self) -> bool:
            return True

        def read_text(self, **_kwargs: object) -> str:
            return "MemTotal:       102400 kB\nMemAvailable:    10240 kB\n"

    monkeypatch.setattr("app.remote.server.Path", _FakeHighUsageMeminfoPath)
    result = _check_memory_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Memory"
    assert result.status == "warn"
    assert "90% used" in result.detail
    assert "90MiB / 100MiB" in result.detail


def test_check_memory_health_returns_missing_when_proc_file_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeMeminfoPath:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exists(self) -> bool:
            return False

    monkeypatch.setattr("app.remote.server.Path", _FakeMeminfoPath)
    result = _check_memory_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Memory"
    assert result.status == "missing"
    assert "/proc/meminfo unavailable on this platform." in result.detail


def test_check_memory_health_returns_missing_when_memtotal_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeIncompletePath:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def exists(self) -> bool:
            return True

        def read_text(self, **_kwargs: object) -> str:
            return "MemAvailable:    8192 kB\n"

    monkeypatch.setattr("app.remote.server.Path", _FakeIncompletePath)
    result = _check_memory_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Memory"
    assert result.status == "missing"
    assert "Incomplete /proc/meminfo data." in result.detail


def test_check_memory_health_returns_missing_when_memavailable_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeIncompletePath:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def exists(self) -> bool:
            return True

        def read_text(self, **_kwargs: object) -> str:
            return "MemTotal:       16384 kB\n"

    monkeypatch.setattr("app.remote.server.Path", _FakeIncompletePath)
    result = _check_memory_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Memory"
    assert result.status == "missing"
    assert "Incomplete /proc/meminfo data." in result.detail


def test_check_memory_health_returns_missing_on_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeOsErrorPath:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def exists(self) -> bool:
            return True

        def read_text(self, **_kwargs: object) -> str:
            raise OSError("permission denied")

    monkeypatch.setattr("app.remote.server.Path", _FakeOsErrorPath)
    result = _check_memory_health()

    assert isinstance(result, DeepHealthCheck)
    assert result.name == "Memory"
    assert result.status == "missing"
    assert "Unable to read meminfo:" in result.detail
