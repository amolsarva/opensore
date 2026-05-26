"""Tests for SloBurnRateTool."""

from __future__ import annotations

from app.tools.SloBurnRateTool import slo_burn_rate


def test_tool_metadata() -> None:
    assert slo_burn_rate.name == "slo_burn_rate"
    assert slo_burn_rate.source == "knowledge"
    assert slo_burn_rate.is_available({}) is True


def test_zero_total_requests_error() -> None:
    result = slo_burn_rate.run(slo_target=0.999, error_count=10, total_requests=0)
    assert result["available"] is False


def test_invalid_slo_target_error() -> None:
    result = slo_burn_rate.run(slo_target=1.5, error_count=1, total_requests=100)
    assert result["available"] is False
    result2 = slo_burn_rate.run(slo_target=0.0, error_count=1, total_requests=100)
    assert result2["available"] is False


def test_perfect_reliability() -> None:
    result = slo_burn_rate.run(slo_target=0.999, error_count=0, total_requests=10000)
    assert result["available"] is True
    assert result["compliance_pct"] == 100.0
    assert result["burn_rate"] == 0.0
    assert result["error_budget_pct_remaining"] == 100.0
    assert result["time_to_exhaustion_hours"] is None
    assert result["is_burning_fast"] is False


def test_burn_rate_one_means_on_budget() -> None:
    # Exactly consuming the error budget: 0.1% errors over 720h window
    # error_budget_fraction = 0.001; if observed_hours = window_hours,
    # actual_error_rate = 0.001 → burn_rate = 1.0
    result = slo_burn_rate.run(
        slo_target=0.999,
        error_count=1000,
        total_requests=1_000_000,
        window_hours=720.0,
    )
    assert result["available"] is True
    assert abs(result["burn_rate"] - 1.0) < 0.01
    assert result["compliance_pct"] == pytest_approx(99.9)


def test_fast_burn_rate_flagged() -> None:
    # 1000 errors in 1000 requests observed over 1 hour, SLO 99.9%, 720h window
    # error_rate = 1.0; budget_fraction = 0.001; budget_for_1h = 0.001/720
    # burn_rate = 1.0 / (0.001/720) = 720000 >> 14.4
    result = slo_burn_rate.run(
        slo_target=0.999,
        error_count=1000,
        total_requests=1000,
        window_hours=720.0,
        observed_hours=1.0,
    )
    assert result["available"] is True
    assert result["is_burning_fast"] is True
    assert result["time_to_exhaustion_hours"] is not None
    assert result["time_to_exhaustion_hours"] < 1.0


def test_error_budget_minutes_for_99_9() -> None:
    # 99.9% SLO over 720h = 0.1% error budget = 43.2 minutes
    result = slo_burn_rate.run(
        slo_target=0.999,
        error_count=0,
        total_requests=1000,
        window_hours=720.0,
    )
    assert abs(result["error_budget_minutes"] - 43.2) < 0.1


def test_partial_budget_consumed() -> None:
    # 50% budget consumed: error_rate = 0.0005, budget_fraction = 0.001
    result = slo_burn_rate.run(
        slo_target=0.999,
        error_count=500,
        total_requests=1_000_000,
        window_hours=720.0,
    )
    assert result["available"] is True
    assert abs(result["error_budget_pct_remaining"] - 50.0) < 1.0


# ---------------------------------------------------------------------------
# pytest approx helper
# ---------------------------------------------------------------------------

def pytest_approx(val: float, rel: float = 1e-3) -> object:
    """Simple approximate comparison helper (avoids pytest import at module level)."""
    class Approx:
        def __eq__(self, other: object) -> bool:
            if not isinstance(other, (int, float)):
                return NotImplemented
            return abs(other - val) <= rel * abs(val)
        def __repr__(self) -> str:
            return f"~{val}"
    return Approx()
