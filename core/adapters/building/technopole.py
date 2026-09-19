"""Adapter slot for a Schneider Technopole-style building digital twin.

Status: **not active**. As of this build, no Technopole / Grenoble campus
digital-twin dataset is publicly downloadable -- see `docs/data_provenance.md`
for what was checked. Rather than fabricate one, this adapter stays dormant and
activates automatically the moment matching files appear under
``data/raw/technopole/``.

It is deliberately written against a *declared* schema (``EXPECTED_COLUMNS``)
and validates the files it finds instead of assuming them, so a real drop-in
either works or fails loudly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from core.adapters.building.base import BuildingSourceAdapter, SiteDescriptor
from core.common import paths
from core.enums import DataMode

TECHNOPOLE_DIR = paths.RAW_DIR / "technopole"

#: Minimum columns a drop-in file must provide, in EcoTwin's internal names.
EXPECTED_COLUMNS = ("timestamp", "zone_id", "metric", "value", "unit")

#: Source column -> internal column. Extend when the real schema is published.
COLUMN_ALIASES: dict[str, str] = {
    "Timestamp": "timestamp",
    "DateTime": "timestamp",
    "ZoneId": "zone_id",
    "Zone": "zone_id",
    "Metric": "metric",
    "PointName": "metric",
    "Value": "value",
    "Unit": "unit",
}


def _discover() -> list[Any]:
    if not TECHNOPOLE_DIR.exists():
        return []
    return sorted(
        [p for p in TECHNOPOLE_DIR.rglob("*") if p.suffix.lower() in {".csv", ".parquet"}]
    )


class TechnopoleAdapter(BuildingSourceAdapter):
    key = "technopole"
    source_key = "ecotwin_fixture"  # re-pointed when a real source is registered
    data_mode = DataMode.SAMPLE_FIXTURE

    def available(self) -> bool:
        files = _discover()
        if not files:
            return False
        try:
            head = self._read(files[0], nrows=50)
        except Exception:
            return False
        return set(EXPECTED_COLUMNS).issubset(head.columns)

    @staticmethod
    def _read(path: Any, nrows: int | None = None) -> pd.DataFrame:
        frame = (
            pd.read_csv(path, nrows=nrows)
            if path.suffix.lower() == ".csv"
            else pd.read_parquet(path)
        )
        return frame.rename(columns=COLUMN_ALIASES)

    def list_sites(self) -> list[SiteDescriptor]:
        if not self.available():
            return []
        frames = [self._read(p) for p in _discover()]
        frame = pd.concat(frames, ignore_index=True)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        return [
            SiteDescriptor(
                site_id="technopole",
                name="Technopole campus",
                surface_m2=None,
                base_temperature_c=None,
                day_off={5: True, 6: True},
                first_timestamp=frame["timestamp"].min().to_pydatetime(),
                last_timestamp=frame["timestamp"].max().to_pydatetime(),
                metrics=tuple(sorted(frame["metric"].dropna().unique().tolist())),
                source_key=self.source_key,
                data_mode=DataMode.REAL_DATA,
                notes="Loaded from data/raw/technopole (schema validated on load).",
            )
        ]

    def load_frame(
        self,
        site_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        if not self.available():
            raise RuntimeError(
                "TechnopoleAdapter is dormant: no validated files under "
                f"{TECHNOPOLE_DIR}. See docs/data_provenance.md."
            )
        frames = [self._read(p) for p in _discover()]
        frame = pd.concat(frames, ignore_index=True)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        wide = frame.pivot_table(
            index="timestamp", columns="metric", values="value", aggfunc="mean"
        ).sort_index()
        wide["quality"] = "GOOD"
        if start is not None:
            wide = wide[wide.index >= pd.Timestamp(start)]
        if end is not None:
            wide = wide[wide.index < pd.Timestamp(end)]
        wide.index.name = "timestamp"
        return wide

    def describe_source(self) -> dict[str, object]:
        files = _discover()
        return {
            "adapter": self.key,
            "status": "ACTIVE" if self.available() else "DORMANT",
            "watch_directory": str(TECHNOPOLE_DIR),
            "expected_columns": list(EXPECTED_COLUMNS),
            "files_found": [str(p.name) for p in files],
            "note": (
                "No Technopole digital-twin dataset was publicly downloadable when "
                "this was built. The adapter activates automatically if matching "
                "files are placed in the watch directory."
            ),
        }
