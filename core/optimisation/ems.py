"""Flexible-load optimisation against a transformer constraint.

The question this answers: a transformer is forecast to exceed its rating; what
is the smallest, least disruptive change to the two flexible resources that
keeps it under the limit?

V1 controls exactly two resources, deliberately:

1. **HVAC flexible demand.** A genuine *reduction*, bought from the building's
   thermal mass. It is not recovered later, so it is bounded by a comfort
   energy budget rather than an energy-balance constraint.
2. **EV / flexible charging.** A *shift*, not a shed. Every kWh curtailed must
   be delivered later in the horizon, within the charger's spare capacity. An
   optimiser that simply refuses to charge cars would trivially solve the
   constraint and would be rejected by anyone who runs a car park.

Formulation (linear, solved by CVXPY to a global optimum)::

    net_t = forecast_t + injected_t - h_t - e_t + r_t

    min   peak
        + lambda_comfort * sum(h_t) / 4          (kWh of HVAC reduction)
        + lambda_shift   * sum(e_t) / 4          (kWh of EV energy deferred)
        + lambda_move    * sum |h_t - h_{t-1}|
        + BIG            * sum(overload_t)

    s.t.  net_t  <= cap_kw + overload_t          overload_t >= 0
          peak   >= net_t
          0 <= h_t <= hvac_available_t
          0 <= e_t <= ev_available_t
          0 <= r_t <= ev_headroom_t
          sum(r_t) == sum(e_t)                   EV energy is conserved
          cumsum(r)_t <= cumsum(e)_t             and cannot be recovered early
          sum(h_t) / 4 <= hvac_energy_budget_kwh
          |h_t - h_{t-1}| <= hvac_ramp_kw

The overload term is a penalised slack rather than a hard bound, so the problem
is always feasible: if the constraint genuinely cannot be met with the
available flexibility, the optimiser returns the best achievable state and says
so, instead of failing and leaving the operator with nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np

log = logging.getLogger(__name__)

STEPS_PER_HOUR = 4
#: Penalty on residual overload. Large enough to dominate, small enough to keep
#: the problem numerically well behaved.
OVERLOAD_PENALTY = 5.0e3


@dataclass
class FlexibleResource:
    """One controllable resource over the horizon."""

    resource_id: str
    label: str
    kind: str  # "hvac" | "ev"
    #: Maximum reduction available at each step, in kW.
    available_kw: np.ndarray
    #: For shiftable resources, spare capacity to catch up later, in kW.
    headroom_kw: np.ndarray | None = None
    #: For reducible resources, the total energy that may be given up, in kWh.
    energy_budget_kwh: float | None = None
    #: Maximum change between consecutive steps, in kW.
    ramp_kw: float | None = None
    shiftable: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class LoadShiftProblem:
    facility_id: str
    #: Forecast site demand over the horizon, in kW.
    forecast_kw: np.ndarray
    #: Scenario-injected load added on top of the forecast, in kW.
    injected_kw: np.ndarray
    #: Demand that corresponds to 100% transformer loading, in kW.
    cap_kw: float
    hvac: FlexibleResource
    ev: FlexibleResource
    lambda_comfort: float = 1.6
    lambda_shift: float = 0.9
    lambda_move: float = 0.35
    #: Aim slightly below the cap so a small forecast error does not breach it.
    safety_margin_pct: float = 3.0

    def horizon(self) -> int:
        return int(len(self.forecast_kw))

    def target_kw(self) -> float:
        return self.cap_kw * (1.0 - self.safety_margin_pct / 100.0)


@dataclass
class LoadShiftResult:
    status: str
    solved: bool
    feasible_within_cap: bool
    hvac_reduction_kw: list[float]
    ev_reduction_kw: list[float]
    ev_recovery_kw: list[float]
    baseline_kw: list[float]
    optimised_kw: list[float]
    baseline_peak_kw: float
    optimised_peak_kw: float
    peak_reduction_kw: float
    hvac_energy_kwh: float
    ev_energy_shifted_kwh: float
    residual_overload_kw: float
    cap_kw: float
    target_kw: float
    solver: str
    solve_time_s: float
    constraints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class PeakOptimiser:
    def solve(self, problem: LoadShiftProblem) -> LoadShiftResult:
        horizon = problem.horizon()
        forecast = np.asarray(problem.forecast_kw, dtype=float)
        injected = np.asarray(problem.injected_kw, dtype=float)
        baseline = forecast + injected
        target = problem.target_kw()

        hvac_available = np.clip(np.asarray(problem.hvac.available_kw, dtype=float), 0, None)
        ev_available = np.clip(np.asarray(problem.ev.available_kw, dtype=float), 0, None)
        ev_headroom = np.clip(
            np.asarray(
                problem.ev.headroom_kw if problem.ev.headroom_kw is not None else np.zeros(horizon),
                dtype=float,
            ),
            0,
            None,
        )

        h = cp.Variable(horizon, nonneg=True, name="hvac_reduction")
        e = cp.Variable(horizon, nonneg=True, name="ev_reduction")
        r = cp.Variable(horizon, nonneg=True, name="ev_recovery")
        overload = cp.Variable(horizon, nonneg=True, name="overload")
        peak = cp.Variable(nonneg=True, name="peak")

        net = baseline - h - e + r

        constraints = [
            h <= hvac_available,
            e <= ev_available,
            r <= ev_headroom,
            net <= target + overload,
            peak >= cp.max(net),
            # EV load is deferred, never destroyed.
            cp.sum(r) == cp.sum(e),
            # ... and deferral precedes recovery. Without this the solver
            # happily "recovers" energy hours before it curtails any, which
            # reads as charging cars that have not arrived yet. Energy balance
            # alone does not imply causality.
            cp.cumsum(r) <= cp.cumsum(e),
        ]
        if problem.hvac.energy_budget_kwh is not None:
            constraints.append(cp.sum(h) / STEPS_PER_HOUR <= problem.hvac.energy_budget_kwh)
        if problem.hvac.ramp_kw is not None and horizon > 1:
            constraints.append(cp.abs(cp.diff(h)) <= problem.hvac.ramp_kw)

        objective = cp.Minimize(
            peak
            + problem.lambda_comfort * cp.sum(h) / STEPS_PER_HOUR
            + problem.lambda_shift * cp.sum(e) / STEPS_PER_HOUR
            + problem.lambda_move * (cp.sum(cp.abs(cp.diff(h))) if horizon > 1 else 0)
            + OVERLOAD_PENALTY * cp.sum(overload)
        )

        prob = cp.Problem(objective, constraints)
        try:
            prob.solve(solver=cp.CLARABEL)
        except Exception as exc:  # pragma: no cover - solver fallback
            log.warning("CLARABEL failed (%s); retrying with SCS", exc)
            prob.solve(solver=cp.SCS)

        solved = prob.status in ("optimal", "optimal_inaccurate") and h.value is not None
        if not solved:
            return LoadShiftResult(
                status=str(prob.status),
                solved=False,
                feasible_within_cap=False,
                hvac_reduction_kw=[0.0] * horizon,
                ev_reduction_kw=[0.0] * horizon,
                ev_recovery_kw=[0.0] * horizon,
                baseline_kw=[round(float(v), 3) for v in baseline],
                optimised_kw=[round(float(v), 3) for v in baseline],
                baseline_peak_kw=round(float(baseline.max()), 3),
                optimised_peak_kw=round(float(baseline.max()), 3),
                peak_reduction_kw=0.0,
                hvac_energy_kwh=0.0,
                ev_energy_shifted_kwh=0.0,
                residual_overload_kw=round(float(max(baseline.max() - target, 0.0)), 3),
                cap_kw=problem.cap_kw,
                target_kw=target,
                solver="none",
                solve_time_s=0.0,
                notes=["Optimisation did not converge; no action is proposed."],
            )

        h_val = np.clip(np.asarray(h.value, dtype=float), 0, None)
        e_val = np.clip(np.asarray(e.value, dtype=float), 0, None)
        r_val = np.clip(np.asarray(r.value, dtype=float), 0, None)
        optimised = baseline - h_val - e_val + r_val
        residual = float(max(optimised.max() - problem.cap_kw, 0.0))

        return LoadShiftResult(
            status=str(prob.status),
            solved=True,
            feasible_within_cap=residual <= 1e-3,
            hvac_reduction_kw=[round(float(v), 4) for v in h_val],
            ev_reduction_kw=[round(float(v), 4) for v in e_val],
            ev_recovery_kw=[round(float(v), 4) for v in r_val],
            baseline_kw=[round(float(v), 3) for v in baseline],
            optimised_kw=[round(float(v), 3) for v in optimised],
            baseline_peak_kw=round(float(baseline.max()), 3),
            optimised_peak_kw=round(float(optimised.max()), 3),
            peak_reduction_kw=round(float(baseline.max() - optimised.max()), 3),
            hvac_energy_kwh=round(float(h_val.sum()) / STEPS_PER_HOUR, 4),
            ev_energy_shifted_kwh=round(float(e_val.sum()) / STEPS_PER_HOUR, 4),
            residual_overload_kw=round(residual, 3),
            cap_kw=problem.cap_kw,
            target_kw=round(target, 3),
            solver=str(prob.solver_stats.solver_name if prob.solver_stats else "unknown"),
            solve_time_s=round(
                float(prob.solver_stats.solve_time or 0.0) if prob.solver_stats else 0.0, 4
            ),
            constraints=[
                f"site demand ≤ {target:.1f} kW "
                f"({problem.safety_margin_pct:.0f}% below the {problem.cap_kw:.0f} kW cap)",
                "HVAC reduction within the available flexibility at each step",
                (
                    f"HVAC energy given up ≤ {problem.hvac.energy_budget_kwh:.1f} kWh"
                    if problem.hvac.energy_budget_kwh is not None
                    else "HVAC energy unbounded"
                ),
                "EV curtailment within the charging load present at each step",
                "every curtailed EV kWh recovered later within charger headroom",
                "recovery never precedes curtailment (cumulative causality)",
            ],
            notes=[
                "HVAC flexibility is a reduction bought from thermal mass and is "
                "bounded by a comfort energy budget.",
                "EV flexibility is a shift: total delivered energy is unchanged, and "
                "no energy is recovered before it has been deferred.",
            ]
            + (
                []
                if residual <= 1e-3
                else [
                    f"Available flexibility cannot fully clear the constraint; "
                    f"{residual:.1f} kW of overload remains."
                ]
            ),
        )
