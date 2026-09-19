"""Scenarios must be deterministic, additive and clearly labelled."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.scenarios import (
    BMS_SCENARIOS,
    EMS_SCENARIOS,
    apply_bms_scenario,
    apply_ems_scenario,
    get_scenario,
    list_scenarios,
)


def _frame(n: int = 288) -> pd.DataFrame:
    index = pd.date_range("2017-08-24", periods=n, freq="15min", name="timestamp")
    hours = index.hour + index.minute / 60.0
    load = 30 + 50 * np.clip(np.sin(np.pi * (hours - 7) / 11), 0, 1)
    return pd.DataFrame(
        {"load_kw": load, "outdoor_temp_c": 22 + 6 * np.sin(2 * np.pi * (hours - 9) / 24)},
        index=index,
    )


def test_exactly_three_scenarios_per_module() -> None:
    assert len(BMS_SCENARIOS) == 3
    assert len(EMS_SCENARIOS) == 3
    assert sum(s.is_baseline for s in BMS_SCENARIOS) == 1
    assert sum(s.is_baseline for s in EMS_SCENARIOS) == 1


def test_every_scenario_explains_itself() -> None:
    for scenario in list_scenarios():
        assert scenario.description and scenario.teaches
        assert scenario.subtitle


def test_unknown_scenario_raises() -> None:
    with pytest.raises(KeyError):
        get_scenario("nope")


@pytest.mark.parametrize("scenario_id", [s.scenario_id for s in BMS_SCENARIOS])
def test_bms_scenarios_are_deterministic(scenario_id: str) -> None:
    frame = _frame()
    first, inj_a = apply_bms_scenario(frame, scenario_id, asset_id="t")
    second, inj_b = apply_bms_scenario(frame, scenario_id, asset_id="t")
    pd.testing.assert_frame_equal(first, second)
    assert (inj_a is None) == (inj_b is None)
    if inj_a and inj_b:
        assert inj_a.seed == inj_b.seed
        assert inj_a.peak_injection == inj_b.peak_injection


def test_seed_is_stable_across_processes() -> None:
    """hash() is salted per interpreter, so the seed must not come from it."""
    import subprocess
    import sys

    code = (
        "import sys; sys.path.insert(0, '.');"
        "from core.scenarios.registry import _seed_for;"
        "print(_seed_for('ems_ev_surge', '227'))"
    )
    runs = {
        subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        ).stdout.strip()
        for _ in range(2)
    }
    assert len(runs) == 1


def test_baseline_injects_nothing() -> None:
    frame = _frame()
    out, injection = apply_bms_scenario(frame, "bms_normal_day", asset_id="t")
    assert injection is None
    assert (out["injection_kw"] == 0).all()
    pd.testing.assert_series_equal(out["load_kw"], frame["load_kw"], check_names=False)


def test_bms_scenarios_preserve_the_measurement() -> None:
    frame = _frame()
    for scenario in BMS_SCENARIOS:
        out, _ = apply_bms_scenario(frame, scenario.scenario_id, asset_id="t")
        pd.testing.assert_series_equal(out["load_kw_measured"], frame["load_kw"], check_names=False)


def test_hot_day_raises_temperature_and_load() -> None:
    frame = _frame()
    out, injection = apply_bms_scenario(
        frame, "bms_hot_day", asset_id="t", hvac_sensitivity_kw_per_k=2.0
    )
    assert injection is not None
    assert (out["outdoor_temp_c"] > out["outdoor_temp_c_measured"]).all()
    assert out["load_kw"].mean() > frame["load_kw"].mean()
    assert injection.peak_injection > 0


def test_drift_grows_over_the_window_not_the_dataset() -> None:
    frame = _frame()
    out, injection = apply_bms_scenario(frame, "bms_sensor_drift", asset_id="t")
    assert injection is not None
    drift = out["injection_kw"].to_numpy()
    assert drift[0] < drift[-1]
    # A 9%/day drift over 3 days must stay a plausible bias, not a 10x blow-up.
    assert injection.detail["final_bias_kw"] < frame["load_kw"].max()


def test_ev_surge_is_additive_and_flagged_flexible() -> None:
    frame = _frame()
    out, injection = apply_ems_scenario(frame, "ems_ev_surge", asset_id="t")
    assert injection is not None
    pd.testing.assert_series_equal(out["load_kw"], frame["load_kw"], check_names=False)
    assert (out["flexible_kw"] == out["injection_kw"]).all()
    assert injection.peak_injection > 50


def test_ev_surge_is_a_bounded_daily_session() -> None:
    """A fleet charges every day, but only during its session window."""
    frame = _frame()
    out, injection = apply_ems_scenario(frame, "ems_ev_surge", asset_id="t")
    assert injection is not None
    active = out.index[out["injection_kw"] > 1.0]
    assert len(active) > 0
    for _, day in pd.Series(active, index=active).groupby(active.date):
        hours = day.dt.hour + day.dt.minute / 60.0
        assert hours.max() - hours.min() <= 4.5
        assert hours.min() >= 12.5
    # And it is off overnight on every day.
    overnight = out.between_time("00:00", "06:00")["injection_kw"]
    assert (overnight < 1e-6).all()


def test_peak_demand_is_not_marked_flexible() -> None:
    frame = _frame()
    out, injection = apply_ems_scenario(frame, "ems_peak_demand", asset_id="t")
    assert injection is not None
    assert (out["flexible_kw"] == 0).all()


def test_different_assets_get_different_seeds() -> None:
    frame = _frame()
    _, a = apply_ems_scenario(frame, "ems_ev_surge", asset_id="1")
    _, b = apply_ems_scenario(frame, "ems_ev_surge", asset_id="2")
    assert a and b and a.seed != b.seed
