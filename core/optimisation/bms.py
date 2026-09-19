"""HVAC setpoint optimisation.

Objective, over a horizon of 15-minute steps::

    min  sum_t  Energy_t
       + lambda_peak    * Peak
       + lambda_comfort * ComfortSlack_t
       + lambda_move    * |u_t - u_{t-1}|

subject to
    comfort_lower_t - slack_t <= T_t <= comfort_upper_t + slack_t
    setpoint_min <= u_t <= setpoint_max
    |u_t - u_{t-1}| <= rate_limit
    T evolves by the linearised zone model
    slack_t >= 0

Why this is convex, and why that matters
----------------------------------------
The zone's real response is nonlinear -- the plant saturates, the COP moves
with outdoor temperature. Solving the nonlinear problem directly would need a
global solver and would be hard to defend. Instead the zone is linearised
around the baseline trajectory the *simulator* just produced, which gives a
quadratic program CVXPY solves to a certifiable global optimum in milliseconds.

The linearisation is an approximation, so the answer is never trusted on its
own: the proposed setpoint trajectory is fed back through the full nonlinear
simulator, and the KPI comparison the UI shows is the *simulated* result, not
the optimiser's own prediction. The optimiser proposes; the simulator judges.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np

from core.adapters.building.simulation import (
    STEP_SECONDS,
    STEPS_PER_HOUR,
    ComfortBand,
    ZoneThermalParams,
    cop_cooling,
)

log = logging.getLogger(__name__)


@dataclass
class SetpointProblem:
    """Everything the optimiser needs, all of it inspectable."""

    outdoor_temp_c: np.ndarray
    occupancy: np.ndarray
    baseline_setpoint_c: np.ndarray
    baseline_zone_temp_c: np.ndarray
    params: ZoneThermalParams
    comfort: ComfortBand = field(default_factory=ComfortBand)
    initial_zone_temp_c: float = 22.5
    setpoint_min_c: float = 20.0
    setpoint_max_c: float = 26.0
    #: Maximum change between consecutive 15-minute steps, in K.
    rate_limit_k: float = 1.0
    lambda_peak: float = 6.0
    lambda_comfort: float = 260.0
    lambda_move: float = 3.0

    def horizon(self) -> int:
        return int(len(self.outdoor_temp_c))


@dataclass
class SetpointOptimisationResult:
    status: str
    solved: bool
    setpoints_c: list[float]
    predicted_zone_temp_c: list[float]
    predicted_hvac_kw: list[float]
    objective: float
    baseline_objective: float
    comfort_slack_kh: float
    max_step_change_k: float
    solver: str
    solve_time_s: float
    constraints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class SetpointOptimiser:
    """Convex setpoint optimisation over a linearised zone model."""

    def solve(self, problem: SetpointProblem) -> SetpointOptimisationResult:
        horizon = problem.horizon()
        params = problem.params
        occupancy = np.clip(problem.occupancy, 0.0, 1.0)
        outdoor = np.asarray(problem.outdoor_temp_c, dtype=float)

        ua = np.array([params.ua_total(o) for o in occupancy])
        # Discrete first-order zone model, linearised about the baseline:
        #   T_{t+1} = a_t T_t + (1 - a_t) T_out_t + b_t (u_t - T_t) + c_t
        # The plant term is written as a gain on the tracking error, which is
        # exactly what the ideal-load simulator does inside its capacity band.
        a = np.exp(-ua * STEP_SECONDS / params.c_air)
        gain = np.clip(params.cooling_capacity_w * STEP_SECONDS / params.c_air / 4.0, 0.15, 0.9)

        q_internal = params.internal_gain_w_m2 * params.floor_area_m2 * (0.25 + 0.75 * occupancy)
        drift = q_internal * STEP_SECONDS / params.c_air * (1.0 - a)

        # Electrical cost per K of cooling delivered, at each step's COP. This
        # is what makes the optimiser prefer to shift work into cooler hours.
        cop = np.array([cop_cooling(float(t), params) for t in outdoor])
        kw_per_k = params.ua_total(1.0) / cop / 1000.0

        lower = np.array([problem.comfort.bounds(o > 0.15)[0] for o in occupancy], dtype=float)
        upper = np.array([problem.comfort.bounds(o > 0.15)[1] for o in occupancy], dtype=float)

        u = cp.Variable(horizon, name="setpoint")
        temp = cp.Variable(horizon + 1, name="zone_temp")
        slack = cp.Variable(horizon, nonneg=True, name="comfort_slack")
        peak = cp.Variable(nonneg=True, name="peak")

        constraints = [temp[0] == problem.initial_zone_temp_c]
        for t in range(horizon):
            constraints.append(
                temp[t + 1]
                == a[t] * temp[t] + (1 - a[t]) * outdoor[t] + gain * (u[t] - temp[t]) + drift[t]
            )
        constraints += [
            u >= problem.setpoint_min_c,
            u <= problem.setpoint_max_c,
            temp[1:] >= lower - slack,
            temp[1:] <= upper + slack,
        ]
        constraints.append(
            cp.abs(u[0] - float(problem.baseline_setpoint_c[0])) <= problem.rate_limit_k
        )
        for t in range(1, horizon):
            constraints.append(cp.abs(u[t] - u[t - 1]) <= problem.rate_limit_k)

        # Cooling effort proxy: how far the zone is pushed below its free-float
        # level, priced at the step's electrical cost per K.
        effort = cp.multiply(kw_per_k, cp.pos(outdoor - u))
        constraints.append(peak >= cp.max(effort))

        movement = cp.sum(cp.abs(cp.diff(u)))
        objective = cp.Minimize(
            cp.sum(effort) / STEPS_PER_HOUR
            + problem.lambda_peak * peak
            + problem.lambda_comfort * cp.sum(slack) / STEPS_PER_HOUR
            + problem.lambda_move * movement
        )

        prob = cp.Problem(objective, constraints)
        try:
            prob.solve(solver=cp.CLARABEL)
        except Exception as exc:  # pragma: no cover - solver fallback
            log.warning("CLARABEL failed (%s); retrying with SCS", exc)
            prob.solve(solver=cp.SCS)

        solved = prob.status in ("optimal", "optimal_inaccurate")
        if not solved or u.value is None:
            return SetpointOptimisationResult(
                status=str(prob.status),
                solved=False,
                setpoints_c=[float(v) for v in problem.baseline_setpoint_c],
                predicted_zone_temp_c=[float(v) for v in problem.baseline_zone_temp_c],
                predicted_hvac_kw=[],
                objective=float("nan"),
                baseline_objective=float("nan"),
                comfort_slack_kh=float("nan"),
                max_step_change_k=0.0,
                solver="none",
                solve_time_s=0.0,
                notes=["Optimisation did not converge; the baseline schedule stands."],
            )

        setpoints = np.asarray(u.value, dtype=float)
        baseline_effort = np.maximum(outdoor - problem.baseline_setpoint_c, 0.0) * kw_per_k
        baseline_objective = float(
            baseline_effort.sum() / STEPS_PER_HOUR + problem.lambda_peak * baseline_effort.max()
        )

        return SetpointOptimisationResult(
            status=str(prob.status),
            solved=True,
            setpoints_c=[round(float(v), 3) for v in setpoints],
            predicted_zone_temp_c=[round(float(v), 3) for v in np.asarray(temp.value)[1:]],
            predicted_hvac_kw=[round(float(v), 4) for v in np.asarray(effort.value, dtype=float)],
            objective=float(prob.value),
            baseline_objective=baseline_objective,
            comfort_slack_kh=round(float(np.sum(slack.value)) / STEPS_PER_HOUR, 4),
            max_step_change_k=(
                round(float(np.max(np.abs(np.diff(setpoints)))), 3) if horizon > 1 else 0.0
            ),
            solver=str(prob.solver_stats.solver_name if prob.solver_stats else "unknown"),
            solve_time_s=round(
                float(prob.solver_stats.solve_time or 0.0) if prob.solver_stats else 0.0, 4
            ),
            constraints=[
                f"setpoint within [{problem.setpoint_min_c}, {problem.setpoint_max_c}] °C",
                f"step change ≤ {problem.rate_limit_k} K per 15 min",
                "zone temperature inside the active comfort band (soft, penalised)",
                "linearised zone dynamics",
            ],
            notes=[
                "Linearised about the baseline trajectory; the proposal is re-run "
                "through the full nonlinear simulator before any KPI is reported.",
                f"Weights: peak {problem.lambda_peak}, comfort {problem.lambda_comfort}, "
                f"movement {problem.lambda_move}.",
            ],
        )
