"""Building adapter over the processed Schneider / DrivenData public dataset.

This is the real-data path. It reads only what ``scripts/prepare_data.py``
wrote, so the expensive CSV work happens once, offline.

Honest labelling, enforced here rather than in the UI:

* ``energy_wh_interval`` is the published measurement -> MEASURED.
* ``load_kw`` is arithmetic on it under a stated unit hypothesis -> DERIVED.
* ``outdoor_temp_c`` is a published station reading resampled onto the load
  grid -> MEASURED where observed, INTERPOLATED where filled.
* Zone-level thermal state does **not** exist in this source. It is never
  invented here; the Control Lab produces it and tags it SIMULATED.
"""

from __future__ import annotations

import functools
import json
import os
from datetime import datetime
from typing import Any

import pandas as pd

from core.adapters.building.base import BuildingSourceAdapter, SiteDescriptor
from core.common import paths
from core.common.ids import as_numeric_id
from core.enums import DataMode

#: Env var naming the sites the demo surface offers, comma-separated.
#: Unset means every site ``prepare_data.py`` prepared.
DEMO_SITE_IDS_ENV = "ECOTWIN_DEMO_SITE_IDS"


def _wanted_site_ids() -> list[str]:
    raw = os.environ.get(DEMO_SITE_IDS_ENV, "").strip()
    return [part.strip() for part in raw.split(",") if part.strip()]


def _restrict(selection: dict[str, Any]) -> dict[str, Any]:
    """Narrow the served catalogue, and record in the payload that it was.

    Why narrow at all: the static recording writes one file per site, scenario
    and cursor, so its size is linear in the number of buildings, and most of
    that weight is buildings nobody opens. Narrowing here rather than in the UI
    keeps the whole surface agreeing with itself -- the portfolio KPIs, the risk
    counts, the dropdowns and the recording all describe the same buildings,
    instead of a table that contradicts the number printed above it.

    What it must not do is quietly serve a different set than it was asked for,
    so an id that is not in the prepared data raises rather than being dropped.
    """
    wanted = _wanted_site_ids()
    prepared = selection.get("sites")
    if not wanted or not isinstance(prepared, list):
        return selection
    known = {str(site.get("site_id")) for site in prepared}
    unknown = sorted(set(wanted) - known)
    if unknown:
        raise ValueError(
            f"{DEMO_SITE_IDS_ENV} names site(s) that are not in the prepared "
            f"dataset: {', '.join(unknown)}. Prepared: {', '.join(sorted(known))}."
        )
    # The BMS lead site carries the curated workflow the demo walks through,
    # so it stays in the catalogue whether or not it was asked for.
    lead = selection.get("bms_site")
    keep = set(wanted) | ({str(lead)} if lead is not None else set())
    out = dict(selection)
    out["sites"] = [site for site in prepared if str(site.get("site_id")) in keep]
    out["ems_sites"] = [sid for sid in selection.get("ems_sites", []) if str(sid) in keep]
    out["catalogue"] = {
        "sites_prepared": len(prepared),
        "sites_served": len(out["sites"]),
        "site_ids": [str(site["site_id"]) for site in out["sites"]],
        "note": (
            f"{DEMO_SITE_IDS_ENV} narrows the catalogue this instance serves. "
            "The prepared dataset holds sites_prepared sites; the rest are on "
            "disk and unserved, not missing."
        ),
    }
    return out


@functools.lru_cache(maxsize=1)
def load_selection() -> dict[str, Any]:
    """The decisions ``prepare_data.py`` made, or an empty marker.

    Cached, so a change to ``ECOTWIN_DEMO_SITE_IDS`` after the first call needs
    ``load_selection.cache_clear()`` to take effect.
    """
    if not paths.SELECTION_JSON.exists():
        return {"status": "NO_RAW_DATA", "mode": "SAMPLE_FIXTURE"}
    return _restrict(json.loads(paths.SELECTION_JSON.read_text()))


@functools.lru_cache(maxsize=1)
def _load_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    load = pd.read_parquet(paths.LOAD_PARQUET)
    weather = pd.read_parquet(paths.WEATHER_PARQUET)
    holidays = (
        pd.read_parquet(paths.HOLIDAYS_PARQUET)
        if paths.HOLIDAYS_PARQUET.exists()
        else pd.DataFrame(columns=["site_id", "date", "holiday"])
    )
    return load, weather, holidays


def processed_data_available() -> bool:
    selection = load_selection()
    return (
        selection.get("status") == "OK"
        and paths.LOAD_PARQUET.exists()
        and paths.WEATHER_PARQUET.exists()
    )


def demo_window() -> tuple[pd.Timestamp, pd.Timestamp] | None:
    selection = load_selection()
    window = selection.get("demo_window")
    if not window:
        return None
    return pd.Timestamp(window["start"]), pd.Timestamp(window["end"])


def site_name(site_id: int | str) -> str:
    """Stable, non-misleading display name.

    The publisher anonymises sites, so we do not invent a street address or
    claim a named Schneider campus. ``Site 063`` is what the source says.
    """
    return f"Site {int(site_id):03d}"


class PowerLawsBuildingAdapter(BuildingSourceAdapter):
    key = "power_laws_building"
    source_key = "power_laws_forecasting"
    data_mode = DataMode.REAL_DATA

    def available(self) -> bool:
        return processed_data_available()

    def _profiles(self) -> dict[int, dict[str, Any]]:
        selection = load_selection()
        return {int(s["site_id"]): s for s in selection.get("sites", [])}

    def list_sites(self) -> list[SiteDescriptor]:
        if not self.available():
            return []
        selection = load_selection()
        load, _, _ = _load_tables()
        out: list[SiteDescriptor] = []
        for site_id, profile in self._profiles().items():
            frame = load[load["site_id"] == site_id]
            if frame.empty:
                continue
            raw_day_off = profile.get("day_off") or {}
            out.append(
                SiteDescriptor(
                    site_id=str(site_id),
                    name=site_name(site_id),
                    surface_m2=float(profile["surface_m2"]),
                    base_temperature_c=float(profile["base_temperature_c"]),
                    day_off={int(k): bool(v) for k, v in raw_day_off.items()},
                    sampling_minutes=15.0,
                    first_timestamp=frame["timestamp"].min().to_pydatetime(),
                    last_timestamp=frame["timestamp"].max().to_pydatetime(),
                    metrics=("load_kw", "energy_wh_interval", "outdoor_temp_c"),
                    source_key=self.source_key,
                    data_mode=DataMode.REAL_DATA,
                    notes=(
                        f"Published floor area {profile['surface_m2']:.0f} m2; "
                        f"median power density {profile['w_per_m2_median']:.1f} W/m2. "
                        f"Selected as BMS lead site: "
                        f"{site_id == selection.get('bms_site')}."
                    ),
                )
            )
        return sorted(out, key=lambda s: int(s.site_id))

    def load_frame(
        self,
        site_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        load, weather, holidays = _load_tables()
        sid = as_numeric_id(site_id, kind="site")
        frame = load[load["site_id"] == sid].set_index("timestamp").sort_index()
        if frame.empty:
            raise KeyError(f"no processed data for site {site_id}")
        wx = weather[weather["site_id"] == sid].set_index("timestamp").sort_index()

        out = pd.DataFrame(
            {
                "load_kw": frame["load_kw"],
                "energy_wh_interval": frame["energy_wh_interval"],
                "quality": frame["quality"],
            }
        )
        out["outdoor_temp_c"] = wx["outdoor_temp_c"].reindex(out.index)
        out["weather_quality"] = wx["quality"].reindex(out.index).fillna("MISSING")

        descriptor = self.site(site_id)
        dow = out.index.dayofweek
        out["is_day_off"] = [bool(descriptor.day_off.get(int(d), False)) for d in dow]
        site_holidays = set(pd.to_datetime(holidays[holidays["site_id"] == sid]["date"]).dt.date)
        out["is_holiday"] = [ts.date() in site_holidays for ts in out.index]

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
            "grid": selection.get("grid", "15min"),
            "unit_hypothesis": selection.get("unit_hypothesis"),
            "selection_rule": selection.get("selection_rule"),
            "demo_window": selection.get("demo_window"),
            "prepared_at": selection.get("generated_at"),
            "files": [
                str(paths.LOAD_PARQUET.relative_to(paths.REPO_ROOT)),
                str(paths.WEATHER_PARQUET.relative_to(paths.REPO_ROOT)),
                str(paths.HOLIDAYS_PARQUET.relative_to(paths.REPO_ROOT)),
            ],
        }
