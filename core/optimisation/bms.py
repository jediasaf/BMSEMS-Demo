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
The zone's real response is nonlinear in exactly two places: the plant
saturates, and the COP moves with outdoor temperature. Everything else --
envelope conduction, ventilation, the coupling between the air node and the
structure -- is linear. So the problem is written with delivered cooling power
as the decision variable over the *same two-node model the simulator
integrates*, with capacity as a box constraint and the COP entering as a
per-step price. That is a linear program CVXPY solves to a certifiable global
optimum in milliseconds.

Modelling the air node alone would be much simpler and quite wrong: this
building's air capacitance gives a 0.8 h time constant while its structure
gives 11 h. A single-node optimiser believes overnight pre-cooling is both
cheap and effective, proposes it, and the simulator then reports a worse
result than doing nothing.

The model is still an approximation -- it plans cooling power directly where
the real plant is driven by a setpoint -- so the answer is never trusted on
its own: the implied setpoint trajectory is fed back through the full
nonlinear simulator, and the KPI comparison the UI shows is the *simulated*
result. The optimiser proposes; the simulator judges, and may veto.
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
    #: Structure temperature at the first step. The simulator carries a mass
    #: node; an optimiser that starts it in the wrong place plans against a
    #: building with the wrong amount of stored heat.
    initial_mass_temp_c: float | None = None
    #: Solar gain per step in W, from ``simulation.solar_gain_w``. Left None it
    #: is taken as zero, which is only right for a windowless building.
    solar_gain_w: np.ndarray | None = None
    setpoint_min_c: float = 20.0
    setpoint_max_c: float = 26.0
    #: Maximum change between consecutive 15-minute steps, in K.
    rate_limit_k: float = 1.0
    lambda_peak: float = 6.0
    lambda_comfort: float = 260.0
    lambda_move: float = 3.0
    #: Tie-break, not a preference. The plant relation only bounds the setpoint
    #: from below (``u >= T_air`` at the end of the step), so a setpoint held
    #: well above a zone the optimiser is cooling anyway costs nothing and the
    #: solver is free to return one. A real plant driven by that setpoint would
    #: simply not cool, so the plan would be unrealisable. This term selects the
    #: lowest setpoint consistent with the cooling actually planned.
    lambda_setpoint_gap: float = 0.05
    #: Price on cooling the plant was asked for and could not deliver, as a
    #: multiple of what delivering it would have cost. Greater than one, so
    #: the plant always runs when it is able and a shortfall is a consequence
    #: of capacity rather than a choice the optimiser made.
    lambda_unmet: float = 2.0

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
        q_internal = params.internal_gain_w_m2 * params.floor_area_m2 * (0.25 + 0.75 * occupancy)
        q_solar = (
            np.zeros(horizon)
            if problem.solar_gain_w is None
            else np.asarray(problem.solar_gain_w, dtype=float)
        )

        # Electrical cost of delivered cooling at each step's COP. This is what
        # makes the optimiser prefer to do its work in the cooler hours.
        cop = np.array([cop_cooling(float(t), params) for t in outdoor])
        kw_per_w = 1.0 / cop / 1000.0
        capacity_w = params.cooling_capacity_w

        lower = np.array([problem.comfort.bounds(o > 0.15)[0] for o in occupancy], dtype=float)
        upper = np.array([problem.comfort.bounds(o > 0.15)[1] for o in occupancy], dtype=float)

        u = cp.Variable(horizon, name="setpoint")
        air = cp.Variable(horizon + 1, name="air_temp")
        mass = cp.Variable(horizon + 1, name="mass_temp")
        cooling_w = cp.Variable(horizon, nonneg=True, name="cooling_w")
        unmet_w = cp.Variable(horizon, nonneg=True, name="unmet_cooling_w")
        slack = cp.Variable(horizon, nonneg=True, name="comfort_slack")
        peak = cp.Variable(nonneg=True, name="peak")

        initial_mass = (
            problem.initial_zone_temp_c
            if problem.initial_mass_temp_c is None
            else float(problem.initial_mass_temp_c)
        )
        constraints = [air[0] == problem.initial_zone_temp_c, mass[0] == initial_mass]
        # The simulator's own two-node update, written out. Euler at 15 min on
        # an 0.8 h air time constant is stable and is exactly what the engine
        # that will judge this proposal does.
        for t in range(horizon):
            q_free = (
                (outdoor[t] - air[t]) * ua[t]
                + (mass[t] - air[t]) * params.h_mass
                + q_internal[t]
                + q_solar[t]
            )
            constraints += [
                air[t + 1] == air[t] + STEP_SECONDS / params.c_air * (q_free - cooling_w[t]),
                mass[t + 1]
                == mass[t] + STEP_SECONDS / params.c_mass * (air[t] - mass[t]) * params.h_mass,
                # Ideal-load plant, written as an inequality: the plant must
                # remove at least what it takes to land the air node on the
                # setpoint. The objective is increasing in cooling, so the
                # bound is tight where cooling is needed and slack where the
                # zone floats below setpoint on its own.
                #
                # `unmet_w` is the part of that demand the plant could not
                # meet. Without it an undersized plant makes the whole
                # program infeasible, where the simulator simply clips to
                # capacity and lets the zone run warm. Infeasible is the
                # wrong answer to "this chiller is too small".
                cooling_w[t] + unmet_w[t] >= q_free - params.c_air * (u[t] - air[t]) / STEP_SECONDS,
            ]

        # The plant is finite; a trajectory that needs more cooling than the
        # chiller can deliver is not a plan, it is a wish.
        constraints += [
            cooling_w <= capacity_w,
            air[1:] >= lower - slack,
            air[1:] <= upper + slack,
            u >= problem.setpoint_min_c,
            u <= problem.setpoint_max_c,
        ]
        constraints.append(
            cp.abs(u[0] - float(problem.baseline_setpoint_c[0])) <= problem.rate_limit_k
        )
        constraints.append(cp.abs(cp.diff(u)) <= problem.rate_limit_k)

        electrical_kw = cp.multiply(kw_per_w, cooling_w)
        constraints.append(peak >= cp.max(electrical_kw))

        movement = cp.sum(cp.abs(cp.diff(u)))
        # Only the degenerate direction is penalised: a setpoint held above a
        # zone the plant is cooling anyway. A setpoint the plant cannot reach
        # sits below the zone, and that is capacity, not slack in the model.
        setpoint_gap = cp.sum(cp.pos(u - air[1:]))
        unmet_kw = cp.multiply(kw_per_w, unmet_w)
        objective = cp.Minimize(
            cp.sum(electrical_kw) / STEPS_PER_HOUR
            + problem.lambda_peak * peak
            + problem.lambda_comfort * cp.sum(slack) / STEPS_PER_HOUR
            + problem.lambda_move * movement
            + problem.lambda_setpoint_gap * setpoint_gap
            + problem.lambda_unmet * cp.sum(unmet_kw) / STEPS_PER_HOUR
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
        # The baseline, scored on the same terms: the cooling the plant would
        # deliver holding the baseline setpoint, at the same per-step COP.
        baseline_cooling_w = np.clip(
            np.maximum(problem.baseline_zone_temp_c - problem.baseline_setpoint_c, 0.0)
            * params.c_air
            / STEP_SECONDS,
            0.0,
            capacity_w,
        )
        baseline_kw = baseline_cooling_w * kw_per_w
        baseline_objective = float(
            baseline_kw.sum() / STEPS_PER_HOUR + problem.lambda_peak * baseline_kw.max()
        )

        return SetpointOptimisationResult(
            status=str(prob.status),
            solved=True,
            setpoints_c=[round(float(v), 3) for v in setpoints],
            predicted_zone_temp_c=[
                round(float(v), 3) for v in np.asarray(air.value, dtype=float)[1:]
            ],
            predicted_hvac_kw=[
                round(float(v), 4) for v in np.asarray(electrical_kw.value, dtype=float)
            ],
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
                "delivered cooling never exceeds installed plant capacity",
                "cooling asked for beyond capacity is reported, not assumed away",
                "two-node zone dynamics, the same model the simulator integrates",
            ],
            notes=[
                "Cooling power is the decision variable; the implied setpoint "
                "trajectory is re-run through the full nonlinear simulator before "
                "any KPI is reported, and is rejected if it does not improve on "
                "the baseline.",
                f"Weights: peak {problem.lambda_peak}, comfort {problem.lambda_comfort}, "
                f"movement {problem.lambda_move}.",
            ],
        )
