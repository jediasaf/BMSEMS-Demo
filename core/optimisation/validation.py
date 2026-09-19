"""Control validation: the gate between a recommendation and any actuation.

Real historical mode is strictly read-only. The only thing EcoTwin will ever
execute is a simulated control action, and even that must pass every check
here first. The checks are deliberately boring and individually cheap, because
a safety gate that is clever is a safety gate nobody trusts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from core.common.schemas import ControlAction, Recommendation


@dataclass(frozen=True)
class ControlLimits:
    """Per-point limits. In production these come from the BMS point database."""

    point: str
    unit: str
    minimum: float
    maximum: float
    #: Largest permitted change from the current value, per command.
    rate_limit: float
    #: Points that may be written at all. Anything absent is read-only.
    writable: bool = True
    comfort_lower_c: float | None = None
    comfort_upper_c: float | None = None


#: The allowlist. A point that is not here cannot be written, in any mode.
DEFAULT_LIMITS: dict[str, ControlLimits] = {
    "zone_cooling_setpoint_c": ControlLimits(
        point="zone_cooling_setpoint_c",
        unit="°C",
        minimum=20.0,
        maximum=26.0,
        rate_limit=2.0,
        comfort_lower_c=21.0,
        comfort_upper_c=24.0,
    ),
    "hvac_flexible_reduction_kw": ControlLimits(
        point="hvac_flexible_reduction_kw",
        unit="kW",
        minimum=0.0,
        maximum=1.0e6,
        rate_limit=1.0e6,
    ),
    "ev_charging_limit_kw": ControlLimits(
        point="ev_charging_limit_kw",
        unit="kW",
        minimum=0.0,
        maximum=1.0e6,
        rate_limit=1.0e6,
    ),
}


@dataclass
class ValidationOutcome:
    valid: bool
    action: ControlAction | None
    checks: list[dict[str, object]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    mode: Literal["SIMULATION", "BLOCKED"] = "BLOCKED"

    def failures(self) -> list[dict[str, object]]:
        return [c for c in self.checks if not c["passed"]]


class ControlValidator:
    """Validates a recommendation into an executable simulated action."""

    def __init__(self, limits: dict[str, ControlLimits] | None = None) -> None:
        self.limits = limits or DEFAULT_LIMITS

    def validate(
        self,
        recommendation: Recommendation,
        *,
        simulation_mode: bool = True,
    ) -> ValidationOutcome:
        checks: list[dict[str, object]] = []
        messages: list[str] = []

        def record(name: str, passed: bool, detail: str) -> None:
            checks.append({"check": name, "passed": passed, "detail": detail})
            if not passed:
                messages.append(f"{name}: {detail}")

        limit = self.limits.get(recommendation.point)
        record(
            "point_is_allowlisted",
            limit is not None,
            f"{recommendation.point!r} is "
            + ("on the writable allowlist" if limit else "not a writable point"),
        )
        if limit is None:
            return ValidationOutcome(valid=False, action=None, checks=checks, messages=messages)

        record(
            "point_is_writable",
            limit.writable,
            "point is writable" if limit.writable else "point is marked read-only",
        )
        proposed = recommendation.proposed_value
        record(
            "within_min_max",
            limit.minimum <= proposed <= limit.maximum,
            f"{proposed} {limit.unit} against [{limit.minimum}, {limit.maximum}]",
        )
        delta = abs(proposed - recommendation.current_value)
        record(
            "within_rate_limit",
            delta <= limit.rate_limit + 1e-9,
            f"change of {delta:.3g} {limit.unit} against a limit of "
            f"{limit.rate_limit:.3g} {limit.unit}",
        )
        if limit.comfort_lower_c is not None and limit.comfort_upper_c is not None:
            # A cooling setpoint above the comfort upper bound would guarantee a
            # violation rather than risk one.
            inside = limit.comfort_lower_c - 0.5 <= proposed <= limit.comfort_upper_c + 2.0
            record(
                "comfort_envelope",
                inside,
                f"{proposed} °C against a comfort envelope of "
                f"[{limit.comfort_lower_c}, {limit.comfort_upper_c}] °C "
                "(+2 K unoccupied allowance)",
            )
        record(
            "simulation_mode_only",
            simulation_mode,
            (
                "target is a simulator"
                if simulation_mode
                else "real actuation is not implemented and never will be in this prototype"
            ),
        )

        valid = all(bool(c["passed"]) for c in checks)
        action = (
            ControlAction(
                action_id=f"act-{recommendation.recommendation_id}",
                asset_id=recommendation.asset_id,
                zone_id=recommendation.zone_id,
                point=recommendation.point,
                value=proposed,
                unit=limit.unit,
                mode="SIMULATION",
                validated=True,
                validation_messages=[],
            )
            if valid
            else None
        )
        return ValidationOutcome(
            valid=valid,
            action=action,
            checks=checks,
            messages=messages,
            mode="SIMULATION" if valid else "BLOCKED",
        )
