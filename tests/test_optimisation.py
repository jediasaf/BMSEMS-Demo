"""Optimiser tests: constraints are the product, so they are what we assert."""

from __future__ import annotations

import numpy as np
import pytest

from core.adapters.building.simulation import ComfortBand, ZoneThermalParams
from core.common.schemas import Recommendation
from core.optimisation.bms import SetpointOptimiser, SetpointProblem
from core.optimisation.ems import FlexibleResource, LoadShiftProblem, PeakOptimiser
from core.optimisation.validation import DEFAULT_LIMITS, ControlValidator
from core.provenance import optimised

HORIZON = 48


def _ems_problem(
    *,
    cap_kw: float = 152.0,
    hvac_budget: float = 25.0,
    headroom_after_session: bool = True,
    horizon: int = HORIZON,
) -> LoadShiftProblem:
    base = np.full(horizon, 85.0)
    injected = np.zeros(horizon)
    injected[16:28] = 70.0  # a charging session in the middle of the horizon
    headroom = np.zeros(horizon)
    if headroom_after_session:
        headroom[28:] = 40.0
    return LoadShiftProblem(
        facility_id="t",
        forecast_kw=base,
        injected_kw=injected,
        cap_kw=cap_kw,
        hvac=FlexibleResource(
            resource_id="F1",
            label="HVAC",
            kind="hvac",
            available_kw=np.full(horizon, 12.0),
            energy_budget_kwh=hvac_budget,
            ramp_kw=5.0,
        ),
        ev=FlexibleResource(
            resource_id="F4",
            label="EV",
            kind="ev",
            available_kw=injected.copy(),
            headroom_kw=headroom,
            shiftable=True,
        ),
    )


# -- EMS -------------------------------------------------------------------
def test_peak_is_brought_under_the_cap() -> None:
    result = PeakOptimiser().solve(_ems_problem())
    assert result.solved
    assert result.optimised_peak_kw < result.baseline_peak_kw
    assert result.residual_overload_kw == pytest.approx(0.0, abs=1e-3)
    assert result.feasible_within_cap


def test_ev_energy_is_conserved_exactly() -> None:
    result = PeakOptimiser().solve(_ems_problem())
    assert sum(result.ev_reduction_kw) == pytest.approx(sum(result.ev_recovery_kw), abs=1e-4)


def test_recovery_never_precedes_curtailment() -> None:
    """Energy balance alone does not stop the solver charging absent cars."""
    result = PeakOptimiser().solve(_ems_problem())
    curtailed = np.cumsum(result.ev_reduction_kw)
    recovered = np.cumsum(result.ev_recovery_kw)
    assert (recovered <= curtailed + 1e-6).all()


def test_hvac_energy_budget_is_respected() -> None:
    result = PeakOptimiser().solve(_ems_problem(cap_kw=105.0, hvac_budget=8.0))
    assert result.hvac_energy_kwh <= 8.0 + 1e-6


def test_reductions_never_exceed_what_is_available() -> None:
    problem = _ems_problem()
    result = PeakOptimiser().solve(problem)
    assert (np.asarray(result.ev_reduction_kw) <= problem.ev.available_kw + 1e-6).all()
    assert (np.asarray(result.hvac_reduction_kw) <= problem.hvac.available_kw + 1e-6).all()
    assert (np.asarray(result.hvac_reduction_kw) >= -1e-9).all()


def test_no_flexibility_means_an_honest_failure_not_a_crash() -> None:
    """The operator must still get the best achievable answer."""
    problem = _ems_problem(cap_kw=60.0, headroom_after_session=False)
    problem.hvac.available_kw = np.zeros(HORIZON)
    result = PeakOptimiser().solve(problem)
    assert result.solved
    assert not result.feasible_within_cap
    assert result.residual_overload_kw > 0
    assert any("cannot fully clear" in note for note in result.notes)


def test_a_quiet_day_needs_no_action() -> None:
    problem = _ems_problem(cap_kw=400.0)
    result = PeakOptimiser().solve(problem)
    assert result.hvac_energy_kwh == pytest.approx(0.0, abs=1e-6)
    assert result.ev_energy_shifted_kwh == pytest.approx(0.0, abs=1e-6)


def test_result_is_deterministic() -> None:
    a = PeakOptimiser().solve(_ems_problem())
    b = PeakOptimiser().solve(_ems_problem())
    assert a.optimised_peak_kw == pytest.approx(b.optimised_peak_kw, rel=1e-6)


def test_constraints_are_reported_for_the_operator() -> None:
    result = PeakOptimiser().solve(_ems_problem())
    assert any("conserv" in c or "recovered later" in c for c in result.constraints)
    assert any("causality" in c for c in result.constraints)


# -- BMS -------------------------------------------------------------------
def _bms_problem(**kwargs) -> SetpointProblem:
    hours = np.arange(HORIZON) * 0.25
    occupancy = np.clip(np.sin(np.pi * (hours - 7) / 11), 0, 1)
    outdoor = 26 + 5 * np.sin(2 * np.pi * (hours - 9) / 24)
    baseline = np.where(occupancy > 0.15, 23.0, 27.0)
    defaults = {
        "outdoor_temp_c": outdoor,
        "occupancy": occupancy,
        "baseline_setpoint_c": baseline,
        "baseline_zone_temp_c": np.full(HORIZON, 23.0),
        "params": ZoneThermalParams(floor_area_m2=1200.0),
        "comfort": ComfortBand(),
        "initial_zone_temp_c": 23.0,
    }
    defaults.update(kwargs)
    return SetpointProblem(**defaults)  # type: ignore[arg-type]


def test_setpoints_stay_inside_their_range() -> None:
    problem = _bms_problem()
    result = SetpointOptimiser().solve(problem)
    assert result.solved
    setpoints = np.asarray(result.setpoints_c)
    assert (setpoints >= problem.setpoint_min_c - 1e-6).all()
    assert (setpoints <= problem.setpoint_max_c + 1e-6).all()


def test_rate_limit_is_respected() -> None:
    problem = _bms_problem(rate_limit_k=0.5)
    result = SetpointOptimiser().solve(problem)
    assert result.max_step_change_k <= 0.5 + 1e-6


def test_a_tighter_rate_limit_cannot_move_faster() -> None:
    loose = SetpointOptimiser().solve(_bms_problem(rate_limit_k=2.0))
    tight = SetpointOptimiser().solve(_bms_problem(rate_limit_k=0.25))
    assert tight.max_step_change_k <= loose.max_step_change_k + 1e-6


def test_a_heavier_comfort_weight_buys_less_slack() -> None:
    relaxed = SetpointOptimiser().solve(_bms_problem(lambda_comfort=5.0))
    strict = SetpointOptimiser().solve(_bms_problem(lambda_comfort=5000.0))
    assert strict.comfort_slack_kh <= relaxed.comfort_slack_kh + 1e-6


def test_the_optimiser_reports_what_it_assumed() -> None:
    result = SetpointOptimiser().solve(_bms_problem())
    assert any("nonlinear simulator" in note for note in result.notes)
    assert result.constraints


def test_cooling_never_exceeds_installed_capacity() -> None:
    """The plant is finite, and a plan that needs more than it has is a wish.

    Driven at 45 C with a small chiller, an unconstrained model would happily
    plan its way to a comfortable zone. The constrained one cannot, and says
    so through comfort slack instead of through an impossible power profile.
    """
    params = ZoneThermalParams(floor_area_m2=1200.0, cooling_capacity_w_m2=15.0)
    problem = _bms_problem(
        params=params,
        outdoor_temp_c=np.full(HORIZON, 45.0),
        occupancy=np.ones(HORIZON),
    )
    result = SetpointOptimiser().solve(problem)
    assert result.solved
    capacity_kw_e = params.cooling_capacity_w / 1000.0 / 1.2  # 1.2 is the COP floor
    assert max(result.predicted_hvac_kw) <= capacity_kw_e + 1e-6
    assert result.comfort_slack_kh > 0, "an undersized plant should report the shortfall"


def test_the_optimiser_models_the_structure_not_just_the_air() -> None:
    """A single-node model would be blind to thermal mass.

    Starting the structure 6 K colder than the air is a real store of cooling.
    An optimiser that only knows the air node cannot see it and plans the same
    trajectory either way.
    """
    warm_structure = SetpointOptimiser().solve(_bms_problem(initial_mass_temp_c=29.0))
    cold_structure = SetpointOptimiser().solve(_bms_problem(initial_mass_temp_c=17.0))
    assert warm_structure.solved and cold_structure.solved
    assert sum(warm_structure.predicted_hvac_kw) > sum(cold_structure.predicted_hvac_kw)


# -- validation gate -------------------------------------------------------
def _recommendation(point: str, current: float, proposed: float) -> Recommendation:
    return Recommendation(
        recommendation_id="r1",
        timestamp="2017-08-24T12:00:00",
        asset_id="t",
        zone_id="Z",
        module="BMS",
        action="a",
        point=point,
        current_value=current,
        proposed_value=proposed,
        unit="°C",
        rationale="r",
        confidence=0.8,
        provenance=optimised(units="°C", processing="p"),
    )


def test_a_reasonable_setpoint_change_passes() -> None:
    outcome = ControlValidator().validate(_recommendation("zone_cooling_setpoint_c", 23.0, 24.0))
    assert outcome.valid
    assert outcome.action is not None
    assert outcome.action.mode == "SIMULATION"


def test_a_point_outside_the_allowlist_is_blocked() -> None:
    outcome = ControlValidator().validate(_recommendation("main_breaker", 0.0, 1.0))
    assert not outcome.valid
    assert outcome.action is None
    assert any(c["check"] == "point_is_allowlisted" and not c["passed"] for c in outcome.checks)


def test_out_of_range_is_blocked() -> None:
    outcome = ControlValidator().validate(_recommendation("zone_cooling_setpoint_c", 23.0, 40.0))
    assert not outcome.valid


def test_a_change_beyond_the_rate_limit_is_blocked() -> None:
    limit = DEFAULT_LIMITS["zone_cooling_setpoint_c"].rate_limit
    outcome = ControlValidator().validate(
        _recommendation("zone_cooling_setpoint_c", 20.0, 20.0 + limit + 0.5)
    )
    assert not outcome.valid
    assert any(c["check"] == "within_rate_limit" and not c["passed"] for c in outcome.checks)


def test_real_actuation_is_always_refused() -> None:
    outcome = ControlValidator().validate(
        _recommendation("zone_cooling_setpoint_c", 23.0, 24.0), simulation_mode=False
    )
    assert not outcome.valid
    assert outcome.mode == "BLOCKED"
    assert any("never will be" in m for m in outcome.messages)


# -- the simulator's veto --------------------------------------------------
def _verdict(**overrides):
    from apps.api.services.bms import acceptance_verdict

    base = {"energy_kwh": 100.0, "peak_kw": 10.0, "comfort_violation_kh": 0.0}
    ai = {"energy_kwh": 90.0, "peak_kw": 9.0, "comfort_violation_kh": 0.0}
    ai.update(overrides)
    delta = {k: ai[k] - base[k] for k in base}
    delta_pct = {k: 100.0 * (ai[k] - base[k]) / base[k] if base[k] else None for k in base}
    return acceptance_verdict(True, base, ai, delta, delta_pct)


def test_a_genuine_improvement_is_accepted() -> None:
    assert _verdict()["accepted"]


def test_a_proposal_that_uses_more_energy_is_rejected() -> None:
    verdict = _verdict(energy_kwh=101.0)
    assert not verdict["accepted"]
    assert any("energy" in reason for reason in verdict["failed"])
    assert "no saving is claimed" in verdict["reason"]


def test_a_proposal_that_raises_the_peak_is_rejected() -> None:
    """The failure mode that actually occurred: energy down, peak far up."""
    verdict = _verdict(energy_kwh=99.0, peak_kw=15.0)
    assert not verdict["accepted"]
    assert any("peak" in reason for reason in verdict["failed"])


def test_a_proposal_that_costs_comfort_is_rejected() -> None:
    verdict = _verdict(comfort_violation_kh=3.0)
    assert not verdict["accepted"]
    assert any("comfort" in reason for reason in verdict["failed"])


def test_an_unsolved_optimisation_is_never_accepted() -> None:
    from apps.api.services.bms import acceptance_verdict

    kpis = {"energy_kwh": 100.0, "peak_kw": 10.0, "comfort_violation_kh": 0.0}
    verdict = acceptance_verdict(False, kpis, kpis, {"energy_kwh": 0.0}, {"peak_kw": 0.0})
    assert not verdict["accepted"]


def test_the_gate_never_claims_it_actuated_anything() -> None:
    assert "no code path to a real actuator" in _verdict()["note"]
