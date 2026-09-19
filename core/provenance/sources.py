"""Registry of every data/compute source EcoTwin is allowed to cite.

A ``Provenance`` record may only name a source that is registered here. That
prevents a plausible-looking but unverifiable citation from reaching the UI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDescriptor:
    key: str
    name: str
    publisher: str
    url: str | None
    licence: str
    description: str
    is_real_measurement: bool


SOURCES: dict[str, SourceDescriptor] = {
    "power_laws_forecasting": SourceDescriptor(
        key="power_laws_forecasting",
        name="Power Laws: Forecasting Energy Consumption",
        publisher="Schneider Electric / DrivenData (public competition data)",
        url="https://www.drivendata.org/competitions/51/electricity-prediction-machine-learning/",
        licence="Public competition dataset, redistributed by reference only (not vendored)",
        description=(
            "Metered building energy consumption for 267 anonymised sites at 5-30 min "
            "sampling, with per-site floor area, base temperature, weekly day-off "
            "calendar, nearest-station outdoor air temperature and a public-holiday "
            "calendar."
        ),
        is_real_measurement=True,
    ),
    "power_laws_weather": SourceDescriptor(
        key="power_laws_weather",
        name="Power Laws weather observations",
        publisher="Schneider Electric / DrivenData (public competition data)",
        url="https://www.drivendata.org/competitions/51/electricity-prediction-machine-learning/",
        licence="Public competition dataset, redistributed by reference only",
        description=(
            "Outdoor dry-bulb air temperature from weather stations near each site, "
            "with the station distance in km. Multiple stations per site."
        ),
        is_real_measurement=True,
    ),
    "ecotwin_fixture": SourceDescriptor(
        key="ecotwin_fixture",
        name="EcoTwin SAMPLE FIXTURE",
        publisher="EcoTwin AI (synthetic, seeded)",
        url=None,
        licence="Project-internal",
        description=(
            "Deterministic synthetic stand-in used only when no real source file is "
            "present. Every value carries SAMPLE FIXTURE in provenance and the demo "
            "status bar switches to SAMPLE FIXTURE mode."
        ),
        is_real_measurement=False,
    ),
    "lightgbm_forecast": SourceDescriptor(
        key="lightgbm_forecast",
        name="EcoTwin gradient-boosted forecaster",
        publisher="EcoTwin AI (LightGBM)",
        url=None,
        licence="Project-internal",
        description="LightGBM regression on calendar, lag, rolling and weather features.",
        is_real_measurement=False,
    ),
    "residual_anomaly": SourceDescriptor(
        key="residual_anomaly",
        name="EcoTwin residual anomaly engine",
        publisher="EcoTwin AI",
        url=None,
        licence="Project-internal",
        description=(
            "Robust z-score of the forecast residual (actual - expected) against a "
            "rolling median/MAD baseline, with rule-based classification."
        ),
        is_real_measurement=False,
    ),
    "pandapower": SourceDescriptor(
        key="pandapower",
        name="pandapower load flow",
        publisher="Fraunhofer IEE / University of Kassel",
        url="https://www.pandapower.org/",
        licence="BSD-3-Clause",
        description="Balanced AC Newton-Raphson power flow over the EcoTwin LV model.",
        is_real_measurement=False,
    ),
    "boptest": SourceDescriptor(
        key="boptest",
        name="BOPTEST building emulator",
        publisher="IBPSA Project 1",
        url="https://github.com/ibpsa/project1-boptest",
        licence="BSD-3-Clause-like (see upstream)",
        description="Modelica building emulator driven over the BOPTEST REST API.",
        is_real_measurement=False,
    ),
    "ecotwin_rc": SourceDescriptor(
        key="ecotwin_rc",
        name="EcoTwin RC thermal engine",
        publisher="EcoTwin AI",
        url=None,
        licence="Project-internal",
        description=(
            "Lumped-parameter 2R2C zone thermal model with an explicit HVAC plant "
            "model (temperature-dependent COP). Used when a BOPTEST instance is not "
            "reachable. Reported as ECOTWIN_RC, never as BOPTEST."
        ),
        is_real_measurement=False,
    ),
    "cvxpy": SourceDescriptor(
        key="cvxpy",
        name="EcoTwin convex optimiser",
        publisher="EcoTwin AI (CVXPY)",
        url="https://www.cvxpy.org/",
        licence="Apache-2.0",
        description="Convex program over comfort, peak, energy and control-movement terms.",
        is_real_measurement=False,
    ),
    "scenario_engine": SourceDescriptor(
        key="scenario_engine",
        name="EcoTwin scenario engine",
        publisher="EcoTwin AI",
        url=None,
        licence="Project-internal",
        description="Seeded, deterministic disturbance injection for what-if testing.",
        is_real_measurement=False,
    ),
    "demo_cache": SourceDescriptor(
        key="demo_cache",
        name="EcoTwin precomputed demo cache",
        publisher="EcoTwin AI",
        url=None,
        licence="Project-internal",
        description=(
            "Results computed ahead of time by the same code paths and replayed for "
            "hosted-demo latency. The originating engine is preserved in the record."
        ),
        is_real_measurement=False,
    ),
}


def source(key: str) -> SourceDescriptor:
    """Look up a registered source, failing loudly on an unknown citation."""
    try:
        return SOURCES[key]
    except KeyError as exc:  # pragma: no cover - programming error
        raise KeyError(
            f"Unregistered provenance source {key!r}. Add it to core/provenance/sources.py "
            "before citing it."
        ) from exc
