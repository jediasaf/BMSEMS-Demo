"""The contract every building source must satisfy.

Written deliberately narrow: the AI, optimisation and UI layers only ever need
site metadata, a rectangular time-series frame and a data-quality view. A
future ``EcoStruxureBuildingOperationAdapter`` implements these four methods
against the EBO API and nothing downstream changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from core.enums import DataMode


@dataclass(frozen=True)
class SiteDescriptor:
    """Everything the platform knows about a building, independent of source."""

    site_id: str
    name: str
    surface_m2: float | None
    base_temperature_c: float | None
    #: Weekday index (0 = Monday) -> is the site normally closed that day.
    day_off: dict[int, bool] = field(default_factory=dict)
    timezone: str = "UTC"
    sampling_minutes: float = 15.0
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    metrics: tuple[str, ...] = ()
    source_key: str = "ecotwin_fixture"
    data_mode: DataMode = DataMode.SAMPLE_FIXTURE
    notes: str | None = None


class BuildingSourceAdapter(ABC):
    """Read-only access to one building data source."""

    #: Registry key, also shown in the UI status bar.
    key: str = "base"
    #: Provenance source key; must exist in ``core.provenance.sources.SOURCES``.
    source_key: str = "ecotwin_fixture"
    data_mode: DataMode = DataMode.SAMPLE_FIXTURE

    @abstractmethod
    def available(self) -> bool:
        """Can this adapter serve data right now? Checked before registration."""

    @abstractmethod
    def list_sites(self) -> list[SiteDescriptor]:
        """Every building this source exposes."""

    @abstractmethod
    def load_frame(
        self,
        site_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Time-series for one building on a strict grid.

        Index: tz-naive ``DatetimeIndex`` named ``timestamp``.
        Required columns: ``load_kw`` (float, NaN where unknown) and
        ``quality`` (``core.enums.Quality`` values as strings).
        Optional columns: ``outdoor_temp_c``, ``energy_wh_interval``,
        ``is_holiday``, ``is_day_off``.
        """

    @abstractmethod
    def describe_source(self) -> dict[str, object]:
        """Human-facing description for the data-quality drawer."""

    def site(self, site_id: str) -> SiteDescriptor:
        for descriptor in self.list_sites():
            if descriptor.site_id == site_id:
                return descriptor
        raise KeyError(f"unknown site {site_id!r} for adapter {self.key!r}")
