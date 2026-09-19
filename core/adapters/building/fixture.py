"""Seeded synthetic building, used only when no real source is present.

Every value it emits is tagged ``SAMPLE FIXTURE`` and the UI status bar
switches to ``SAMPLE FIXTURE`` mode, so a fixture number can never be mistaken
for a measurement. The generator is physically motivated rather than random
noise -- a base load, an occupancy-driven component and a weather-driven HVAC
component -- so the AI layer is exercised on a realistic shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from core.adapters.building.base import BuildingSourceAdapter, SiteDescriptor
from core.common.ids import as_numeric_id
from core.enums import DataMode

SEED = 20240312
FIXTURE_START = pd.Timestamp("2016-03-07 00:00:00")
FIXTURE_DAYS = 120
GRID_MINUTES = 15


def _synthesise(site_id: int, days: int, start: pd.Timestamp) -> pd.DataFrame:
    rng = np.random.default_rng(SEED + site_id)
    index = pd.date_range(start, periods=days * 24 * 60 // GRID_MINUTES, freq="15min")
    hours = index.hour + index.minute / 60.0
    dow = index.dayofweek
    day_of_year = index.dayofyear

    # Outdoor temperature: seasonal mean + diurnal swing + correlated noise.
    seasonal = 9.0 + 9.0 * np.sin(2 * np.pi * (day_of_year - 105) / 365.0)
    diurnal = 4.0 * np.sin(2 * np.pi * (hours - 9.0) / 24.0)
    noise = pd.Series(rng.normal(0, 1.1, len(index))).rolling(8, min_periods=1).mean().to_numpy()
    outdoor = seasonal + diurnal + noise

    # Occupancy: weekday ramp, near-zero at weekends.
    occupied = np.clip(
        np.exp(-0.5 * ((hours - 13.0) / 3.4) ** 2) * 1.08 - 0.06,
        0.0,
        1.0,
    )
    occupied = np.where(dow >= 5, occupied * 0.08, occupied)

    base_kw = 20.0 + 0.6 * site_id % 7
    occupancy_kw = 62.0 * occupied
    # Degree-day style HVAC response around a 17 C balance point.
    heating = np.clip(17.0 - outdoor, 0, None) * 1.35
    cooling = np.clip(outdoor - 21.5, 0, None) * 1.9
    hvac_kw = (heating + cooling) * (0.35 + 0.65 * occupied)

    load = base_kw + occupancy_kw + hvac_kw
    load *= 1.0 + rng.normal(0, 0.022, len(index))
    load = np.clip(load, 4.0, None)

    return pd.DataFrame(
        {
            "load_kw": load,
            "energy_wh_interval": load * 1000.0 / 4.0,
            "outdoor_temp_c": outdoor,
            "quality": "GOOD",
            "weather_quality": "GOOD",
        },
        index=index,
    )


class FixtureBuildingAdapter(BuildingSourceAdapter):
    key = "fixture_building"
    source_key = "ecotwin_fixture"
    data_mode = DataMode.SAMPLE_FIXTURE

    #: Kept small on purpose: the fixture exists to keep the app alive, not to
    #: pretend to be a portfolio.
    SITE_IDS = (901, 902, 903)

    def available(self) -> bool:
        return True

    def list_sites(self) -> list[SiteDescriptor]:
        return [
            SiteDescriptor(
                site_id=str(sid),
                name=f"SAMPLE FIXTURE Building {sid}",
                surface_m2=2400.0 + 600.0 * idx,
                base_temperature_c=18.0,
                day_off={5: True, 6: True},
                sampling_minutes=float(GRID_MINUTES),
                first_timestamp=FIXTURE_START.to_pydatetime(),
                last_timestamp=(FIXTURE_START + timedelta(days=FIXTURE_DAYS)).to_pydatetime(),
                metrics=("load_kw", "energy_wh_interval", "outdoor_temp_c"),
                source_key=self.source_key,
                data_mode=DataMode.SAMPLE_FIXTURE,
                notes="Synthetic, seeded. Not a measurement of any real building.",
            )
            for idx, sid in enumerate(self.SITE_IDS)
        ]

    def load_frame(
        self,
        site_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        frame = _synthesise(as_numeric_id(site_id, kind="site"), FIXTURE_DAYS, FIXTURE_START)
        descriptor = self.site(site_id)
        dow = frame.index.dayofweek
        frame["is_day_off"] = [bool(descriptor.day_off.get(int(d), False)) for d in dow]
        frame["is_holiday"] = False
        if start is not None:
            frame = frame[frame.index >= pd.Timestamp(start)]
        if end is not None:
            frame = frame[frame.index < pd.Timestamp(end)]
        frame.index.name = "timestamp"
        return frame

    def describe_source(self) -> dict[str, object]:
        return {
            "adapter": self.key,
            "source_key": self.source_key,
            "data_mode": self.data_mode.value,
            "grid": "15min",
            "seed": SEED,
            "warning": (
                "SAMPLE FIXTURE. Synthetic, deterministic values generated because no "
                "real source files are present. Not a measurement."
            ),
            "generator": (
                "base load + Gaussian occupancy profile + degree-day HVAC response "
                "around a 17 C balance point"
            ),
        }
