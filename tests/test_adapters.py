"""Adapter contract: shape, units, alignment and honest labelling."""

from __future__ import annotations

import pandas as pd
import pytest

from core.adapters.building.base import BuildingSourceAdapter
from core.adapters.building.fixture import FixtureBuildingAdapter
from core.adapters.building.technopole import TechnopoleAdapter
from core.adapters.power.base import PowerSourceAdapter
from core.adapters.power.facility import (
    ASSUMED_POWER_FACTOR,
    SIZING_HEADROOM,
    STANDARD_KVA,
    size_transformer,
)
from core.adapters.power.fixture import FixturePowerAdapter
from core.enums import DataMode
from tests.conftest import requires_real_data

REQUIRED_BUILDING_COLUMNS = {"load_kw", "quality"}


def _check_frame(frame: pd.DataFrame) -> None:
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.name == "timestamp"
    assert frame.index.is_monotonic_increasing
    assert frame.index.tz is None, "the source publishes no offset; stay naive"
    assert REQUIRED_BUILDING_COLUMNS.issubset(frame.columns)


def test_fixture_building_adapter_satisfies_the_contract() -> None:
    adapter = FixtureBuildingAdapter()
    assert isinstance(adapter, BuildingSourceAdapter)
    assert adapter.available()
    assert adapter.data_mode is DataMode.SAMPLE_FIXTURE
    sites = adapter.list_sites()
    assert sites
    frame = adapter.load_frame(sites[0].site_id)
    _check_frame(frame)
    assert (frame["load_kw"] > 0).all()


def test_fixture_is_deterministic() -> None:
    first = FixtureBuildingAdapter().load_frame("901")
    second = FixtureBuildingAdapter().load_frame("901")
    pd.testing.assert_frame_equal(first, second)


def test_fixture_describes_itself_as_a_fixture() -> None:
    description = FixtureBuildingAdapter().describe_source()
    assert "SAMPLE FIXTURE" in str(description["warning"])
    assert description["data_mode"] == "SAMPLE_FIXTURE"


def test_fixture_power_adapter_satisfies_the_contract() -> None:
    adapter = FixturePowerAdapter()
    assert isinstance(adapter, PowerSourceAdapter)
    facilities = adapter.list_facilities()
    assert facilities
    frame = adapter.load_frame(facilities[0].facility_id)
    _check_frame(frame)
    for facility in facilities:
        assert facility.transformer_kva >= facility.peak_kw


def test_unknown_asset_raises() -> None:
    with pytest.raises(KeyError):
        FixtureBuildingAdapter().site("does-not-exist")


def test_technopole_adapter_is_dormant_without_files() -> None:
    adapter = TechnopoleAdapter()
    description = adapter.describe_source()
    if not adapter.available():
        assert description["status"] == "DORMANT"
        with pytest.raises(RuntimeError, match="dormant"):
            adapter.load_frame("technopole")


@pytest.mark.parametrize("peak_kw", [10.0, 80.0, 120.0, 400.0, 3000.0])
def test_transformer_sizing_picks_a_standard_rating(peak_kw: float) -> None:
    rating = size_transformer(peak_kw)
    assert rating in STANDARD_KVA or rating % 500 == 0
    # Carries the peak with the documented headroom, and is the *smallest*
    # rating that does - an oversized transformer would flatter every loading
    # figure in the EMS.
    required_kva = peak_kw / ASSUMED_POWER_FACTOR * SIZING_HEADROOM
    assert rating >= required_kva
    smaller = [r for r in STANDARD_KVA if r < rating]
    if smaller:
        assert max(smaller) < required_kva


def test_transformer_sizing_is_monotonic() -> None:
    ratings = [size_transformer(p) for p in (10, 50, 100, 200, 400, 800, 1600)]
    assert ratings == sorted(ratings)


@requires_real_data
def test_real_building_adapter_frames_are_aligned(building_adapter) -> None:
    sites = building_adapter.list_sites()
    assert sites
    frame = building_adapter.load_frame(sites[0].site_id)
    _check_frame(frame)
    deltas = pd.Series(frame.index).diff().dropna().dt.total_seconds() / 60
    assert deltas.nunique() == 1, "grid must be strictly regular"
    assert deltas.iloc[0] == 15.0
    assert "outdoor_temp_c" in frame.columns


@requires_real_data
def test_real_adapter_reports_real_data_mode(building_adapter) -> None:
    assert building_adapter.data_mode is DataMode.REAL_DATA
    description = building_adapter.describe_source()
    assert description["unit_hypothesis"]["publisher_states_unit"] is False
    assert "DERIVED" in description["unit_hypothesis"]["consequence"]


@requires_real_data
def test_derived_kw_matches_the_published_counter(building_adapter) -> None:
    """load_kw must be exactly Wh-per-interval x 4 / 1000, not a fitted scale."""
    frame = building_adapter.load_frame(building_adapter.list_sites()[0].site_id)
    sample = frame.dropna(subset=["load_kw", "energy_wh_interval"]).head(500)
    expected = sample["energy_wh_interval"] * 4.0 / 1000.0
    pd.testing.assert_series_equal(sample["load_kw"], expected, check_names=False, rtol=1e-9)
