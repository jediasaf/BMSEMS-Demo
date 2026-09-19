"""Seeded synthetic facility portfolio, used only when no real source exists."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.adapters.building.fixture import FIXTURE_DAYS, FIXTURE_START, _synthesise
from core.adapters.power.base import FacilityDescriptor, PowerSourceAdapter
from core.adapters.power.facility import size_transformer
from core.common.ids import as_numeric_id
from core.enums import DataMode

FIXTURE_FACILITIES = (901, 902, 903, 904, 905, 906)
#: Scales the shared building generator so the portfolio is not six clones.
SCALE = {901: 1.0, 902: 2.4, 903: 0.6, 904: 3.1, 905: 1.7, 906: 0.9}


class FixturePowerAdapter(PowerSourceAdapter):
    key = "fixture_facility"
    source_key = "ecotwin_fixture"
    data_mode = DataMode.SAMPLE_FIXTURE

    def available(self) -> bool:
        return True

    def list_facilities(self) -> list[FacilityDescriptor]:
        out: list[FacilityDescriptor] = []
        for fid in FIXTURE_FACILITIES:
            frame = self.load_frame(str(fid))
            peak = float(frame["load_kw"].quantile(0.99))
            out.append(
                FacilityDescriptor(
                    facility_id=str(fid),
                    name=f"SAMPLE FIXTURE Facility {fid}",
                    surface_m2=2400.0 * SCALE[fid],
                    main_meter_id=f"MM-{fid}",
                    transformer_kva=size_transformer(peak),
                    baseline_kw=float(frame["load_kw"].median()),
                    peak_kw=peak,
                    source_key=self.source_key,
                    data_mode=DataMode.SAMPLE_FIXTURE,
                    first_timestamp=frame.index.min().to_pydatetime(),
                    last_timestamp=frame.index.max().to_pydatetime(),
                    notes="Synthetic, seeded. Not a measurement of any real facility.",
                )
            )
        return out

    def load_frame(
        self,
        facility_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        fid = as_numeric_id(facility_id, kind="facility")
        frame = _synthesise(fid, FIXTURE_DAYS, FIXTURE_START)
        frame["load_kw"] = frame["load_kw"] * SCALE.get(fid, 1.0)
        frame["energy_wh_interval"] = frame["load_kw"] * 1000.0 / 4.0
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
            "warning": "SAMPLE FIXTURE. Synthetic, deterministic. Not a measurement.",
        }
