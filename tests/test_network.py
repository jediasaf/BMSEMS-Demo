"""pandapower model: topology, convergence and electrical sanity."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from core.adapters.power.pandapower_adapter import (
    FEEDER_CABLES,
    LOADING_CRITICAL_PCT,
    POWER_FACTOR,
    VOLTAGE_LIMITS,
    FeederSplit,
    PandapowerNetwork,
    disaggregate,
    estimate_hvac_sensitivity,
)


@pytest.fixture(scope="module")
def network() -> PandapowerNetwork:
    net = PandapowerNetwork("t", 250.0)
    net.build()
    return net


def _split(total: float, flexible: float = 0.0) -> FeederSplit:
    return disaggregate(
        total,
        base_kw=20.0,
        outdoor_temp_c=30.0,
        base_temperature_c=18.0,
        hvac_sensitivity_kw_per_k=2.0,
        flexible_kw=flexible,
    )


def test_load_flow_converges(network: PandapowerNetwork) -> None:
    state = network.solve(_split(120.0))
    assert state.converged
    assert state.status in {"NORMAL", "WARNING", "CRITICAL"}


def test_loading_rises_with_load(network: PandapowerNetwork) -> None:
    loadings = [
        network.solve(_split(total)).transformer_loading_pct for total in (40, 90, 150, 220)
    ]
    assert loadings == sorted(loadings)


def test_voltage_falls_as_load_rises(network: PandapowerNetwork) -> None:
    light = network.solve(_split(40.0))
    heavy = network.solve(_split(220.0))
    assert heavy.lv_bus_voltage_pu < light.lv_bus_voltage_pu
    assert light.lv_bus_voltage_pu <= 1.0 + 1e-6


def test_losses_rise_with_load(network: PandapowerNetwork) -> None:
    assert network.solve(_split(200.0)).losses_kw > network.solve(_split(50.0)).losses_kw


def test_losses_are_a_small_share_of_throughput(network: PandapowerNetwork) -> None:
    state = network.solve(_split(150.0))
    assert 0 < state.losses_kw < 0.1 * state.total_load_kw


def test_overload_is_flagged_with_a_violation(network: PandapowerNetwork) -> None:
    state = network.solve(_split(150.0, flexible=180.0))
    assert state.transformer_loading_pct > LOADING_CRITICAL_PCT
    assert state.status == "CRITICAL"
    assert any("exceeds nameplate" in v for v in state.violations)


def test_a_normal_load_has_no_violations(network: PandapowerNetwork) -> None:
    state = network.solve(_split(80.0))
    assert state.violations == []
    for name, value in state.bus_voltages_pu.items():
        if name != "MV-GRID":
            assert VOLTAGE_LIMITS[0] <= value <= VOLTAGE_LIMITS[1]


def test_injected_load_is_additive_not_netted() -> None:
    plain = _split(100.0)
    surged = _split(100.0, flexible=60.0)
    assert surged.total() == pytest.approx(plain.total() + 60.0, rel=1e-9)
    # The measured part of the split is untouched by the injection.
    assert surged.hvac_kw == pytest.approx(plain.hvac_kw)
    assert surged.office_kw == pytest.approx(plain.office_kw)


def test_disaggregation_conserves_the_total() -> None:
    split = _split(137.0)
    assert split.total() == pytest.approx(137.0, rel=1e-6)


def test_hvac_share_tracks_degree_hours() -> None:
    warm = disaggregate(
        100.0,
        base_kw=20.0,
        outdoor_temp_c=34.0,
        base_temperature_c=18.0,
        hvac_sensitivity_kw_per_k=2.0,
    )
    mild = disaggregate(
        100.0,
        base_kw=20.0,
        outdoor_temp_c=18.0,
        base_temperature_c=18.0,
        hvac_sensitivity_kw_per_k=2.0,
    )
    assert warm.hvac_kw > mild.hvac_kw


def test_capacity_calibration_lands_on_nameplate(network: PandapowerNetwork) -> None:
    """The point of the bisection: kVA x pf is not the same as 100% loading."""
    reference = _split(120.0)
    cap = network.capacity_kw(reference)
    state = network.solve(
        FeederSplit(
            hvac_kw=reference.hvac_kw * cap / reference.total(),
            lighting_kw=reference.lighting_kw * cap / reference.total(),
            office_kw=reference.office_kw * cap / reference.total(),
            flexible_kw=reference.flexible_kw * cap / reference.total(),
        )
    )
    assert state.transformer_loading_pct == pytest.approx(LOADING_CRITICAL_PCT, abs=0.1)
    # And it is materially different from the naive shortcut.
    naive = 250.0 * POWER_FACTOR
    assert abs(cap - naive) > 1.0


def test_topology_is_described_for_the_ui(network: PandapowerNetwork) -> None:
    topology = network.topology()
    assert topology["transformer"]["vector_group"] == "Dyn11"
    assert len(topology["feeders"]) == len(FEEDER_CABLES)
    assert any(feeder["flexible"] for feeder in topology["feeders"])


def test_state_carries_its_assumptions(network: PandapowerNetwork) -> None:
    state = network.solve(_split(100.0))
    assert any("DERIVED" in a for a in state.assumptions)
    assert any("sub-meter" in a for a in state.assumptions)


def test_hvac_sensitivity_is_estimated_from_history() -> None:
    rng = np.random.default_rng(1)
    temp = rng.uniform(5, 35, 3000)
    degree_hours = np.maximum(temp - 18, 0) + np.maximum(14 - temp, 0)
    load = 30 + 2.5 * degree_hours + rng.normal(0, 1.0, 3000)
    slope = estimate_hvac_sensitivity(load, temp, 18.0)
    assert 2.0 < slope < 3.0


def test_hvac_sensitivity_is_zero_without_enough_data() -> None:
    assert estimate_hvac_sensitivity(np.array([1.0, 2.0]), np.array([10.0, 11.0]), 18.0) == 0.0


def test_feeders_are_sized_for_the_facility() -> None:
    """One cable size for every facility made a large site's feeders bind
    before its transformer, and the calibrated capacity came out at a third of
    nameplate."""
    from core.adapters.power.pandapower_adapter import parallel_circuits

    small = parallel_circuits(100.0, "F1_HVAC")
    large = parallel_circuits(7000.0, "F1_HVAC")
    assert small == 1
    assert large > small
    assert all(parallel_circuits(kva, "F1_HVAC") >= 1 for kva in (50, 250, 1600))


@pytest.mark.parametrize("kva", [100.0, 250.0, 800.0, 2000.0, 7000.0])
def test_calibrated_capacity_is_close_to_nameplate_at_every_scale(kva: float) -> None:
    net = PandapowerNetwork("t", kva)
    net.build()
    reference = disaggregate(
        kva * 0.4,
        base_kw=kva * 0.1,
        outdoor_temp_c=28.0,
        base_temperature_c=18.0,
        hvac_sensitivity_kw_per_k=kva * 0.01,
    )
    cap = net.capacity_kw(reference)
    naive = kva * POWER_FACTOR
    # Below the naive figure (losses and reactive flow), but not far below:
    # a much smaller ratio means something other than the transformer binds.
    assert 0.85 <= cap / naive <= 1.0


def test_the_model_survives_being_solved_from_two_threads() -> None:
    """A load flow is not an atomic read, and this model is shared.

    ``solve`` writes the loads in, runs Newton-Raphson, then reads the results
    back out. The API warms every facility's capacity on a background thread
    while request handlers are already solving, so those three steps interleave
    for real. Before the lock, that handed callers another load's answer: the
    capacity bisection returned 131.683 kW where it should return 144.940, and
    50.042 where it should return 91.013, from identical inputs.

    Each thread here checks its own answer against the single-threaded one, so
    a torn read fails the test rather than merely looking odd.
    """
    net = PandapowerNetwork("t", 250.0)
    net.build()

    loads = [40.0, 80.0, 120.0, 160.0, 200.0]
    expected = {kw: net.solve(_split(kw)).transformer_loading_pct for kw in loads}

    wrong: list[str] = []

    def hammer(kw: float) -> None:
        for _ in range(12):
            got = net.solve(_split(kw)).transformer_loading_pct
            if not np.isclose(got, expected[kw], atol=1e-6):
                wrong.append(f"{kw} kW read {got:.4f}, not {expected[kw]:.4f}")

    threads = [threading.Thread(target=hammer, args=(kw,)) for kw in loads * 3]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not wrong, "\n".join(wrong[:10])


def test_capacity_calibration_survives_concurrent_solves() -> None:
    """The same, for the number the EMS optimiser is actually held to."""
    net = PandapowerNetwork("t", 250.0)
    net.build()
    reference = _split(120.0)
    expected = net.capacity_kw(reference)

    caps: list[float] = []
    noise = [True]

    def solve_other_loads() -> None:
        while noise[0]:
            for kw in (10.0, 240.0, 5_000.0):
                net.solve(_split(kw), quiet=True)

    background = threading.Thread(target=solve_other_loads, daemon=True)
    background.start()
    try:
        for _ in range(3):
            caps.append(net.capacity_kw(reference))
    finally:
        noise[0] = False
        background.join(timeout=10)

    assert all(c == pytest.approx(expected, abs=1e-6) for c in caps), caps


def test_capacity_says_so_rather_than_guessing_when_the_bracket_is_wrong(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A search that cannot find the answer must not return its last guess.

    Bisection is only valid while the bracket contains the answer. A reference
    that already overloads the transformer at 5% of itself breaks that, and
    the old loop would walk the bracket down and return the collapsed
    midpoint as though it were a measurement.
    """
    net = PandapowerNetwork("t", 100.0)
    net.build()
    # 5% of this reference is already far past a 100 kVA transformer.
    reference = _split(40_000.0)
    with caplog.at_level("WARNING"):
        cap = net.capacity_kw(reference)
    assert cap == pytest.approx(100.0 * POWER_FACTOR)
    assert "nameplate" in caplog.text.lower()
