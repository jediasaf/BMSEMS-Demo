"""Controlled vocabularies.

These enums are the contract between the backend and the UI. The UI renders a
provenance badge for every value it draws, and the badge text is exactly the
``SourceType`` member name — so adding a member here is a UI-visible change.
"""

from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    """How a number came to exist. Never widen the meaning of a member.

    MEASURED  - read from a published measurement in a source dataset, at most
                resampled/aggregated. The underlying observation is real.
    PREDICTED - produced by a forecasting model from measured history.
    SIMULATED - produced by a physics / network solver (pandapower, BOPTEST,
                the EcoTwin RC thermal engine). Not an observation.
    OPTIMISED - produced by a constrained optimiser as a proposed setpoint or
                dispatch. Not an observation and not yet applied anywhere.
    DERIVED   - computed deterministically from measured values plus published
                metadata (e.g. kW from kWh-per-interval, EUI from floor area).
    INJECTED  - a deliberate, seeded scenario disturbance added by EcoTwin for
                what-if testing. Always synthetic, always labelled.
    """

    MEASURED = "MEASURED"
    PREDICTED = "PREDICTED"
    SIMULATED = "SIMULATED"
    OPTIMISED = "OPTIMISED"
    DERIVED = "DERIVED"
    INJECTED = "INJECTED"


class Quality(str, Enum):
    """Point-level data quality flag carried from the adapter to the UI."""

    GOOD = "GOOD"
    INTERPOLATED = "INTERPOLATED"
    ESTIMATED = "ESTIMATED"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AnomalyKind(str, Enum):
    """Explainable anomaly classes produced by the residual engine."""

    OVER_CONSUMPTION = "OVER_CONSUMPTION"
    UNDER_CONSUMPTION = "UNDER_CONSUMPTION"
    OFF_HOURS_LOAD = "OFF_HOURS_LOAD"
    FLATLINE = "FLATLINE"
    SENSOR_DRIFT = "SENSOR_DRIFT"
    MISSING_DATA = "MISSING_DATA"
    PEAK_EXCURSION = "PEAK_EXCURSION"


class DataMode(str, Enum):
    """Where the served values come from, shown in the demo status bar."""

    REAL_DATA = "REAL_DATA"
    SAMPLE_FIXTURE = "SAMPLE_FIXTURE"


class SimulationEngine(str, Enum):
    """Which simulator produced a SIMULATED value. Never mislabel this.

    BOPTEST is only ever reported when a BOPTEST instance actually answered.
    """

    BOPTEST = "BOPTEST"
    ECOTWIN_RC = "ECOTWIN_RC"
    PANDAPOWER = "PANDAPOWER"
    REPLAY = "REPLAY"


ENGINE_LABELS: dict[SimulationEngine, str] = {
    SimulationEngine.BOPTEST: "BOPTEST (IBPSA Project 1)",
    SimulationEngine.ECOTWIN_RC: "EcoTwin RC thermal engine",
    SimulationEngine.PANDAPOWER: "pandapower",
    SimulationEngine.REPLAY: "Simulation replay (cached)",
}
