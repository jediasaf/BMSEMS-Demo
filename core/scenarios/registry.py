"""The curated scenario set.

Three per module, no more. Each one is seeded, so the same scenario produces
byte-identical numbers on every run and on every machine -- which is what makes
a live demo safe and a regression test possible.

Everything a scenario adds is tagged ``INJECTED`` and the UI shows the banner.
A scenario never rewrites history: it adds a disturbance on top of the measured
series and both are charted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

SEED_BASE = 20240312


@dataclass(frozen=True)
class ScenarioInjection:
    """What a scenario did, in numbers the UI can show verbatim.

    Every field is computed from the frame the injection was applied to, so
    the demo can state its own disturbance without anyone reading the code.
    """

    scenario_id: str
    label: str
    description: str
    metric: str
    unit: str
    peak_injection: float
    total_injection: float
    affected_steps: int
    seed: int
    #: The asset the disturbance was applied to. A scenario is seeded per
    #: asset, so naming it here is what makes the seed reproducible.
    affected_asset: str = ""
    #: First and last instant the injection is non-zero, ISO-8601, naive local
    #: clock (the source publishes no offset).
    injection_start: str | None = None
    injection_end: str | None = None
    #: Wall-clock extent of the injected disturbance.
    duration_hours: float = 0.0
    detail: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    module: Literal["BMS", "EMS"]
    name: str
    subtitle: str
    description: str
    #: What an operator should learn from running it.
    teaches: str
    is_baseline: bool = False
    parameters: dict[str, float] = field(default_factory=dict)
    #: The one scenario per module the guided interview demo runs. Exactly one
    #: per module, asserted in the tests.
    is_flagship: bool = False
    #: Which measured channel the disturbance is added to.
    injected_parameter: str = ""
    #: The magnitude, in words, of what `parameters` says in numbers.
    magnitude: str = ""
    #: How long the disturbance lasts, in words.
    duration: str = ""
    #: The mechanism the scenario is expected to trigger. Deliberately a
    #: mechanism and not a number: the number is whatever the models return.
    expected_impact: str = ""


BMS_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        scenario_id="bms_normal_day",
        module="BMS",
        name="Normal Day",
        subtitle="Measured operation, no injection",
        description=(
            "The building as recorded. Nothing is added; this is the reference "
            "every other BMS scenario is compared against."
        ),
        teaches="What the model expects when the building behaves.",
        is_baseline=True,
        injected_parameter="none",
        magnitude="none",
        duration="none",
        expected_impact=(
            "No finding above the materiality floor. The reference case exists "
            "so an empty insight feed can be shown to be correct rather than broken."
        ),
    ),
    Scenario(
        scenario_id="bms_hot_day",
        module="BMS",
        name="Hot Day / HVAC Stress",
        subtitle="Outdoor temperature raised, cooling load follows",
        description=(
            "Outdoor air temperature is raised by a fixed offset with a "
            "mid-afternoon emphasis, and the site load is scaled by the building's "
            "own fitted cooling sensitivity. The forecaster sees the real weather, "
            "so the residual engine registers the gap."
        ),
        teaches=(
            "How a weather excursion separates from an equipment fault: the "
            "deviation tracks degree-hours rather than the occupancy schedule."
        ),
        parameters={"temperature_offset_c": 7.0, "afternoon_emphasis_c": 3.0},
        is_flagship=True,
        injected_parameter=(
            "outdoor_temp_c, and load_kw through the site's fitted cooling sensitivity"
        ),
        magnitude="+7.0 K baseline offset, +3.0 K further at 15:00",
        duration="the whole replay window, weighted to each afternoon",
        expected_impact=(
            "The forecaster is given the real weather, so the extra cooling load "
            "lands in the residual. The robust z-score crosses its threshold, an "
            "over-consumption insight is raised with its possible causes, and a "
            "constrained setpoint relaxation is proposed. The saving is whatever "
            "the zone simulator returns for that setpoint -- it is not asserted "
            "here and it is not asserted in the UI until the Control Lab has run."
        ),
    ),
    Scenario(
        scenario_id="bms_sensor_drift",
        module="BMS",
        name="Sensor Drift",
        subtitle="A meter channel drifts slowly out of calibration",
        description=(
            "A linear bias is added to the measured load over the window, of the "
            "kind a mis-scaled CT or a drifting transducer produces. It is small "
            "at any single instant and unmistakable in aggregate."
        ),
        teaches=(
            "Why a sustained one-sided residual is classified as drift rather than "
            "over-consumption, and why a materiality floor matters."
        ),
        parameters={"drift_pct_per_day": 9.0},
        injected_parameter="load_kw",
        magnitude="+9% of the measured load per day, accumulating",
        duration="the whole replay window, growing linearly from zero",
        expected_impact=(
            "A one-sided residual that grows rather than tracking the occupancy "
            "schedule, classified SENSOR_DRIFT rather than over-consumption. No "
            "control action is proposed, because the right answer is to inspect "
            "the instrument."
        ),
    ),
)

EMS_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        scenario_id="ems_normal_day",
        module="EMS",
        name="Normal Day",
        subtitle="Measured demand, no injection",
        description=(
            "Portfolio demand as recorded, mapped onto the network model. The "
            "reference case for the transformer risk assessment."
        ),
        teaches="Normal transformer loading and the headroom actually available.",
        is_baseline=True,
        injected_parameter="none",
        magnitude="none",
        duration="none",
        expected_impact=(
            "A converged load flow with every bus inside the EN 50160 band and "
            "the transformer inside nameplate. No violation, and none invented."
        ),
    ),
    Scenario(
        scenario_id="ems_peak_demand",
        module="EMS",
        name="Peak Demand",
        subtitle="Coincident afternoon demand across the portfolio",
        description=(
            "A broad afternoon uplift applied to the site's demand, representing "
            "the coincidence of cooling load, occupancy and process demand that "
            "produces the monthly maximum."
        ),
        teaches=(
            "That a well-sized transformer survives its own peak day. The rating "
            "was derived from the site's P99 with 25% headroom, so coincident "
            "demand alone rarely reaches nameplate -- which is precisely what "
            "sizing is for. Compare with EV Charging Surge, which is load the "
            "transformer was never sized for."
        ),
        parameters={"uplift_pct": 38.0, "centre_hour": 15.0, "width_hours": 3.5},
        injected_parameter="facility demand, as an additive uplift on every feeder",
        magnitude="+38% of measured demand at the 15:00 centre of the bell",
        duration="roughly 12:00-18:00, a 3.5 h Gaussian width",
        expected_impact=(
            "Transformer loading rises but stays inside nameplate, because the "
            "rating was derived from the site's own P99 with headroom. The "
            "instructive result is the one where nothing breaks."
        ),
    ),
    Scenario(
        scenario_id="ems_ev_surge",
        module="EMS",
        name="EV Charging Surge",
        subtitle="Fleet charging session arrives on top of site demand",
        description=(
            "A block of EV charging load is added to the flexible feeder during "
            "the afternoon. It is additive: the measured site demand is untouched "
            "and both series are charted."
        ),
        teaches=(
            "The flagship case. Unlike a peak day, this is load the transformer "
            "was never sized for: it goes past nameplate, and the fix is to shift "
            "the energy rather than shed it. Deferral must also precede recovery, "
            "or the optimiser charges vehicles that have not arrived."
        ),
        parameters={"charger_kw": 120.0, "start_hour": 13.0, "duration_hours": 4.0},
        is_flagship=True,
        injected_parameter="the flexible feeder (F4), as additive EV charging load",
        magnitude="120 kW nameplate, ramping over 30 min and tapering over 45 min",
        duration="13:00-17:00 each day of the window",
        expected_impact=(
            "The load flow puts the transformer past 100% of its calibrated "
            "capacity and pulls the LV bus down. The linear program defers EV "
            "charging into the evening -- conserving its energy as a hard "
            "equality and never recovering before it curtailed -- and buys HVAC "
            "flexibility within a comfort budget. A second, independent load "
            "flow reports the result."
        ),
    ),
)

ALL_SCENARIOS: dict[str, Scenario] = {s.scenario_id: s for s in (*BMS_SCENARIOS, *EMS_SCENARIOS)}


def list_scenarios(module: str | None = None) -> list[Scenario]:
    if module is None:
        return list(ALL_SCENARIOS.values())
    return [s for s in ALL_SCENARIOS.values() if s.module == module.upper()]


def get_scenario(scenario_id: str) -> Scenario:
    try:
        return ALL_SCENARIOS[scenario_id]
    except KeyError as exc:
        raise KeyError(f"unknown scenario {scenario_id!r}") from exc


def _seed_for(scenario_id: str, asset_id: str) -> int:
    """Stable across processes.

    ``hash()`` on a string is salted per interpreter run, so using it here
    would make "deterministic scenario" true only within one process -- the
    demo would show different numbers after a restart.
    """
    digest = hashlib.sha256(f"{scenario_id}|{asset_id}".encode()).digest()
    return SEED_BASE + int.from_bytes(digest[:4], "big") % 100_000


def _hour_of_day(index: pd.DatetimeIndex) -> np.ndarray:
    return index.hour.to_numpy() + index.minute.to_numpy() / 60.0


def _bell(hours: np.ndarray, centre: float, width: float) -> np.ndarray:
    return np.exp(-0.5 * ((hours - centre) / max(width, 1e-6)) ** 2)


def _extent(index: pd.DatetimeIndex, injection: np.ndarray) -> tuple[str | None, str | None, float]:
    """First and last instant the injection is live, and how many hours it runs.

    The UI states the disturbance's own extent rather than the replay window,
    so it is read off the series instead of off the parameters.
    """
    live = np.flatnonzero(~np.isclose(injection, 0.0))
    if live.size == 0:
        return None, None, 0.0
    # Hours the injection is actually non-zero, not the span between its first
    # and last instant: a session that repeats on each day of the window would
    # otherwise report the whole window as its duration.
    hours = live.size * 0.25
    return index[int(live[0])].isoformat(), index[int(live[-1])].isoformat(), round(hours, 2)


# --------------------------------------------------------------------------
# BMS
# --------------------------------------------------------------------------
def apply_bms_scenario(
    frame: pd.DataFrame,
    scenario_id: str,
    *,
    asset_id: str,
    hvac_sensitivity_kw_per_k: float = 1.0,
) -> tuple[pd.DataFrame, ScenarioInjection | None]:
    """Return ``(frame_with_injection, injection_summary)``.

    The original measured columns are preserved as ``load_kw_measured`` and
    ``outdoor_temp_c_measured`` so the UI can chart both.
    """
    scenario = get_scenario(scenario_id)
    out = frame.copy()
    out["load_kw_measured"] = frame["load_kw"]
    if "outdoor_temp_c" in frame:
        out["outdoor_temp_c_measured"] = frame["outdoor_temp_c"]
    out["injection_kw"] = 0.0

    if scenario.is_baseline:
        return out, None

    seed = _seed_for(scenario_id, asset_id)
    rng = np.random.default_rng(seed)
    hours = _hour_of_day(out.index)

    if scenario_id == "bms_hot_day":
        offset = scenario.parameters["temperature_offset_c"]
        emphasis = scenario.parameters["afternoon_emphasis_c"]
        delta_t = offset + emphasis * _bell(hours, 15.0, 3.0)
        if "outdoor_temp_c" in out:
            out["outdoor_temp_c"] = out["outdoor_temp_c_measured"] + delta_t
        # Extra cooling load, using the site's own fitted sensitivity plus a
        # small seeded variation so the series is not suspiciously smooth.
        extra = delta_t * hvac_sensitivity_kw_per_k * (1.0 + rng.normal(0, 0.04, len(out)))
        extra = np.clip(extra, 0.0, None)
        out["injection_kw"] = extra
        out["load_kw"] = out["load_kw_measured"] + extra
        detail = {
            "temperature_offset_c": float(offset),
            "peak_temperature_offset_c": float(np.max(delta_t)),
            "hvac_sensitivity_kw_per_k": float(hvac_sensitivity_kw_per_k),
        }
        metric, unit = "load_kw", "kW"

    elif scenario_id == "bms_sensor_drift":
        pct_per_day = scenario.parameters["drift_pct_per_day"]
        # Days since the start of the injected window, not since the start of
        # the dataset: the scenario describes a drift that begins now.
        days = (out.index - out.index[0]).total_seconds().to_numpy() / 86400.0
        drift = out["load_kw_measured"].to_numpy() * (pct_per_day / 100.0) * days
        out["injection_kw"] = drift
        out["load_kw"] = out["load_kw_measured"] + drift
        detail = {
            "drift_pct_per_day": float(pct_per_day),
            "final_bias_kw": float(drift[-1]) if len(drift) else 0.0,
        }
        metric, unit = "load_kw", "kW"

    else:  # pragma: no cover - guarded by the registry
        raise KeyError(f"no BMS handler for {scenario_id!r}")

    injection = out["injection_kw"].to_numpy()
    first, last, hours = _extent(out.index, injection)
    return out, ScenarioInjection(
        scenario_id=scenario_id,
        label=scenario.name,
        description=scenario.description,
        metric=metric,
        unit=unit,
        peak_injection=round(float(np.nanmax(injection)), 3),
        total_injection=round(float(np.nansum(injection)) / 4.0, 3),
        affected_steps=int(np.count_nonzero(~np.isclose(injection, 0.0))),
        seed=seed,
        affected_asset=asset_id,
        injection_start=first,
        injection_end=last,
        duration_hours=hours,
        detail={k: round(v, 4) for k, v in detail.items()},
    )


# --------------------------------------------------------------------------
# EMS
# --------------------------------------------------------------------------
def apply_ems_scenario(
    frame: pd.DataFrame,
    scenario_id: str,
    *,
    asset_id: str,
) -> tuple[pd.DataFrame, ScenarioInjection | None]:
    """Add ``injection_kw`` and ``flexible_kw`` columns to a facility frame.

    ``load_kw`` is left untouched: injected load is additive and the network
    model receives it as a separate feeder contribution.
    """
    scenario = get_scenario(scenario_id)
    out = frame.copy()
    out["injection_kw"] = 0.0
    out["flexible_kw"] = 0.0

    if scenario.is_baseline:
        return out, None

    seed = _seed_for(scenario_id, asset_id)
    rng = np.random.default_rng(seed)
    hours = _hour_of_day(out.index)

    if scenario_id == "ems_peak_demand":
        uplift = scenario.parameters["uplift_pct"] / 100.0
        shape = _bell(hours, scenario.parameters["centre_hour"], scenario.parameters["width_hours"])
        extra = out["load_kw"].to_numpy() * uplift * shape
        extra = extra * (1.0 + rng.normal(0, 0.03, len(out)))
        out["injection_kw"] = np.clip(extra, 0.0, None)
        detail = {
            "uplift_pct": scenario.parameters["uplift_pct"],
            "centre_hour": scenario.parameters["centre_hour"],
        }

    elif scenario_id == "ems_ev_surge":
        charger_kw = scenario.parameters["charger_kw"]
        start = scenario.parameters["start_hour"]
        duration = scenario.parameters["duration_hours"]
        active = (hours >= start) & (hours < start + duration)
        # Chargers ramp to full power over ~30 minutes and taper at the end of
        # the session, rather than switching as a perfect step.
        progress = np.clip((hours - start) / 0.5, 0.0, 1.0) * np.clip(
            (start + duration - hours) / 0.75, 0.0, 1.0
        )
        profile = np.where(active, charger_kw * progress, 0.0)
        profile = profile * (1.0 + rng.normal(0, 0.02, len(out)))
        profile = np.clip(profile, 0.0, None)
        out["injection_kw"] = profile
        out["flexible_kw"] = profile
        detail = {
            "charger_kw": charger_kw,
            "start_hour": start,
            "duration_hours": duration,
        }

    else:  # pragma: no cover
        raise KeyError(f"no EMS handler for {scenario_id!r}")

    injection = out["injection_kw"].to_numpy()
    first, last, hours = _extent(out.index, injection)
    return out, ScenarioInjection(
        scenario_id=scenario_id,
        label=scenario.name,
        description=scenario.description,
        metric="load_kw",
        unit="kW",
        peak_injection=round(float(np.nanmax(injection)), 3),
        total_injection=round(float(np.nansum(injection)) / 4.0, 3),
        affected_steps=int(np.count_nonzero(~np.isclose(injection, 0.0))),
        seed=seed,
        affected_asset=asset_id,
        injection_start=first,
        injection_end=last,
        duration_hours=hours,
        detail={k: round(float(v), 4) for k, v in detail.items()},
    )
