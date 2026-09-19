"""Building simulation interface and the EcoTwin RC thermal engine.

Two engines implement one interface:

``BoptestEngine``   - a real client for the BOPTEST REST API (IBPSA Project 1),
                      used when a BOPTEST instance is reachable. Local Docker
                      mode starts one.
``RcThermalEngine`` - a lumped-parameter 2R2C zone model with an explicit HVAC
                      plant, used when BOPTEST is not reachable.

The distinction is never smoothed over. ``SimulationResult.engine`` carries the
engine that actually answered, provenance repeats it, and the UI status bar
reads ``Live local engine`` / ``EcoTwin RC`` / ``Simulation replay``
accordingly. A result from the RC engine is never labelled BOPTEST.

The RC model
------------
Two capacitances -- indoor air and the building's thermal mass -- and three
resistances::

    T_out ──R_oa── T_air ──R_am── T_mass
                     │
                   Q_hvac + Q_gain

    C_air  dT_air/dt  = (T_out - T_air)/R_oa + (T_mass - T_air)/R_am
                        + Q_int + Q_sol + Q_hvac
    C_mass dT_mass/dt = (T_air - T_mass)/R_am

Integrated with an explicit Euler step at the 15-minute control interval, which
is stable for these time constants (tau_air ~ 1 h, tau_mass ~ 40 h). The HVAC
plant is a proportional controller against the active setpoint, limited by
capacity, with a temperature-dependent coefficient of performance so the energy
cost of a setpoint change responds to outdoor conditions the way a real chiller
does.

Parameters are derived from the building's published floor area using standard
envelope figures, and every one of them is reported in the result so a reviewer
can check the physics rather than take the number on trust.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from core.enums import SimulationEngine

log = logging.getLogger(__name__)

STEP_MINUTES = 15
STEP_SECONDS = STEP_MINUTES * 60
STEPS_PER_HOUR = 60 // STEP_MINUTES
#: How far below the comfort lower bound the heating setpoint sits by default.
HEATING_SETPOINT_MARGIN_K = 0.5


# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ZoneThermalParams:
    """Envelope and plant parameters, derived from published floor area.

    Defaults are mid-range values for a conditioned commercial office in a
    temperate climate. They are stated here rather than buried so that a
    reviewer can argue with them.
    """

    floor_area_m2: float
    #: Fabric + glazing + infiltration conductance, W/K per m2 of floor area.
    ua_per_m2: float = 0.85
    #: Mechanical ventilation conductance at full occupancy, W/K per m2.
    #: Demand-controlled, so it scales with occupancy.
    ventilation_ua_per_m2: float = 0.45
    #: Air-node capacitance, J/K per m2 (air volume plus light furnishings).
    c_air_per_m2: float = 2.0e4
    #: Structural mass capacitance, J/K per m2 (slab, partitions).
    c_mass_per_m2: float = 2.2e5
    #: Air-to-mass coupling conductance, W/K per m2.
    h_mass_per_m2: float = 5.5
    #: Peak internal gain from people, lighting and equipment, W/m2.
    internal_gain_w_m2: float = 16.0
    #: Peak solar gain through glazing, W/m2 of floor area.
    solar_gain_w_m2: float = 12.0
    #: Sensible cooling capacity, W/m2.
    cooling_capacity_w_m2: float = 75.0
    #: Sensible heating capacity, W/m2.
    heating_capacity_w_m2: float = 65.0
    #: Cooling COP at 35 C outdoor, and its degradation per K above 35 C.
    cop_cooling_nominal: float = 3.4
    cop_cooling_slope: float = 0.055
    #: Heating COP (air-source heat pump) at 7 C outdoor, and slope per K below.
    cop_heating_nominal: float = 3.1
    cop_heating_slope: float = 0.06
    #: Fan and pump power at design airflow, as a share of cooling capacity.
    auxiliary_fraction: float = 0.13
    #: Minimum fan power as a share of design, whenever the zone is occupied.
    auxiliary_minimum: float = 0.3
    #: Minimum separation enforced between the heating and cooling setpoints,
    #: in K. Without a deadband a zone can heat and cool within the same hour,
    #: which is the single most common real-world waste mode and not something
    #: to simulate into existence by accident.
    deadband_k: float = 2.0

    @property
    def ua(self) -> float:
        return self.ua_per_m2 * self.floor_area_m2

    def ua_total(self, occupancy: float) -> float:
        """Envelope plus demand-controlled ventilation."""
        return self.ua + self.ventilation_ua_per_m2 * self.floor_area_m2 * (
            0.2 + 0.8 * float(np.clip(occupancy, 0.0, 1.0))
        )

    @property
    def c_air(self) -> float:
        return self.c_air_per_m2 * self.floor_area_m2

    @property
    def c_mass(self) -> float:
        return self.c_mass_per_m2 * self.floor_area_m2

    @property
    def h_mass(self) -> float:
        return self.h_mass_per_m2 * self.floor_area_m2

    @property
    def cooling_capacity_w(self) -> float:
        return self.cooling_capacity_w_m2 * self.floor_area_m2

    @property
    def heating_capacity_w(self) -> float:
        return self.heating_capacity_w_m2 * self.floor_area_m2

    def time_constants_hours(self) -> dict[str, float]:
        return {
            "air": round(self.c_air / max(self.ua_total(1.0) + self.h_mass, 1e-6) / 3600.0, 2),
            "mass": round(self.c_mass / max(self.h_mass, 1e-6) / 3600.0, 1),
        }


@dataclass(frozen=True)
class ComfortBand:
    """The constraint the optimiser must respect and the KPI scores against."""

    lower_c: float = 21.0
    upper_c: float = 24.0
    #: Band applied when the zone is unoccupied (setback).
    unoccupied_lower_c: float = 16.0
    unoccupied_upper_c: float = 28.0

    def bounds(self, occupied: bool) -> tuple[float, float]:
        return (
            (self.lower_c, self.upper_c)
            if occupied
            else (self.unoccupied_lower_c, self.unoccupied_upper_c)
        )


@dataclass
class SimulationRequest:
    """One simulation run."""

    asset_id: str
    zone_id: str
    start: datetime
    #: Cooling setpoint per step, in degrees C. Length sets the horizon.
    setpoints_c: list[float]
    outdoor_temp_c: list[float]
    occupancy: list[float]
    #: Heating setpoint per step. Defaults to the active comfort lower bound
    #: minus a small margin, i.e. ordinary dual-setpoint control. Deriving it
    #: as ``cooling - deadband`` instead makes a 27 C summer setback imply a
    #: 25 C heating setpoint, and the plant heats the building in August.
    heating_setpoints_c: list[float] | None = None
    initial_air_temp_c: float = 22.5
    initial_mass_temp_c: float = 22.5
    params: ZoneThermalParams | None = None
    comfort: ComfortBand = field(default_factory=ComfortBand)
    label: str = "baseline"

    def horizon(self) -> int:
        return len(self.setpoints_c)


@dataclass
class SimulationResult:
    """Simulator output plus the KPIs the Control Lab compares."""

    engine: SimulationEngine
    engine_version: str
    label: str
    asset_id: str
    zone_id: str
    timestamps: list[datetime]
    zone_temp_c: list[float]
    mass_temp_c: list[float]
    setpoint_c: list[float]
    hvac_electrical_kw: list[float]
    outdoor_temp_c: list[float]
    #: Total HVAC electrical energy over the horizon.
    energy_kwh: float
    peak_kw: float
    #: Degree-hours outside the active comfort band. The standard discomfort KPI.
    comfort_violation_kh: float
    comfort_violation_steps: int
    mean_zone_temp_c: float
    cop_mean: float
    parameters: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "zone_temp_c": self.zone_temp_c,
                "mass_temp_c": self.mass_temp_c,
                "setpoint_c": self.setpoint_c,
                "hvac_electrical_kw": self.hvac_electrical_kw,
                "outdoor_temp_c": self.outdoor_temp_c,
            },
            index=pd.DatetimeIndex(self.timestamps, name="timestamp"),
        )

    def kpis(self) -> dict[str, float]:
        return {
            "energy_kwh": round(self.energy_kwh, 3),
            "peak_kw": round(self.peak_kw, 3),
            "comfort_violation_kh": round(self.comfort_violation_kh, 4),
            "comfort_violation_steps": float(self.comfort_violation_steps),
            "mean_zone_temp_c": round(self.mean_zone_temp_c, 2),
            "cop_mean": round(self.cop_mean, 3),
        }


class BuildingSimulationEngine(ABC):
    engine: SimulationEngine
    version: str = "unknown"

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def simulate(self, request: SimulationRequest) -> SimulationResult: ...


# --------------------------------------------------------------------------
# RC engine
# --------------------------------------------------------------------------
def cop_cooling(outdoor_c: float, params: ZoneThermalParams) -> float:
    """Chiller COP falls as it rejects heat into a hotter ambient."""
    return float(
        np.clip(
            params.cop_cooling_nominal - params.cop_cooling_slope * (outdoor_c - 25.0),
            1.2,
            7.0,
        )
    )


def cop_heating(outdoor_c: float, params: ZoneThermalParams) -> float:
    """Heat-pump COP falls as the source gets colder."""
    return float(
        np.clip(
            params.cop_heating_nominal - params.cop_heating_slope * (7.0 - outdoor_c),
            1.0,
            5.5,
        )
    )


class RcThermalEngine(BuildingSimulationEngine):
    """The 2R2C zone model described in this module's docstring."""

    engine = SimulationEngine.ECOTWIN_RC
    version = "ecotwin-rc-1.0"

    def available(self) -> bool:
        return True

    def simulate(self, request: SimulationRequest) -> SimulationResult:
        params = request.params or ZoneThermalParams(floor_area_m2=2000.0)
        horizon = request.horizon()
        if not (len(request.outdoor_temp_c) == len(request.occupancy) == horizon):
            raise ValueError("setpoints, outdoor temperature and occupancy must share a length")

        t_air = float(request.initial_air_temp_c)
        t_mass = float(request.initial_mass_temp_c)

        air_temps: list[float] = []
        mass_temps: list[float] = []
        elec_kw: list[float] = []
        cops: list[float] = []
        timestamps: list[datetime] = []
        violation_kh = 0.0
        violation_steps = 0

        for step in range(horizon):
            stamp = request.start + timedelta(minutes=STEP_MINUTES * step)
            outdoor = float(request.outdoor_temp_c[step])
            occupancy = float(np.clip(request.occupancy[step], 0.0, 1.0))
            setpoint = float(request.setpoints_c[step])

            q_internal = (
                params.internal_gain_w_m2 * params.floor_area_m2 * (0.25 + 0.75 * occupancy)
            )
            # Solar gain follows a clipped sinusoid over daylight hours; without
            # an irradiance series this is the honest minimum, and it is
            # reported in `parameters` as an assumption.
            hour = stamp.hour + stamp.minute / 60.0
            solar_shape = float(np.clip(np.sin(np.pi * (hour - 6.5) / 11.0), 0.0, 1.0))
            q_solar = params.solar_gain_w_m2 * params.floor_area_m2 * solar_shape

            ua_total = params.ua_total(occupancy)
            # Free response of the zone over one step, i.e. what the air node
            # would do with the plant off.
            q_free = (
                (outdoor - t_air) * ua_total
                + (t_mass - t_air) * params.h_mass
                + q_internal
                + q_solar
            )

            # Ideal-load plant (as in an EnergyPlus IdealLoadsAirSystem): the
            # heat flow that lands the air node exactly on the nearer setpoint
            # at the end of the step, clipped to installed capacity. A
            # proportional controller would leave a steady-state offset that
            # swamps the setpoint experiment this whole page exists to run.
            cool_setpoint = setpoint
            if request.heating_setpoints_c is not None:
                heat_setpoint = float(request.heating_setpoints_c[step])
            else:
                lower, _ = request.comfort.bounds(occupancy > 0.15)
                heat_setpoint = lower - HEATING_SETPOINT_MARGIN_K
            heat_setpoint = min(heat_setpoint, cool_setpoint - params.deadband_k)
            q_hvac = 0.0
            if t_air > cool_setpoint or (q_free > 0 and t_air >= cool_setpoint):
                target = cool_setpoint
                required = params.c_air * (target - t_air) / STEP_SECONDS - q_free
                q_hvac = float(np.clip(required, -params.cooling_capacity_w, 0.0))
            elif t_air < heat_setpoint or (q_free < 0 and t_air <= heat_setpoint):
                target = heat_setpoint
                required = params.c_air * (target - t_air) / STEP_SECONDS - q_free
                q_hvac = float(np.clip(required, 0.0, params.heating_capacity_w))

            if q_hvac < 0:
                cop = cop_cooling(outdoor, params)
                electrical_w = abs(q_hvac) / cop
                load_fraction = abs(q_hvac) / params.cooling_capacity_w
            elif q_hvac > 0:
                cop = cop_heating(outdoor, params)
                electrical_w = q_hvac / cop
                load_fraction = q_hvac / params.heating_capacity_w
            else:
                cop = cop_cooling(outdoor, params)
                electrical_w = 0.0
                load_fraction = 0.0

            # Fans and pumps run whenever the zone is occupied, whether or not
            # the plant is loaded; ignoring that flatters every saving estimate.
            # Power follows airflow, and airflow follows load above a minimum.
            airflow_fraction = max(
                params.auxiliary_minimum if occupancy > 0.15 else 0.0,
                min(load_fraction, 1.0),
            )
            auxiliary_w = params.auxiliary_fraction * params.cooling_capacity_w * airflow_fraction
            total_electrical_w = electrical_w + auxiliary_w

            d_air = (q_free + q_hvac) / params.c_air
            d_mass = ((t_air - t_mass) * params.h_mass) / params.c_mass

            band_lower, band_upper = request.comfort.bounds(occupancy > 0.15)
            if t_air > band_upper:
                violation_kh += (t_air - band_upper) / STEPS_PER_HOUR
                violation_steps += 1
            elif t_air < band_lower:
                violation_kh += (band_lower - t_air) / STEPS_PER_HOUR
                violation_steps += 1

            timestamps.append(stamp)
            air_temps.append(round(t_air, 4))
            mass_temps.append(round(t_mass, 4))
            elec_kw.append(round(total_electrical_w / 1000.0, 5))
            cops.append(cop)

            t_air += d_air * STEP_SECONDS
            t_mass += d_mass * STEP_SECONDS

        energy_kwh = float(np.sum(elec_kw) / STEPS_PER_HOUR)
        return SimulationResult(
            engine=self.engine,
            engine_version=self.version,
            label=request.label,
            asset_id=request.asset_id,
            zone_id=request.zone_id,
            timestamps=timestamps,
            zone_temp_c=air_temps,
            mass_temp_c=mass_temps,
            setpoint_c=[float(s) for s in request.setpoints_c],
            hvac_electrical_kw=elec_kw,
            outdoor_temp_c=[float(t) for t in request.outdoor_temp_c],
            energy_kwh=energy_kwh,
            peak_kw=float(np.max(elec_kw)) if elec_kw else 0.0,
            comfort_violation_kh=violation_kh,
            comfort_violation_steps=violation_steps,
            mean_zone_temp_c=float(np.mean(air_temps)) if air_temps else 0.0,
            cop_mean=float(np.mean(cops)) if cops else 0.0,
            parameters={
                **asdict(params),
                "time_constants_hours": params.time_constants_hours(),
                "step_minutes": STEP_MINUTES,
                "integrator": "explicit Euler",
                "comfort_band": asdict(request.comfort),
            },
            notes=[
                "EcoTwin RC thermal engine, not BOPTEST.",
                "Solar gain is a clipped daylight sinusoid: the source publishes no "
                "irradiance series.",
                "Envelope parameters are derived from published floor area using "
                "standard commercial-office figures.",
                "Plant is an ideal-load model limited by installed capacity. "
                "Heating and cooling setpoints are scheduled separately, with at "
                f"least a {params.deadband_k:g} K deadband between them.",
            ],
        )


def get_simulation_engine(prefer_boptest: bool = True) -> BuildingSimulationEngine:
    """Return the best engine available right now.

    Imported lazily so ``simulation.py`` has no import-time dependency on the
    BOPTEST client, and so a missing httpx cannot break the in-process engine.
    """
    if prefer_boptest:
        from core.adapters.building.boptest import BoptestEngine

        boptest = BoptestEngine()
        if boptest.available():
            return boptest
    return RcThermalEngine()
