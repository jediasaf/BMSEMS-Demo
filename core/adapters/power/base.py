"""The contract every power/meter source must satisfy.

A future ``PowerMonitoringExpertAdapter`` implements these against the PME
web services; the forecaster, the network model and the optimiser are unaware.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from core.enums import DataMode


@dataclass(frozen=True)
class FacilityDescriptor:
    """A metered facility in the portfolio."""

    facility_id: str
    name: str
    surface_m2: float | None
    main_meter_id: str
    #: Nameplate rating of the serving transformer, in kVA.
    transformer_kva: float
    baseline_kw: float
    peak_kw: float
    timezone: str = "UTC"
    sampling_minutes: float = 15.0
    source_key: str = "ecotwin_fixture"
    data_mode: DataMode = DataMode.SAMPLE_FIXTURE
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    notes: str | None = None


class PowerSourceAdapter(ABC):
    """Read-only access to one electrical-metering source."""

    key: str = "base"
    source_key: str = "ecotwin_fixture"
    data_mode: DataMode = DataMode.SAMPLE_FIXTURE

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def list_facilities(self) -> list[FacilityDescriptor]: ...

    @abstractmethod
    def load_frame(
        self,
        facility_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Main-meter time-series on a strict grid.

        Index: tz-naive ``DatetimeIndex`` named ``timestamp``.
        Required columns: ``load_kw``, ``quality``.
        Optional: ``outdoor_temp_c``, ``energy_wh_interval``.
        """

    @abstractmethod
    def describe_source(self) -> dict[str, object]: ...

    def facility(self, facility_id: str) -> FacilityDescriptor:
        for descriptor in self.list_facilities():
            if descriptor.facility_id == facility_id:
                return descriptor
        raise KeyError(f"unknown facility {facility_id!r} for adapter {self.key!r}")
