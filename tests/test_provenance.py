"""Provenance is a contract, so these tests are about what it *refuses*."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.enums import SimulationEngine, SourceType
from core.provenance import derived, injected, measured, optimised, predicted, simulated
from core.provenance.model import Provenance, ProvenancedSeries, as_replay
from core.provenance.sources import SOURCES, source


def test_measured_requires_a_real_measurement_source() -> None:
    with pytest.raises(ValidationError):
        measured("ecotwin_fixture", field="x", units="kW")


def test_simulated_requires_an_engine() -> None:
    with pytest.raises(ValidationError):
        Provenance(
            source_type=SourceType.SIMULATED,
            source_key="pandapower",
            source_name="x",
            publisher="y",
        )


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(KeyError):
        source("not_a_real_source")


def test_every_registered_source_is_self_consistent() -> None:
    for key, descriptor in SOURCES.items():
        assert descriptor.key == key
        assert descriptor.name and descriptor.publisher and descriptor.licence


def test_each_constructor_sets_the_expected_badge() -> None:
    cases = [
        (measured("power_laws_forecasting", field="Value", units="kWh"), "MEASURED"),
        (
            derived("power_laws_forecasting", field="Value", units="kW", processing="x4/1000"),
            "DERIVED",
        ),
        (predicted(model_id="m", units="kW"), "PREDICTED"),
        (simulated(SimulationEngine.PANDAPOWER, units="%"), "SIMULATED"),
        (optimised(units="°C", processing="cvxpy"), "OPTIMISED"),
        (injected(units="kW", processing="surge", scenario_id="s"), "INJECTED"),
    ]
    for provenance, badge in cases:
        assert provenance.badge == badge


def test_simulated_carries_the_engine_label() -> None:
    provenance = simulated(SimulationEngine.ECOTWIN_RC, units="kW")
    assert provenance.engine is SimulationEngine.ECOTWIN_RC
    assert "RC" in (provenance.engine_label or "")
    assert provenance.source_key == "ecotwin_rc"


def test_replay_preserves_the_originating_engine() -> None:
    original = simulated(SimulationEngine.BOPTEST, units="kW", processing="run")
    replay = as_replay(original, cache_key="abc")
    assert replay.engine is SimulationEngine.BOPTEST
    assert "SIMULATION REPLAY" in (replay.notes or "")
    assert "abc" in (replay.processing or "")


def test_fixture_provenance_is_flagged() -> None:
    provenance = derived("ecotwin_fixture", field="load", units="kW", processing="synthetic")
    assert provenance.is_fixture is True


def test_series_rejects_mismatched_lengths() -> None:
    provenance = predicted(model_id="m", units="kW")
    with pytest.raises(ValidationError):
        ProvenancedSeries(
            series_id="s",
            label="s",
            timestamps=[],
            values=[1.0],
            provenance=provenance,
        )


def test_series_rejects_a_band_of_the_wrong_length() -> None:
    import datetime as dt

    provenance = predicted(model_id="m", units="kW")
    now = dt.datetime(2017, 8, 24)
    with pytest.raises(ValidationError):
        ProvenancedSeries(
            series_id="s",
            label="s",
            timestamps=[now, now],
            values=[1.0, 2.0],
            lower=[0.0],
            provenance=provenance,
        )
