"""SLO burn rate calculator — compute error budget, burn rate, and time-to-exhaustion."""

from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool


class SloBurnRateTool(BaseTool):
    """Calculate SLO burn rate and error budget status from raw SLI measurements."""

    name = "slo_burn_rate"
    source = "knowledge"
    description = (
        "Calculate SLO burn rate, error budget remaining, and projected time-to-exhaustion "
        "from raw SLI measurements. Use when investigating SLO breaches or early-warning "
        "degradation to quantify how quickly the error budget is burning."
    )
    use_cases = [
        "Quantifying error budget depletion speed during a production incident",
        "Determining how long before an SLO is breached at the current error rate",
        "Comparing burn rate across multiple services to prioritise response",
        "Projecting time-to-exhaustion for escalation decisions",
        "Assessing whether a rolling SLO window will survive the current incident",
    ]
    requires = ["slo_target", "error_count", "total_requests"]
    input_schema = {
        "type": "object",
        "properties": {
            "slo_target": {
                "type": "number",
                "description": "SLO target as a fraction (e.g. 0.999 for 99.9%, 0.995 for 99.5%)",
            },
            "window_hours": {
                "type": "number",
                "default": 720.0,
                "description": "SLO measurement window in hours (default 720 = 30 days)",
            },
            "error_count": {
                "type": "number",
                "description": "Number of failed/errored requests in the observed period",
            },
            "total_requests": {
                "type": "number",
                "description": "Total requests in the observed period",
            },
            "observed_hours": {
                "type": "number",
                "description": (
                    "Duration over which error_count and total_requests were observed. "
                    "Defaults to window_hours. Use a shorter value (e.g. 1.0) when "
                    "reporting on the most recent hour's data."
                ),
            },
        },
        "required": ["slo_target", "error_count", "total_requests"],
    }
    outputs = {
        "burn_rate": "Burn rate multiplier (1.0 = on-budget; >1.0 = burning faster than allowed)",
        "error_budget_pct_remaining": "Percentage of error budget remaining in the SLO window",
        "time_to_exhaustion_hours": "Hours until budget is exhausted at current rate (None if no errors)",
        "compliance_pct": "Actual reliability % in the observed window",
        "error_budget_minutes": "Total allowable downtime/error minutes in the SLO window",
        "is_burning_fast": "True when burn_rate > 14.4 (exhausts monthly budget in 2 hours)",
    }

    def is_available(self, sources: dict) -> bool:  # noqa: ARG002
        return True

    def extract_params(self, sources: dict) -> dict[str, Any]:  # noqa: ARG002
        return {
            "slo_target": 0.999,
            "window_hours": 720.0,
            "error_count": 0,
            "total_requests": 1,
        }

    def run(
        self,
        slo_target: float,
        error_count: float,
        total_requests: float,
        window_hours: float = 720.0,
        observed_hours: float | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if total_requests <= 0:
            return {
                "source": "knowledge",
                "available": False,
                "error": "total_requests must be > 0.",
            }
        if not (0.0 < slo_target < 1.0):
            return {
                "source": "knowledge",
                "available": False,
                "error": "slo_target must be between 0 and 1 exclusive (e.g. 0.999).",
            }
        if window_hours <= 0:
            return {
                "source": "knowledge",
                "available": False,
                "error": "window_hours must be > 0.",
            }

        obs_hours = observed_hours or window_hours
        error_budget_fraction = 1.0 - slo_target
        error_budget_minutes = error_budget_fraction * window_hours * 60

        actual_error_rate = error_count / total_requests
        compliance_pct = (1.0 - actual_error_rate) * 100

        # Normalise observed rate to the full window to compute burn rate
        # budget allowed in obs_hours = error_budget_fraction * (obs_hours / window_hours)
        budget_for_obs = error_budget_fraction * (obs_hours / window_hours)
        burn_rate = actual_error_rate / budget_for_obs if budget_for_obs > 0 else float("inf")

        # Fraction of total window budget consumed so far
        budget_consumed_fraction = actual_error_rate / error_budget_fraction if error_budget_fraction > 0 else float("inf")
        error_budget_pct_remaining = max(0.0, (1.0 - budget_consumed_fraction) * 100)

        # Time-to-exhaustion at the current rate
        time_to_exhaustion_hours: float | None
        if actual_error_rate <= 0:
            time_to_exhaustion_hours = None  # infinite runway
        else:
            remaining_budget_fraction = error_budget_fraction * (error_budget_pct_remaining / 100)
            rate_per_hour = actual_error_rate / obs_hours
            if rate_per_hour > 0:
                time_to_exhaustion_hours = remaining_budget_fraction / rate_per_hour
            else:
                time_to_exhaustion_hours = None

        safe_burn_rate = burn_rate if burn_rate != float("inf") else None
        is_burning_fast = (burn_rate > 14.4) if burn_rate != float("inf") else True

        return {
            "source": "knowledge",
            "available": True,
            "slo_target_pct": slo_target * 100,
            "compliance_pct": round(compliance_pct, 4),
            "burn_rate": round(safe_burn_rate, 3) if safe_burn_rate is not None else None,
            "error_budget_pct_remaining": round(error_budget_pct_remaining, 2),
            "error_budget_minutes": round(error_budget_minutes, 1),
            "time_to_exhaustion_hours": (
                round(time_to_exhaustion_hours, 1)
                if time_to_exhaustion_hours is not None
                else None
            ),
            "is_burning_fast": is_burning_fast,
            "error_count": error_count,
            "total_requests": total_requests,
            "observed_hours": obs_hours,
            "window_hours": window_hours,
        }


slo_burn_rate = SloBurnRateTool()
