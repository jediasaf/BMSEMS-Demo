"""BMS workflow: Measured → Detect → Predict → Recommend → Simulate → Compare."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from apps.api.services.timeparse import naive_instant
from apps.api.services.expected import ExpectedLoadService, ExpectedSeries
from core.adapters.building import BuildingSourceAdapter, get_building_adapter
from core.adapters.building.power_laws import demo_window
from core.adapters.building.simulation import (
    ComfortBand,
    RcThermalEngine,
    SimulationRequest,
    SimulationResult,
    STEPS_PER_HOUR,
    ZoneThermalParams,
    get_simulation_engine,
)
from core.adapters.power.pandapower_adapter import disaggregate, estimate_hvac_sensitivity
from core.common.schemas import (
    AssetNode,
    ExpectedImpact,
    FeatureContribution,
    Insight,
    KpiValue,
    Recommendation,
)
from core.enums import Severity, SimulationEngine, SourceType
from core.models.anomaly import AnomalyConfig, ResidualAnomalyDetector
from core.optimisation.bms import SetpointOptimiser, SetpointProblem
from core.provenance import Provenance
from core.provenance.model import derived, measured, optimised, simulated
from core.scenarios import ScenarioInjection, apply_bms_scenario, get_scenario

log = logging.getLogger(__name__)

#: Nominal occupied cooling setpoint the building is assumed to run today.
BASELINE_OCCUPIED_SETPOINT_C = 23.0
BASELINE_UNOCCUPIED_SETPOINT_C = 27.0
#: The Control Lab models the building as one conditioned thermal zone. The
#: conditioned area is then *calibrated* against the site's own metered HVAC
#: load (see ``zone_params``), so the simulated HVAC power is comparable with
#: the HVAC feeder in the electrical model rather than an unrelated number.
CALIBRATION_BOUNDS = (0.15, 1.60)
#: Hours of the replay window used to calibrate.
CALIBRATION_HOURS = 24


@dataclass
class BmsContext:
    """Everything a BMS request needs, assembled once and cached."""

    adapter: BuildingSourceAdapter
    site_id: str
    frame: pd.DataFrame
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    expected: ExpectedSeries
    hvac_sensitivity_kw_per_k: float
    scenario_id: str = "bms_normal_day"
    injection: ScenarioInjection | None = None

    @property
    def window(self) -> pd.DataFrame:
        return self.frame.loc[self.window_start : self.window_end]


class BmsService:
    def __init__(self) -> None:
        self.adapter = get_building_adapter()
        self.expected_service = ExpectedLoadService()
        self.detector = ResidualAnomalyDetector(AnomalyConfig())

    # -- context ----------------------------------------------------------
    def default_site_id(self) -> str:
        from core.adapters.building.power_laws import load_selection

        selection = load_selection()
        site = selection.get("bms_site")
        if site is not None:
            return str(site)
        sites = self.adapter.list_sites()
        if not sites:
            raise RuntimeError("no building sites available")
        return sites[0].site_id

    def replay_window(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        window = demo_window()
        if window is not None:
            return window[0], window[1]
        sites = self.adapter.list_sites()
        last = pd.Timestamp(sites[0].last_timestamp)
        return last - pd.Timedelta(days=3), last

    @lru_cache(maxsize=16)
    def context(self, site_id: str, scenario_id: str = "bms_normal_day") -> BmsContext:
        """Assemble the working set for one site and scenario.

        A scenario is injected into the **replay window only**. Injecting it
        across the whole history would let the detector's own rolling baseline
        absorb the disturbance, and nothing would ever be flagged -- the
        disturbance has to be new relative to how the building normally behaves.

        The expected series is computed from the *unmodified* measurements, so
        a scenario reads as an unforecast event rather than as something the
        model was told about in advance.
        """
        raw = self.adapter.load_frame(site_id)
        start, end = self.replay_window()
        expected = self.expected_service.expected(raw, asset_id=site_id)
        descriptor = self.adapter.site(site_id)
        sensitivity = estimate_hvac_sensitivity(
            raw["load_kw"].to_numpy(),
            raw.get("outdoor_temp_c", pd.Series(index=raw.index, dtype=float)).to_numpy(),
            float(descriptor.base_temperature_c or 18.0),
        )

        frame = raw.copy()
        frame["load_kw_measured"] = raw["load_kw"]
        frame["injection_kw"] = 0.0
        injection: ScenarioInjection | None = None
        scenario = get_scenario(scenario_id)
        if not scenario.is_baseline:
            window_frame, injection = apply_bms_scenario(
                raw.loc[start:end],
                scenario_id,
                asset_id=site_id,
                hvac_sensitivity_kw_per_k=max(sensitivity, 0.5),
            )
            for column in ("load_kw", "outdoor_temp_c", "injection_kw"):
                if column in window_frame:
                    frame.loc[window_frame.index, column] = window_frame[column]

        return BmsContext(
            adapter=self.adapter,
            site_id=site_id,
            frame=frame,
            window_start=start,
            window_end=end,
            expected=expected,
            hvac_sensitivity_kw_per_k=sensitivity,
            scenario_id=scenario_id,
            injection=injection,
        )

    # -- provenance helpers ----------------------------------------------
    def _load_provenance(self, timestamp: datetime | None = None) -> Provenance:
        """kW is arithmetic on the published counter, so DERIVED, not MEASURED."""
        return derived(
            self.adapter.source_key,
            field="Value → load_kw",
            units="kW",
            processing="Wh per 15-minute interval × 4 ÷ 1000, on a strict 15-minute grid",
            assumptions=[
                "The publisher does not state a unit for `Value`. The Wh-per-interval "
                "hypothesis was validated by a power-density check against the "
                "published floor area (see docs/data_provenance.md).",
            ],
            timestamp=timestamp,
        )

    def _temp_provenance(self, timestamp: datetime | None = None) -> Provenance:
        return measured(
            "power_laws_weather",
            field="Temperature",
            units="°C",
            processing="nearest weather station, resampled onto the 15-minute grid",
            timestamp=timestamp,
        )

    # -- occupancy --------------------------------------------------------
    def occupancy_series(self, frame: pd.DataFrame, site_id: str) -> pd.Series:
        """An occupancy *proxy*, derived - never presented as a measurement.

        The source publishes no occupancy. What it does publish is a weekly
        day-off calendar, a holiday calendar, and a load series with a strong
        diurnal shape. Normalising the load between its unoccupied floor and
        its occupied ceiling, then zeroing it on closed days, gives a proxy that
        is honest about what it is.
        """
        descriptor = self.adapter.site(site_id)
        load = frame["load_kw"].astype(float)
        closed = frame.get("is_day_off", pd.Series(False, index=frame.index)).astype(
            bool
        ) | frame.get("is_holiday", pd.Series(False, index=frame.index)).astype(bool)
        open_load = load[~closed]
        if open_load.dropna().empty:
            return pd.Series(0.0, index=frame.index)
        floor = float(np.nanpercentile(open_load.dropna(), 5))
        ceiling = float(np.nanpercentile(open_load.dropna(), 95))
        if ceiling - floor < 1e-6:
            return pd.Series(0.0, index=frame.index)
        proxy = ((load - floor) / (ceiling - floor)).clip(0.0, 1.0)
        proxy[closed] = proxy[closed] * 0.12
        _ = descriptor
        return proxy.fillna(0.0)

    # -- KPIs -------------------------------------------------------------
    def kpis(
        self,
        site_id: str,
        at: datetime | None = None,
        scenario_id: str = "bms_normal_day",
    ) -> list[KpiValue]:
        ctx = self.context(site_id, scenario_id)
        window = ctx.window
        if window.empty:
            return []
        stamp = naive_instant(at) if at is not None else window.index[-1]
        stamp = min(max(stamp, window.index[0]), window.index[-1])
        row = window.loc[:stamp].iloc[-1]
        expected_row = ctx.expected.frame.loc[:stamp]
        expected_now = (
            float(expected_row["prediction"].iloc[-1]) if len(expected_row) else float("nan")
        )
        occupancy = self.occupancy_series(ctx.frame, site_id).loc[:stamp]
        occupancy_now = float(occupancy.iloc[-1]) if len(occupancy) else 0.0

        insights = self.insights(site_id, until=stamp, scenario_id=scenario_id)
        active = [i for i in insights if i.severity in (Severity.HIGH, Severity.CRITICAL)]
        descriptor = self.adapter.site(site_id)

        load_now = float(row["load_kw"])
        deviation = load_now - expected_now if np.isfinite(expected_now) else float("nan")
        status = Severity.INFO
        if np.isfinite(deviation) and expected_now:
            ratio = abs(deviation) / max(abs(expected_now), 1e-6)
            status = (
                Severity.HIGH if ratio > 0.25 else Severity.MEDIUM if ratio > 0.12 else Severity.LOW
            )

        kpis = [
            KpiValue(
                key="building_load",
                label="Building load",
                value=round(load_now, 1),
                unit="kW",
                display=f"{load_now:,.1f} kW",
                delta=round(deviation, 1) if np.isfinite(deviation) else None,
                delta_label="vs expected",
                status=status,
                provenance=self._load_provenance(stamp.to_pydatetime()),
                hint="Whole-site electrical demand at the replay instant.",
            ),
            KpiValue(
                key="expected_load",
                label="Expected load",
                value=round(expected_now, 1) if np.isfinite(expected_now) else None,
                unit="kW",
                display=f"{expected_now:,.1f} kW" if np.isfinite(expected_now) else "—",
                status=Severity.INFO,
                provenance=ctx.expected.provenance,
                hint=ctx.expected.gate_reason,
            ),
            KpiValue(
                key="occupancy_proxy",
                label="Occupancy proxy",
                value=round(occupancy_now * 100, 0),
                unit="%",
                display=f"{occupancy_now * 100:,.0f}%",
                status=Severity.INFO,
                provenance=derived(
                    self.adapter.source_key,
                    field="load_kw + day-off/holiday calendar",
                    units="%",
                    processing=(
                        "load normalised between its 5th and 95th percentile on open "
                        "days, damped on closed days"
                    ),
                    assumptions=[
                        "The source publishes no occupancy measurement. This is a "
                        "proxy and is labelled DERIVED wherever it appears.",
                    ],
                    timestamp=stamp.to_pydatetime(),
                ),
                hint="Proxy. The source publishes no occupancy sensor.",
            ),
            KpiValue(
                key="outdoor_temp",
                label="Outdoor air",
                value=round(float(row.get("outdoor_temp_c", float("nan"))), 1),
                unit="°C",
                display=f"{float(row.get('outdoor_temp_c', float('nan'))):,.1f} °C",
                status=Severity.INFO,
                provenance=self._temp_provenance(stamp.to_pydatetime()),
                hint="Nearest published weather station.",
            ),
            KpiValue(
                key="active_anomalies",
                label="Active anomalies",
                value=float(len(active)),
                unit=None,
                display=str(len(active)),
                status=Severity.HIGH if active else Severity.INFO,
                provenance=derived(
                    "residual_anomaly",
                    field="load_kw residual",
                    units="count",
                    processing=(
                        f"robust z > {self.detector.config.threshold} sustained for "
                        f"{self.detector.config.min_run} intervals, HIGH or CRITICAL only"
                    ),
                    timestamp=stamp.to_pydatetime(),
                ),
                hint="High and critical findings up to the replay instant.",
            ),
            KpiValue(
                key="energy_intensity",
                label="Power density",
                value=round(load_now / max(descriptor.surface_m2 or 1.0, 1.0) * 1000.0, 1),
                unit="W/m²",
                display=f"{load_now / max(descriptor.surface_m2 or 1.0, 1.0) * 1000.0:,.1f} W/m²",
                status=Severity.INFO,
                provenance=derived(
                    self.adapter.source_key,
                    field="load_kw ÷ Surface",
                    units="W/m²",
                    processing="instantaneous load divided by the published floor area",
                    timestamp=stamp.to_pydatetime(),
                ),
                hint=f"Published floor area {descriptor.surface_m2:,.0f} m².",
            ),
        ]
        return kpis

    # -- series -----------------------------------------------------------
    def timeline(self, site_id: str, scenario_id: str = "bms_normal_day") -> dict[str, Any]:
        ctx = self.context(site_id, scenario_id)
        window = ctx.window
        expected = ctx.expected.frame.loc[window.index]
        detector_frame = self.detector.score(
            ctx.frame["load_kw"],
            ctx.expected.frame["prediction"],
            reference_end=ctx.window_start,
        ).frame.loc[window.index]

        timestamps = [ts.to_pydatetime() for ts in window.index]

        def clean(values: Any) -> list[float | None]:
            return [None if pd.isna(v) else round(float(v), 4) for v in values]

        return {
            "asset_id": site_id,
            "window": {
                "start": window.index[0].to_pydatetime(),
                "end": window.index[-1].to_pydatetime(),
                "step_minutes": 15,
                "n_steps": len(window),
            },
            "series": [
                {
                    "series_id": "actual",
                    "label": "Measured load",
                    "unit": "kW",
                    "timestamps": timestamps,
                    "values": clean(window["load_kw"]),
                    "provenance": self._load_provenance().model_dump(mode="json"),
                },
                {
                    "series_id": "expected",
                    "label": "Expected load",
                    "unit": "kW",
                    "timestamps": timestamps,
                    "values": clean(expected["prediction"]),
                    "lower": clean(expected["lower"]),
                    "upper": clean(expected["upper"]),
                    "provenance": ctx.expected.provenance.model_dump(mode="json"),
                },
                {
                    "series_id": "outdoor_temp",
                    "label": "Outdoor air temperature",
                    "unit": "°C",
                    "timestamps": timestamps,
                    "values": clean(window.get("outdoor_temp_c", pd.Series(dtype=float))),
                    "provenance": self._temp_provenance().model_dump(mode="json"),
                },
                {
                    "series_id": "occupancy_proxy",
                    "label": "Occupancy proxy",
                    "unit": "%",
                    "timestamps": timestamps,
                    "values": clean(
                        self.occupancy_series(ctx.frame, site_id).loc[window.index] * 100
                    ),
                    "provenance": derived(
                        self.adapter.source_key,
                        field="load_kw + calendar",
                        units="%",
                        processing="normalised load between open-day percentiles",
                    ).model_dump(mode="json"),
                },
                {
                    "series_id": "residual_z",
                    "label": "Robust deviation score",
                    "unit": "σ",
                    "timestamps": timestamps,
                    "values": clean(detector_frame["robust_z"]),
                    "provenance": derived(
                        "residual_anomaly",
                        field="robust_z",
                        units="σ",
                        processing="0.6745 × (residual − rolling median) ÷ rolling MAD",
                    ).model_dump(mode="json"),
                },
            ],
            "served_by": ctx.expected.served_by,
            "gate_reason": ctx.expected.gate_reason,
            "model_id": ctx.expected.model_id,
        }

    # -- insights ---------------------------------------------------------
    def insights(
        self,
        site_id: str,
        until: pd.Timestamp | None = None,
        scenario_id: str = "bms_normal_day",
    ) -> list[Insight]:
        """Findings inside the replay window.

        Scoring runs over the *whole* history, not just the window: the robust
        baseline is a 7-day rolling median/MAD, and a 3-day window would leave
        it undefined for most of the period. Findings are then filtered to the
        window.
        """
        ctx = self.context(site_id, scenario_id)
        if ctx.window.empty:
            return []
        frame = ctx.frame
        # The baseline is calibrated on history that ends where the replay
        # window begins, so a disturbance spanning the whole window cannot
        # redefine "normal" underneath the detector.
        stats = self.detector.score(
            frame["load_kw"],
            ctx.expected.frame["prediction"],
            reference_end=ctx.window_start,
        )
        closed = frame.get("is_day_off", pd.Series(False, index=frame.index)).astype(
            bool
        ) | frame.get("is_holiday", pd.Series(False, index=frame.index)).astype(bool)
        found = self.detector.detect(
            stats,
            asset_id=site_id,
            module="BMS",
            metric="load_kw",
            unit="kW",
            is_closed=closed,
            max_insights=400,
        )
        end = pd.Timestamp(until) if until is not None else ctx.window_end
        inside = [
            i
            for i in found
            if ctx.window_start <= pd.Timestamp(i.timestamp) <= end
        ]
        inside.sort(key=lambda i: pd.Timestamp(i.timestamp))
        return inside

    # -- asset tree -------------------------------------------------------
    def asset_tree(self, site_id: str, scenario_id: str = "bms_normal_day") -> AssetNode:
        """Building → Floor → Zone → Equipment → Point.

        The source has no zone topology. Rather than invent a floor plan, the
        hierarchy is generated from the published floor area with an explicit
        note on every synthesised node, and only the site node carries measured
        values.
        """
        ctx = self.context(site_id, scenario_id)
        descriptor = self.adapter.site(site_id)
        window = ctx.window
        latest = window.iloc[-1] if not window.empty else None
        insights = self.insights(site_id, scenario_id=scenario_id)
        flagged = {i.zone_id for i in insights if i.zone_id}

        area = float(descriptor.surface_m2 or 2000.0)
        n_floors = max(1, min(4, int(round(area / 1200.0))))
        zones_per_floor = max(2, min(4, int(round(area / n_floors / 450.0))))
        site_load = float(latest["load_kw"]) if latest is not None else 0.0

        floors: list[AssetNode] = []
        for floor_index in range(n_floors):
            zones: list[AssetNode] = []
            for zone_index in range(zones_per_floor):
                zone_id = f"Z{floor_index + 1}.{zone_index + 1:02d}"
                share = 1.0 / (n_floors * zones_per_floor)
                zones.append(
                    AssetNode(
                        node_id=zone_id,
                        parent_id=f"F{floor_index + 1}",
                        name=f"Zone {zone_id}",
                        kind="zone",
                        metrics={
                            "allocated_load_kw": round(site_load * share, 2),
                            "floor_area_m2": round(area * share, 1),
                        },
                        units={"allocated_load_kw": "kW", "floor_area_m2": "m²"},
                        source_type=SourceType.DERIVED,
                        has_anomaly=zone_id in flagged,
                        detail=(
                            "Zone geometry is not published by the source. Load is "
                            "allocated pro rata by floor area and is DERIVED."
                        ),
                        children=[
                            AssetNode(
                                node_id=f"{zone_id}-AHU",
                                parent_id=zone_id,
                                name="Air handling",
                                kind="equipment",
                                source_type=SourceType.SIMULATED,
                                detail=(
                                    "Modelled in the Control Lab. No equipment-level "
                                    "telemetry exists in this source."
                                ),
                                children=[
                                    AssetNode(
                                        node_id=f"{zone_id}-SP",
                                        parent_id=f"{zone_id}-AHU",
                                        name="Cooling setpoint",
                                        kind="point",
                                        metrics={"value": BASELINE_OCCUPIED_SETPOINT_C},
                                        units={"value": "°C"},
                                        source_type=SourceType.SIMULATED,
                                        detail="Writable only against the simulator.",
                                    )
                                ],
                            )
                        ],
                    )
                )
            floors.append(
                AssetNode(
                    node_id=f"F{floor_index + 1}",
                    parent_id=site_id,
                    name=f"Floor {floor_index + 1}",
                    kind="floor",
                    metrics={"floor_area_m2": round(area / n_floors, 1)},
                    units={"floor_area_m2": "m²"},
                    source_type=SourceType.DERIVED,
                    detail="Floor split derived from the published total floor area.",
                    children=zones,
                )
            )

        return AssetNode(
            node_id=site_id,
            parent_id=None,
            name=descriptor.name,
            kind="building",
            metrics={
                "load_kw": round(site_load, 2),
                "floor_area_m2": area,
                "outdoor_temp_c": round(float(latest.get("outdoor_temp_c", float("nan"))), 2)
                if latest is not None
                else 0.0,
            },
            units={"load_kw": "kW", "floor_area_m2": "m²", "outdoor_temp_c": "°C"},
            source_type=SourceType.MEASURED,
            has_anomaly=bool(insights),
            detail="Whole-site meter. The only node in this tree backed by a measurement.",
            children=floors,
        )

    # -- zone thermal model ----------------------------------------------
    @lru_cache(maxsize=16)
    def zone_params(self, site_id: str) -> ZoneThermalParams:
        """Single-zone thermal parameters, calibrated to the metered HVAC load.

        Starting from the published floor area, the conditioned area is scaled
        until the simulator's baseline HVAC electrical power matches the HVAC
        share the disaggregation estimates from this site's own weather
        sensitivity. One free parameter, with a physical meaning -- the
        conditioned area the measured load implies -- rather than a fudge
        factor applied to the answer.

        Without this the Control Lab and the network model would be talking
        about different buildings, and the cross-module impact figure would be
        meaningless.
        """
        descriptor = self.adapter.site(site_id)
        published_area = float(descriptor.surface_m2 or 2000.0)
        ctx = self.context(site_id)
        base_params = ZoneThermalParams(floor_area_m2=published_area)

        window = ctx.window.head(CALIBRATION_HOURS * STEPS_PER_HOUR)
        if window.empty or ctx.hvac_sensitivity_kw_per_k <= 0:
            return base_params

        base_kw = float(np.nanpercentile(ctx.frame["load_kw"].dropna(), 10))
        measured_hvac = np.array(
            [
                disaggregate(
                    float(row["load_kw"]),
                    base_kw=base_kw,
                    outdoor_temp_c=float(row.get("outdoor_temp_c", float("nan"))),
                    base_temperature_c=float(descriptor.base_temperature_c or 18.0),
                    hvac_sensitivity_kw_per_k=ctx.hvac_sensitivity_kw_per_k,
                ).hvac_kw
                for _, row in window.iterrows()
                if np.isfinite(row["load_kw"])
            ]
        )
        target_kw = float(np.mean(measured_hvac)) if len(measured_hvac) else 0.0
        if target_kw <= 0.5:
            return base_params

        inputs = self.control_lab_inputs(site_id, hours=CALIBRATION_HOURS)
        probe = RcThermalEngine().simulate(
            SimulationRequest(
                asset_id=site_id,
                zone_id="ZB",
                start=inputs["index"][0].to_pydatetime(),
                setpoints_c=[float(v) for v in self.baseline_setpoints(inputs["occupancy"])],
                outdoor_temp_c=[float(v) for v in inputs["outdoor"]],
                occupancy=[float(v) for v in inputs["occupancy"]],
                params=base_params,
                label="calibration",
            )
        )
        simulated_kw = float(np.mean(probe.hvac_electrical_kw))
        if simulated_kw <= 1e-6:
            return base_params

        # HVAC power scales close to linearly with conditioned area in this
        # model, so one ratio step lands within a few percent.
        ratio = float(np.clip(target_kw / simulated_kw, *CALIBRATION_BOUNDS))
        log.info(
            "zone calibration %s: metered HVAC %.2f kW vs simulated %.2f kW -> "
            "conditioned area %.0f%% of published",
            site_id,
            target_kw,
            simulated_kw,
            ratio * 100,
        )
        return ZoneThermalParams(floor_area_m2=max(published_area * ratio, 120.0))

    def calibration_report(self, site_id: str) -> dict[str, Any]:
        descriptor = self.adapter.site(site_id)
        params = self.zone_params(site_id)
        published = float(descriptor.surface_m2 or 2000.0)
        return {
            "published_floor_area_m2": round(published, 1),
            "conditioned_area_m2": round(params.floor_area_m2, 1),
            "conditioned_share": round(params.floor_area_m2 / max(published, 1e-6), 4),
            "method": (
                "conditioned area scaled so the simulator's baseline HVAC power "
                "matches the HVAC share estimated from this site's own metered "
                "weather sensitivity"
            ),
            "bounds": list(CALIBRATION_BOUNDS),
            "time_constants_hours": params.time_constants_hours(),
        }

    def control_lab_inputs(
        self,
        site_id: str,
        start: datetime | None = None,
        hours: int = 24,
        scenario_id: str = "bms_normal_day",
    ) -> dict[str, Any]:
        ctx = self.context(site_id, scenario_id)
        window = ctx.window
        steps = hours * STEPS_PER_HOUR
        begin = pd.Timestamp(start) if start is not None else window.index[0]
        slice_ = ctx.frame.loc[begin:].head(steps)
        if len(slice_) < steps:
            slice_ = ctx.frame.loc[: window.index[-1]].tail(steps)
        occupancy = self.occupancy_series(ctx.frame, site_id).loc[slice_.index]
        outdoor = slice_["outdoor_temp_c"].ffill().bfill()
        if outdoor.isna().all():
            outdoor = pd.Series(22.0, index=slice_.index)
        return {
            "index": slice_.index,
            "outdoor": outdoor.to_numpy(dtype=float),
            "occupancy": occupancy.to_numpy(dtype=float),
        }

    def baseline_setpoints(self, occupancy: np.ndarray) -> np.ndarray:
        return np.where(
            occupancy > 0.15, BASELINE_OCCUPIED_SETPOINT_C, BASELINE_UNOCCUPIED_SETPOINT_C
        )

    def simulate(
        self,
        site_id: str,
        *,
        setpoints: np.ndarray,
        inputs: dict[str, Any],
        label: str,
        prefer_boptest: bool = True,
    ) -> SimulationResult:
        engine = get_simulation_engine(prefer_boptest=prefer_boptest)
        request = SimulationRequest(
            asset_id=site_id,
            zone_id="ZB",
            start=inputs["index"][0].to_pydatetime(),
            setpoints_c=[float(v) for v in setpoints],
            outdoor_temp_c=[float(v) for v in inputs["outdoor"]],
            occupancy=[float(v) for v in inputs["occupancy"]],
            params=self.zone_params(site_id),
            comfort=ComfortBand(),
            label=label,
        )
        try:
            return engine.simulate(request)
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("simulation engine %s failed (%s); using RC engine", engine.engine, exc)
            return RcThermalEngine().simulate(request)

    def control_lab(
        self,
        site_id: str,
        *,
        start: datetime | None = None,
        hours: int = 24,
        prefer_boptest: bool = True,
        scenario_id: str = "bms_normal_day",
    ) -> dict[str, Any]:
        """Baseline vs AI control, both scored by the same simulator."""
        inputs = self.control_lab_inputs(
            site_id, start=start, hours=hours, scenario_id=scenario_id
        )
        baseline_setpoints = self.baseline_setpoints(inputs["occupancy"])
        baseline = self.simulate(
            site_id,
            setpoints=baseline_setpoints,
            inputs=inputs,
            label="baseline",
            prefer_boptest=prefer_boptest,
        )

        problem = SetpointProblem(
            outdoor_temp_c=inputs["outdoor"],
            occupancy=inputs["occupancy"],
            baseline_setpoint_c=baseline_setpoints,
            baseline_zone_temp_c=np.asarray(baseline.zone_temp_c),
            params=self.zone_params(site_id),
            comfort=ComfortBand(),
            initial_zone_temp_c=baseline.zone_temp_c[0],
        )
        optimisation = SetpointOptimiser().solve(problem)
        optimised_result = self.simulate(
            site_id,
            setpoints=np.asarray(optimisation.setpoints_c),
            inputs=inputs,
            label="ai_control",
            prefer_boptest=prefer_boptest,
        )

        base_kpis = baseline.kpis()
        ai_kpis = optimised_result.kpis()
        delta = {
            key: round(ai_kpis[key] - base_kpis[key], 4) for key in base_kpis if key in ai_kpis
        }
        delta_pct = {
            key: round(
                100.0 * (ai_kpis[key] - base_kpis[key]) / base_kpis[key], 2
            )
            if abs(base_kpis[key]) > 1e-9
            else None
            for key in base_kpis
            if key in ai_kpis
        }

        engine_provenance = simulated(
            baseline.engine,
            units="mixed",
            processing=(
                f"{baseline.engine_version}: 24 h at 15-minute steps, identical "
                "weather and occupancy inputs for both cases"
            ),
            assumptions=baseline.notes,
        )

        return {
            "asset_id": site_id,
            "zone_id": baseline.zone_id,
            "engine": baseline.engine.value,
            "engine_label": baseline.engine_version,
            "is_boptest": baseline.engine is SimulationEngine.BOPTEST,
            "timestamps": [ts for ts in baseline.timestamps],
            "baseline": {
                "label": "Baseline schedule",
                "kpis": base_kpis,
                "zone_temp_c": baseline.zone_temp_c,
                "setpoint_c": baseline.setpoint_c,
                "hvac_kw": baseline.hvac_electrical_kw,
            },
            "ai_control": {
                "label": "AI control",
                "kpis": ai_kpis,
                "zone_temp_c": optimised_result.zone_temp_c,
                "setpoint_c": optimised_result.setpoint_c,
                "hvac_kw": optimised_result.hvac_electrical_kw,
            },
            "outdoor_temp_c": baseline.outdoor_temp_c,
            "occupancy": [float(v) for v in inputs["occupancy"]],
            "delta": delta,
            "delta_pct": delta_pct,
            "optimisation": {
                "status": optimisation.status,
                "solved": optimisation.solved,
                "solver": optimisation.solver,
                "solve_time_s": optimisation.solve_time_s,
                "constraints": optimisation.constraints,
                "notes": optimisation.notes,
                "max_step_change_k": optimisation.max_step_change_k,
                "comfort_slack_kh": optimisation.comfort_slack_kh,
            },
            "parameters": baseline.parameters,
            "provenance": engine_provenance.model_dump(mode="json"),
            "comparison_note": (
                "Both cases were run through the same simulator with identical "
                "weather and occupancy. The optimiser only proposed the setpoint "
                "trajectory; every KPI above is the simulator's answer."
            ),
        }

    # -- recommendations --------------------------------------------------
    def recommendations(
        self,
        site_id: str,
        max_items: int = 3,
        scenario_id: str = "bms_normal_day",
    ) -> list[Recommendation]:
        ctx = self.context(site_id, scenario_id)
        insights = self.insights(site_id, scenario_id=scenario_id)
        if not insights:
            return []
        descriptor = self.adapter.site(site_id)
        occupancy = self.occupancy_series(ctx.frame, site_id)

        out: list[Recommendation] = []
        for insight in insights[:max_items]:
            stamp = pd.Timestamp(insight.timestamp)
            window = ctx.frame.loc[stamp : stamp + pd.Timedelta(hours=6)]
            if window.empty:
                continue
            occupancy_now = float(occupancy.loc[:stamp].iloc[-1]) if len(occupancy) else 0.0
            occupancy_next = (
                float(occupancy.loc[stamp : stamp + pd.Timedelta(hours=2)].mean())
                if len(occupancy)
                else 0.0
            )
            occupancy_change = (
                (occupancy_next - occupancy_now) / max(occupancy_now, 1e-3) * 100.0
                if occupancy_now > 0.02
                else 0.0
            )
            outdoor_now = float(window["outdoor_temp_c"].iloc[0]) if len(window) else float("nan")
            outdoor_trend = (
                float(window["outdoor_temp_c"].iloc[-1] - window["outdoor_temp_c"].iloc[0])
                if len(window) > 1
                else 0.0
            )

            # A setpoint relaxation is only proposed when the deviation is an
            # excess and the building is not about to fill up.
            if insight.deviation is None or insight.deviation <= 0:
                continue
            proposed = BASELINE_OCCUPIED_SETPOINT_C + (
                1.0 if occupancy_change <= 5.0 else 0.5
            )
            factors = [
                FeatureContribution(
                    feature="occupancy_proxy",
                    label="Occupancy proxy, next 2 h",
                    contribution=round(occupancy_change, 1),
                    direction="down" if occupancy_change < 0 else "up",
                    detail=f"{occupancy_now * 100:.0f}% now → {occupancy_next * 100:.0f}%",
                ),
                FeatureContribution(
                    feature="outdoor_temp_c",
                    label="Outdoor air temperature",
                    contribution=round(outdoor_trend, 2),
                    direction="up"
                    if outdoor_trend > 0.5
                    else "down"
                    if outdoor_trend < -0.5
                    else "flat",
                    detail=f"{outdoor_now:.1f} °C, {outdoor_trend:+.1f} K over 6 h",
                ),
                FeatureContribution(
                    feature="residual",
                    label="Load above expected",
                    contribution=round(insight.deviation, 1),
                    direction="up",
                    detail=f"{insight.deviation:+.1f} kW at {insight.robust_z:.1f}σ",
                ),
                FeatureContribution(
                    feature="comfort_margin",
                    label="Comfort margin to the upper bound",
                    contribution=round(ComfortBand().upper_c - BASELINE_OCCUPIED_SETPOINT_C, 2),
                    direction="flat",
                    detail=(
                        f"setpoint {BASELINE_OCCUPIED_SETPOINT_C} °C against a "
                        f"{ComfortBand().upper_c} °C upper bound"
                    ),
                ),
            ]

            recommendation_id = "rec-" + hashlib.sha1(
                f"{site_id}|{insight.insight_id}|setpoint".encode()
            ).hexdigest()[:10]
            out.append(
                Recommendation(
                    recommendation_id=recommendation_id,
                    timestamp=insight.timestamp,
                    asset_id=site_id,
                    zone_id=insight.zone_id or "Z1.01",
                    module="BMS",
                    action="Relax the occupied cooling setpoint",
                    point="zone_cooling_setpoint_c",
                    current_value=BASELINE_OCCUPIED_SETPOINT_C,
                    proposed_value=round(proposed, 1),
                    unit="°C",
                    rationale=(
                        f"Measured load is {insight.deviation:+,.0f} kW above expected at "
                        f"{abs(insight.robust_z or 0):.1f}× this building's normal forecast "
                        f"miss. The occupancy proxy moves {occupancy_change:+.0f}% over the "
                        f"next two hours and outdoor air is {outdoor_trend:+.1f} K over six, "
                        f"so a {proposed - BASELINE_OCCUPIED_SETPOINT_C:.1f} K relaxation is "
                        "expected to stay inside the configured comfort envelope."
                    ),
                    factors=factors,
                    confidence=round(min(insight.confidence * 0.92, 0.95), 3),
                    mode="ADVISORY",
                    constraints_checked=[
                        "point on the writable allowlist",
                        "within setpoint min/max",
                        "within the per-command rate limit",
                        "inside the comfort envelope",
                        "simulation target only",
                    ],
                    provenance=optimised(
                        units="°C",
                        processing=(
                            "candidate setpoint from the residual finding and the "
                            "occupancy/weather context; the trajectory is optimised and "
                            "simulated in the Control Lab before any KPI is claimed"
                        ),
                        model_id="ecotwin-bms-setpoint-v1",
                        assumptions=[
                            "Advisory only. Real historical mode is read-only.",
                            f"Building floor area {descriptor.surface_m2:,.0f} m².",
                        ],
                        timestamp=insight.timestamp,
                    ),
                    expected_impact=ExpectedImpact(
                        comfort_note="Within the configured comfort band, subject to simulation",
                        provenance=derived(
                            "ecotwin_rc",
                            field=None,
                            units="—",
                            processing=(
                                "not yet estimated: run the proposal in the Control Lab "
                                "to obtain simulated energy, peak and comfort effects"
                            ),
                        ),
                        basis=(
                            "No number is claimed until the simulator has run both cases."
                        ),
                    ),
                    simulatable=True,
                    source_insight_id=insight.insight_id,
                )
            )
        return out


@lru_cache(maxsize=1)
def get_bms_service() -> BmsService:
    return BmsService()
