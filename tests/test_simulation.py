"""The building simulator must obey physics, not just return numbers."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from core.adapters.building.simulation import (
    STEPS_PER_HOUR,
    ComfortBand,
    RcThermalEngine,
    SimulationRequest,
    ZoneThermalParams,
    cop_cooling,
    cop_heating,
    get_simulation_engine,
)
from core.enums import SimulationEngine

HORIZON = 96


def _inputs(outdoor_mean: float = 24.0):
    hours = np.arange(HORIZON) * 0.25
    occupancy = np.where(
        (hours >= 7) & (hours <= 18), np.clip(np.sin(np.pi * (hours - 7) / 11), 0, 1), 0.0
    )
    outdoor = outdoor_mean + 6 * np.sin(2 * np.pi * (hours - 9) / 24)
    return outdoor, occupancy


def _run(
    setpoint_occupied: float, params: ZoneThermalParams | None = None, outdoor_mean: float = 24.0
):
    outdoor, occupancy = _inputs(outdoor_mean)
    setpoints = np.where(occupancy > 0.15, setpoint_occupied, 27.0)
    return RcThermalEngine().simulate(
        SimulationRequest(
            asset_id="t",
            zone_id="Z",
            start=datetime(2017, 8, 24),
            setpoints_c=[float(v) for v in setpoints],
            outdoor_temp_c=[float(v) for v in outdoor],
            occupancy=[float(v) for v in occupancy],
            params=params or ZoneThermalParams(floor_area_m2=1200.0),
            comfort=ComfortBand(),
            label="t",
        )
    )


def test_result_is_labelled_with_the_engine_that_ran_it() -> None:
    result = _run(23.0)
    assert result.engine is SimulationEngine.ECOTWIN_RC
    assert "RC" in result.engine_version.upper()
    assert any("not BOPTEST" in note for note in result.notes)


def test_engine_falls_back_when_boptest_is_absent(monkeypatch) -> None:
    monkeypatch.delenv("BOPTEST_URL", raising=False)
    engine = get_simulation_engine(prefer_boptest=True)
    assert engine.engine is SimulationEngine.ECOTWIN_RC


def test_relaxing_the_cooling_setpoint_saves_energy() -> None:
    """The single physical claim the Control Lab rests on."""
    tight = _run(22.0)
    loose = _run(24.0)
    assert loose.energy_kwh < tight.energy_kwh
    saving_per_k = (tight.energy_kwh - loose.energy_kwh) / tight.energy_kwh / 2.0
    # Sanity band for a cooling-dominated zone. Outside it, something is wrong.
    assert 0.02 < saving_per_k < 0.30, f"{saving_per_k:.1%} per K is not credible"


def test_energy_is_monotonic_in_the_setpoint() -> None:
    energies = [_run(sp).energy_kwh for sp in (22.0, 23.0, 24.0, 25.0)]
    assert energies == sorted(energies, reverse=True)


def test_no_heating_on_a_hot_day() -> None:
    """A fixed deadband once made the plant heat a building in August."""
    result = _run(23.0, outdoor_mean=28.0)
    frame = result.to_frame()
    assert (frame["zone_temp_c"] > 20.0).all()
    # Overnight, with the zone above the heating setpoint, the plant must idle.
    night = frame.between_time("01:00", "05:00")
    assert night["hvac_electrical_kw"].max() < 1.0


def test_a_warmer_day_costs_more_energy() -> None:
    assert _run(23.0, outdoor_mean=30.0).energy_kwh > _run(23.0, outdoor_mean=18.0).energy_kwh


def test_zone_temperature_stays_physical() -> None:
    result = _run(23.0)
    temps = np.array(result.zone_temp_c)
    assert temps.min() > 5.0 and temps.max() < 45.0
    # No step larger than a few K in 15 minutes: the integrator is stable.
    assert np.abs(np.diff(temps)).max() < 4.0


def test_comfort_violations_are_counted_in_degree_hours() -> None:
    result = _run(30.0)  # deliberately far above the comfort band
    assert result.comfort_violation_kh > 0
    assert result.comfort_violation_steps > 0
    assert result.comfort_violation_kh == pytest.approx(result.comfort_violation_kh, rel=1e-9)


def test_energy_equals_the_integral_of_power() -> None:
    result = _run(23.0)
    expected = sum(result.hvac_electrical_kw) / STEPS_PER_HOUR
    assert result.energy_kwh == pytest.approx(expected, rel=1e-9)


def test_simulation_is_deterministic() -> None:
    a, b = _run(23.0), _run(23.0)
    assert a.energy_kwh == b.energy_kwh
    assert a.zone_temp_c == b.zone_temp_c


def test_cop_degrades_with_ambient() -> None:
    params = ZoneThermalParams(floor_area_m2=1000.0)
    assert cop_cooling(20.0, params) > cop_cooling(38.0, params)
    assert cop_heating(10.0, params) > cop_heating(-8.0, params)
    assert cop_cooling(45.0, params) >= 1.2  # never unphysical


def test_bigger_zone_uses_more_energy() -> None:
    small = _run(23.0, ZoneThermalParams(floor_area_m2=500.0))
    large = _run(23.0, ZoneThermalParams(floor_area_m2=2000.0))
    assert large.energy_kwh > small.energy_kwh


def test_time_constants_are_in_a_building_like_range() -> None:
    taus = ZoneThermalParams(floor_area_m2=1500.0).time_constants_hours()
    assert 0.3 < taus["air"] < 4.0
    assert 4.0 < taus["mass"] < 80.0


def test_mismatched_input_lengths_are_rejected() -> None:
    with pytest.raises(ValueError, match="share a length"):
        RcThermalEngine().simulate(
            SimulationRequest(
                asset_id="t",
                zone_id="Z",
                start=datetime(2017, 8, 24),
                setpoints_c=[23.0, 23.0],
                outdoor_temp_c=[20.0],
                occupancy=[0.5, 0.5],
            )
        )


def test_parameters_are_reported_for_review() -> None:
    result = _run(23.0)
    assert "ua_per_m2" in result.parameters
    assert "time_constants_hours" in result.parameters
    assert result.parameters["integrator"] == "explicit Euler"


def test_boptest_client_lives_in_its_own_module_and_never_mislabels() -> None:
    """Structural, on purpose: in-process engines and the network client are
    separate modules, and the client only ever claims to be BOPTEST."""
    from core.adapters.building.boptest import BoptestEngine

    engine = BoptestEngine(base_url="")
    assert engine.engine is SimulationEngine.BOPTEST
    assert engine.available() is False, "no URL configured means not available"


def test_an_unreachable_boptest_falls_back_without_claiming_boptest(monkeypatch) -> None:
    monkeypatch.setenv("BOPTEST_URL", "http://127.0.0.1:1")
    engine = get_simulation_engine(prefer_boptest=True)
    assert engine.engine is SimulationEngine.ECOTWIN_RC
    result = _run(23.0)
    assert result.engine is not SimulationEngine.BOPTEST
