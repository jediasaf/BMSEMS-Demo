"""Facility (meter) adapter over the processed Schneider / DrivenData dataset.

The source publishes a whole-site meter only. EcoTwin does **not** invent
sub-meter categories that the data cannot support: the split into HVAC /
lighting / process / flexible feeders happens in the network model, is computed
by a documented disaggregation, and is tagged DERIVED there -- never presented
as a measured sub-meter.
"""

from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from core.adapters.building.power_laws import (
    _load_tables,
    load_selection,
    processed_data_available,
    site_name,
)
from core.adapters.power.base import FacilityDescriptor, PowerSourceAdapter
from core.common.ids import as_numeric_id
from core.enums import DataMode

#: Standard IEC 60076 distribution-transformer ratings, in kVA.
STANDARD_KVA = (100, 160, 250, 400, 630, 800, 1000, 1250, 1600, 2000, 2500)
#: Assumed displacement power factor for a commercial LV installation.
ASSUMED_POWER_FACTOR = 0.95
#: Design headroom over the observed peak when sizing the serving transformer.
SIZING_HEADROOM = 1.25


def size_transformer(peak_kw: float, power_factor: float = ASSUMED_POWER_FACTOR) -> float:
    """Smallest standard rating that carries ``peak_kw`` with design headroom.

    The source does not publish transformer data, so the rating is DERIVED from
    the observed peak by ordinary LV design practice, and the assumption is
    carried in provenance wherever a loading percentage is shown.
    """
    required_kva = peak_kw / max(power_factor, 1e-6) * SIZING_HEADROOM
    for rating in STANDARD_KVA:
        if rating >= required_kva:
            return float(rating)
    return float(math.ceil(required_kva / 500.0) * 500)


class FacilityPowerAdapter(PowerSourceAdapter):
    key = "power_laws_facility"
    source_key = "power_laws_forecasting"
    data_mode = DataMode.REAL_DATA

    def available(self) -> bool:
        return processed_data_available()

    def list_facilities(self) -> list[FacilityDescriptor]:
        if not self.available():
            return []
        selection = load_selection()
        load, _, _ = _load_tables()
        chosen = selection.get("ems_sites", [])
        profiles = {int(s["site_id"]): s for s in selection.get("sites", [])}
        out: list[FacilityDescriptor] = []
        for site_id in chosen:
            profile = profiles.get(int(site_id))
            frame = load[load["site_id"] == int(site_id)]
            if profile is None or frame.empty:
                continue
            peak = float(profile["p99_kw"])
            out.append(
                FacilityDescriptor(
                    facility_id=str(site_id),
                    name=site_name(site_id),
                    surface_m2=float(profile["surface_m2"]),
                    main_meter_id=f"MM-{int(site_id):03d}",
                    transformer_kva=size_transformer(peak),
                    baseline_kw=float(profile["median_kw"]),
                    peak_kw=peak,
                    sampling_minutes=15.0,
                    source_key=self.source_key,
                    data_mode=DataMode.REAL_DATA,
                    first_timestamp=frame["timestamp"].min().to_pydatetime(),
                    last_timestamp=frame["timestamp"].max().to_pydatetime(),
                    notes=(
                        f"Transformer rating DERIVED: smallest standard kVA covering the "
                        f"P99 load of {peak:.0f} kW at pf {ASSUMED_POWER_FACTOR} with "
                        f"{SIZING_HEADROOM:.0%} headroom."
                    ),
                )
            )
        return out

    def load_frame(
        self,
        facility_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        load, weather, _ = _load_tables()
        sid = as_numeric_id(facility_id, kind="facility")
        frame = load[load["site_id"] == sid].set_index("timestamp").sort_index()
        if frame.empty:
            raise KeyError(f"no processed data for facility {facility_id}")
        wx = weather[weather["site_id"] == sid].set_index("timestamp").sort_index()
        out = pd.DataFrame(
            {
                "load_kw": frame["load_kw"],
                "energy_wh_interval": frame["energy_wh_interval"],
                "quality": frame["quality"],
            }
        )
        out["outdoor_temp_c"] = wx["outdoor_temp_c"].reindex(out.index)
        if start is not None:
            out = out[out.index >= pd.Timestamp(start)]
        if end is not None:
            out = out[out.index < pd.Timestamp(end)]
        out.index.name = "timestamp"
        return out

    def describe_source(self) -> dict[str, object]:
        selection = load_selection()
        return {
            "adapter": self.key,
            "source_key": self.source_key,
            "data_mode": self.data_mode.value,
            "unit_hypothesis": selection.get("unit_hypothesis"),
            "transformer_sizing": {
                "rule": "smallest IEC standard kVA >= P99 kW / pf * headroom",
                "power_factor": ASSUMED_POWER_FACTOR,
                "headroom": SIZING_HEADROOM,
                "source_type": "DERIVED",
                "note": "The dataset publishes no transformer nameplate data.",
            },
            "submetering": {
                "published": False,
                "note": (
                    "Only a whole-site meter exists. Feeder-level values in the "
                    "network model are DERIVED by documented disaggregation, never "
                    "presented as measured sub-meters."
                ),
            },
        }
