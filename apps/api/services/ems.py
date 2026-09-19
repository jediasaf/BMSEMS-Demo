"""EMS workflow: Measured → Forecast → Detect Risk → Optimise → Simulate → Resolve."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from apps.api.services.timeparse import naive_instant
from apps.api.services.expected import ExpectedLoadService, ExpectedSeries
from core.adapters.building.power_laws import demo_window
from core.adapters.power import PowerSourceAdapter, get_power_adapter
from core.adapters.power.facility import ASSUMED_POWER_FACTOR
from core.adapters.power.pandapower_adapter import (
    LOADING_CRITICAL_PCT,
    LOADING_WARN_PCT,
    NetworkState,
    PandapowerNetwork,
    disaggregate,
    estimate_hvac_sensitivity,
)
from core.common.schemas import Insight, KpiValue
from core.enums import Severity, SimulationEngine
from core.models.anomaly import AnomalyConfig, ResidualAnomalyDetector
from core.optimisation.ems import FlexibleResource, LoadShiftProblem, PeakOptimiser
from core.provenance import Provenance
from core.provenance.model import derived, injected, optimised, simulated
from core.scenarios import ScenarioInjection, apply_ems_scenario, get_scenario

log = logging.getLogger(__name__)

STEPS_PER_HOUR = 4
#: Share of a facility's HVAC feeder load that can be given up temporarily.
HVAC_FLEXIBILITY_SHARE = 0.30
#: How long HVAC flexibility can be held before comfort is at risk, in hours.
HVAC_FLEXIBILITY_HOURS = 1.5
#: Spare EV charger capacity available for catch-up, as a share of its rating.
EV_CATCHUP_SHARE = 0.55
#: Horizon the risk assessment and optimisation look over.
#:
#: Twelve hours, not eight: deferred load has to land somewhere. A horizon that
#: ends before the flexible resource does leaves the optimiser with nowhere to
#: recover the energy it curtails, and the honest answer becomes "infeasible"
#: for a problem that is perfectly feasible over a realistic operating window.
RISK_HORIZON_STEPS = 12 * STEPS_PER_HOUR


@dataclass
class EmsContext:
    adapter: PowerSourceAdapter
    facility_id: str
    frame: pd.DataFrame
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    expected: ExpectedSeries
    hvac_sensitivity_kw_per_k: float
    base_kw: float
    transformer_kva: float
    cap_kw: float
    scenario_id: str
    injection: ScenarioInjection | None

    @property
    def window(self) -> pd.DataFrame:
        return self.frame.loc[self.window_start : self.window_end]


class EmsService:
    def __init__(self) -> None:
        self.adapter = get_power_adapter()
        self.expected_service = ExpectedLoadService()
        self.detector = ResidualAnomalyDetector(AnomalyConfig())
        self._networks: dict[str, PandapowerNetwork] = {}
        self._caps: dict[str, float] = {}

    # -- context ----------------------------------------------------------
    def facilities(self) -> list[Any]:
        return self.adapter.list_facilities()

    def default_facility_id(self) -> str:
        """Default to the BMS lead building when it is in the portfolio.

        The cross-module workflow -- power risk, then building analysis, then a
        control simulation, then the power impact -- only means anything if both
        modules are looking at the same asset.
        """
        facilities = self.facilities()
        if not facilities:
            raise RuntimeError("no facilities available")
        from core.adapters.building.power_laws import load_selection

        bms_site = load_selection().get("bms_site")
        if bms_site is not None:
            for facility in facilities:
                if facility.facility_id == str(bms_site):
                    return facility.facility_id
        # Otherwise the facility whose peak sits closest under its rating: that
        # is where a risk story is real rather than manufactured.
        ranked = sorted(
            facilities,
            key=lambda f: abs(
                f.peak_kw / max(f.transformer_kva * ASSUMED_POWER_FACTOR, 1e-6) - 0.75
            ),
        )
        return ranked[0].facility_id

    def default_instant(self, facility_id: str, scenario_id: str) -> pd.Timestamp:
        """Where the replay starts.

        Mid-morning on the second day, so the forward risk horizon covers an
        afternoon peak rather than a quiet midnight. Anchored to the window
        rather than to wall-clock time, so the demo is reproducible.
        """
        ctx = self.context(facility_id, scenario_id)
        target = ctx.window_start + pd.Timedelta(hours=32)
        window = ctx.window
        if window.empty:
            return ctx.window_start
        if target > window.index[-1]:
            target = window.index[max(len(window) // 2, 0)]
        return min(max(target, window.index[0]), window.index[-1])

    def replay_window(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        window = demo_window()
        if window is not None:
            return window[0], window[1]
        facility = self.facilities()[0]
        last = pd.Timestamp(facility.last_timestamp)
        return last - pd.Timedelta(days=3), last

    def network(self, facility_id: str) -> PandapowerNetwork:
        if facility_id not in self._networks:
            descriptor = self.adapter.facility(facility_id)
            network = PandapowerNetwork(facility_id, descriptor.transformer_kva)
            network.build()
            self._networks[facility_id] = network
        return self._networks[facility_id]

    @lru_cache(maxsize=32)
    def context(
        self, facility_id: str, scenario_id: str = "ems_normal_day"
    ) -> EmsContext:
        raw = self.adapter.load_frame(facility_id)
        start, end = self.replay_window()
        expected = self.expected_service.expected(raw, asset_id=facility_id)
        descriptor = self.adapter.facility(facility_id)
        sensitivity = estimate_hvac_sensitivity(
            raw["load_kw"].to_numpy(),
            raw.get("outdoor_temp_c", pd.Series(index=raw.index, dtype=float)).to_numpy(),
            18.0,
        )
        base_kw = float(np.nanpercentile(raw["load_kw"].dropna(), 10))

        frame = raw.copy()
        frame["injection_kw"] = 0.0
        frame["flexible_kw"] = 0.0
        injection_summary: ScenarioInjection | None = None
        if not get_scenario(scenario_id).is_baseline:
            window_frame, injection_summary = apply_ems_scenario(
                raw.loc[start:end], scenario_id, asset_id=facility_id
            )
            for column in ("injection_kw", "flexible_kw"):
                frame.loc[window_frame.index, column] = window_frame[column]

        return EmsContext(
            adapter=self.adapter,
            facility_id=facility_id,
            frame=frame,
            window_start=start,
            window_end=end,
            expected=expected,
            hvac_sensitivity_kw_per_k=sensitivity,
            base_kw=base_kw,
            transformer_kva=descriptor.transformer_kva,
            cap_kw=self._cap_kw(facility_id, raw, base_kw, sensitivity),
            scenario_id=scenario_id,
            injection=injection_summary,
        )

    def _cap_kw(
        self,
        facility_id: str,
        frame: pd.DataFrame,
        base_kw: float,
        sensitivity: float,
    ) -> float:
        """Site demand at exactly 100% transformer loading, from the load flow."""
        if facility_id in self._caps:
            return self._caps[facility_id]
        reference_row = frame.dropna(subset=["load_kw"]).iloc[len(frame) // 2]
        reference = disaggregate(
            float(reference_row["load_kw"]),
            base_kw=base_kw,
            outdoor_temp_c=float(reference_row.get("outdoor_temp_c", float("nan"))),
            base_temperature_c=18.0,
            hvac_sensitivity_kw_per_k=sensitivity,
        )
        cap = self.network(facility_id).capacity_kw(reference)
        self._caps[facility_id] = cap
        return cap

    # -- provenance -------------------------------------------------------
    def _load_provenance(self, timestamp: datetime | None = None) -> Provenance:
        return derived(
            self.adapter.source_key,
            field="Value → load_kw",
            units="kW",
            processing="Wh per 15-minute interval × 4 ÷ 1000, on a strict 15-minute grid",
            assumptions=[
                "The publisher does not state a unit for `Value`; the hypothesis was "
                "validated by a power-density check (see docs/data_provenance.md).",
            ],
            timestamp=timestamp,
        )

    def _network_provenance(self, timestamp: datetime | None = None) -> Provenance:
        return simulated(
            SimulationEngine.PANDAPOWER,
            units="%",
            processing="balanced AC Newton-Raphson load flow over the EcoTwin LV model",
            assumptions=[
                "Transformer rating is DERIVED from the observed peak; the source "
                "publishes no nameplate data.",
                f"Displacement power factor assumed {ASSUMED_POWER_FACTOR}.",
                "Feeder split is a documented disaggregation, not measured sub-metering.",
            ],
            timestamp=timestamp,
        )

    # -- network ----------------------------------------------------------
    def split_at(self, ctx: EmsContext, stamp: pd.Timestamp) -> Any:
        row = ctx.frame.loc[:stamp].iloc[-1]
        return disaggregate(
            float(row["load_kw"]) if np.isfinite(row["load_kw"]) else ctx.base_kw,
            base_kw=ctx.base_kw,
            outdoor_temp_c=float(row.get("outdoor_temp_c", float("nan"))),
            base_temperature_c=18.0,
            hvac_sensitivity_kw_per_k=ctx.hvac_sensitivity_kw_per_k,
            flexible_kw=float(row.get("flexible_kw", 0.0)),
        )

    def network_state(
        self,
        facility_id: str,
        at: datetime | None = None,
        scenario_id: str = "ems_normal_day",
    ) -> tuple[NetworkState, Any, pd.Timestamp]:
        ctx = self.context(facility_id, scenario_id)
        window = ctx.window
        stamp = (
            naive_instant(at)
            if at is not None
            else self.default_instant(facility_id, scenario_id)
        )
        stamp = min(max(stamp, window.index[0]), window.index[-1])
        split = self.split_at(ctx, stamp)
        return self.network(facility_id).solve(split), split, stamp

    # -- risk -------------------------------------------------------------
    def peak_risk(
        self,
        facility_id: str,
        at: datetime | None = None,
        scenario_id: str = "ems_normal_day",
    ) -> dict[str, Any]:
        """Forecast transformer loading over the next hours and grade the risk."""
        ctx = self.context(facility_id, scenario_id)
        window = ctx.window
        stamp = (
            naive_instant(at)
            if at is not None
            else self.default_instant(facility_id, scenario_id)
        )
        stamp = min(max(stamp, window.index[0]), window.index[-1])

        # Look forward over the risk horizon; near the end of the replay window
        # fall back to the trailing horizon so the view is never a single point.
        horizon_index = window.loc[stamp:].head(RISK_HORIZON_STEPS).index
        if len(horizon_index) < RISK_HORIZON_STEPS:
            horizon_index = window.tail(RISK_HORIZON_STEPS).index
        expected = ctx.expected.frame.loc[horizon_index, "prediction"]
        measured = ctx.frame.loc[horizon_index, "load_kw"]
        # Prefer the forecast; fall back to the measurement where the model has
        # no answer, so the risk view never has holes.
        forecast = expected.fillna(measured).ffill().bfill()
        injected_kw = ctx.frame.loc[horizon_index, "injection_kw"]
        total = forecast + injected_kw.fillna(0.0)

        loading_pct = total / max(ctx.cap_kw, 1e-6) * 100.0
        peak_pos = int(np.nanargmax(total.to_numpy()))
        peak_time = horizon_index[peak_pos]
        peak_kw = float(total.iloc[peak_pos])
        peak_loading = float(loading_pct.iloc[peak_pos])

        if peak_loading >= LOADING_CRITICAL_PCT:
            level, severity = "OVERLOAD RISK", Severity.CRITICAL
        elif peak_loading >= LOADING_WARN_PCT:
            level, severity = "HIGH", Severity.HIGH
        elif peak_loading >= 70.0:
            level, severity = "MODERATE", Severity.MEDIUM
        else:
            level, severity = "LOW", Severity.LOW

        split_at_peak = disaggregate(
            float(forecast.iloc[peak_pos]),
            base_kw=ctx.base_kw,
            outdoor_temp_c=float(
                ctx.frame.loc[peak_time].get("outdoor_temp_c", float("nan"))
            ),
            base_temperature_c=18.0,
            hvac_sensitivity_kw_per_k=ctx.hvac_sensitivity_kw_per_k,
            flexible_kw=float(injected_kw.iloc[peak_pos]),
        )
        contributors = sorted(
            (
                {
                    "feeder": feeder,
                    "kw": round(kw, 2),
                    "share_pct": round(100.0 * kw / max(split_at_peak.total(), 1e-6), 1),
                    "flexible": feeder in ("F1_HVAC", "F4_FLEXIBLE"),
                }
                for feeder, kw in split_at_peak.as_dict().items()
            ),
            key=lambda c: c["kw"],
            reverse=True,
        )

        return {
            "facility_id": facility_id,
            "assessed_at": stamp.to_pydatetime(),
            "horizon_minutes": len(horizon_index) * 15,
            "transformer_id": "TR-01",
            "transformer_kva": ctx.transformer_kva,
            "cap_kw": round(ctx.cap_kw, 2),
            "predicted_peak_kw": round(peak_kw, 2),
            "predicted_peak_at": peak_time.to_pydatetime(),
            "predicted_peak_loading_pct": round(peak_loading, 2),
            "risk_level": level,
            "severity": severity.value,
            "timestamps": [ts.to_pydatetime() for ts in horizon_index],
            "forecast_kw": [round(float(v), 3) for v in forecast],
            "injected_kw": [round(float(v), 3) for v in injected_kw.fillna(0.0)],
            "loading_pct": [round(float(v), 3) for v in loading_pct],
            "contributors": contributors,
            "largest_flexible_contributor": next(
                (c["feeder"] for c in contributors if c["flexible"]), None
            ),
            "provenance": {
                "forecast": ctx.expected.provenance.model_dump(mode="json"),
                "loading": self._network_provenance(peak_time.to_pydatetime()).model_dump(
                    mode="json"
                ),
            },
            "served_by": ctx.expected.served_by,
            "gate_reason": ctx.expected.gate_reason,
        }

    # -- optimisation -----------------------------------------------------
    def optimise(
        self,
        facility_id: str,
        at: datetime | None = None,
        scenario_id: str = "ems_ev_surge",
    ) -> dict[str, Any]:
        """Resolve the risk, then prove it with a second load flow."""
        ctx = self.context(facility_id, scenario_id)
        risk = self.peak_risk(facility_id, at=at, scenario_id=scenario_id)
        index = pd.DatetimeIndex(risk["timestamps"])
        forecast = np.asarray(risk["forecast_kw"], dtype=float)
        injected_kw = np.asarray(risk["injected_kw"], dtype=float)

        hvac_available = np.array(
            [
                disaggregate(
                    float(f),
                    base_kw=ctx.base_kw,
                    outdoor_temp_c=float(
                        ctx.frame.loc[ts].get("outdoor_temp_c", float("nan"))
                    ),
                    base_temperature_c=18.0,
                    hvac_sensitivity_kw_per_k=ctx.hvac_sensitivity_kw_per_k,
                ).hvac_kw
                * HVAC_FLEXIBILITY_SHARE
                for f, ts in zip(forecast, index, strict=True)
            ]
        )
        ev_available = injected_kw.copy()
        # Catch-up capacity exists only once a session has started and only
        # while it is not already drawing full power. Offering headroom before
        # the first arrival would let the optimiser charge vehicles that are
        # not there.
        session = np.flatnonzero(injected_kw > 0.1)
        ev_headroom = np.zeros_like(injected_kw)
        if session.size:
            first = int(session[0])
            ev_headroom[first:] = np.where(
                injected_kw[first:] > 0.1,
                0.0,
                float(np.nanmax(injected_kw)) * EV_CATCHUP_SHARE,
            )

        hvac = FlexibleResource(
            resource_id="F1_HVAC",
            label="HVAC flexible demand",
            kind="hvac",
            available_kw=hvac_available,
            energy_budget_kwh=float(np.nanmax(hvac_available)) * HVAC_FLEXIBILITY_HOURS,
            ramp_kw=max(float(np.nanmax(hvac_available)) * 0.4, 1.0),
            notes=[
                f"{HVAC_FLEXIBILITY_SHARE:.0%} of the modelled HVAC feeder load, held "
                f"for at most {HVAC_FLEXIBILITY_HOURS} equivalent hours.",
            ],
        )
        ev = FlexibleResource(
            resource_id="F4_FLEXIBLE",
            label="EV / flexible charging",
            kind="ev",
            available_kw=ev_available,
            headroom_kw=ev_headroom,
            shiftable=True,
            notes=["Energy is deferred, never shed: the constraint is an equality."],
        )

        problem = LoadShiftProblem(
            facility_id=facility_id,
            forecast_kw=forecast,
            injected_kw=injected_kw,
            cap_kw=ctx.cap_kw,
            hvac=hvac,
            ev=ev,
        )
        result = PeakOptimiser().solve(problem)

        # Prove it: run the network again at the worst instant, before and after.
        worst_pos = int(np.argmax(np.asarray(result.baseline_kw)))
        worst_time = index[worst_pos]
        network = self.network(facility_id)
        outdoor = float(ctx.frame.loc[worst_time].get("outdoor_temp_c", float("nan")))

        before_split = disaggregate(
            float(forecast[worst_pos]),
            base_kw=ctx.base_kw,
            outdoor_temp_c=outdoor,
            base_temperature_c=18.0,
            hvac_sensitivity_kw_per_k=ctx.hvac_sensitivity_kw_per_k,
            flexible_kw=float(injected_kw[worst_pos]),
        )
        before = network.solve(before_split)

        after_split = disaggregate(
            float(forecast[worst_pos]) - result.hvac_reduction_kw[worst_pos],
            base_kw=ctx.base_kw,
            outdoor_temp_c=outdoor,
            base_temperature_c=18.0,
            hvac_sensitivity_kw_per_k=ctx.hvac_sensitivity_kw_per_k,
            flexible_kw=max(
                float(injected_kw[worst_pos])
                - result.ev_reduction_kw[worst_pos]
                + result.ev_recovery_kw[worst_pos],
                0.0,
            ),
        )
        after = network.solve(after_split)

        return {
            "facility_id": facility_id,
            "scenario_id": scenario_id,
            "risk": risk,
            "timestamps": [ts.to_pydatetime() for ts in index],
            "baseline_kw": result.baseline_kw,
            "optimised_kw": result.optimised_kw,
            "hvac_reduction_kw": result.hvac_reduction_kw,
            "ev_reduction_kw": result.ev_reduction_kw,
            "ev_recovery_kw": result.ev_recovery_kw,
            "summary": {
                "baseline_peak_kw": result.baseline_peak_kw,
                "optimised_peak_kw": result.optimised_peak_kw,
                "peak_reduction_kw": result.peak_reduction_kw,
                "hvac_energy_kwh": result.hvac_energy_kwh,
                "ev_energy_shifted_kwh": result.ev_energy_shifted_kwh,
                "residual_overload_kw": result.residual_overload_kw,
                "feasible_within_cap": result.feasible_within_cap,
                "cap_kw": result.cap_kw,
                "target_kw": result.target_kw,
                "status": result.status,
                "solver": result.solver,
                "solve_time_s": result.solve_time_s,
            },
            "constraints": result.constraints,
            "notes": result.notes,
            "worst_instant": worst_time.to_pydatetime(),
            "network_before": {
                "transformer_loading_pct": before.transformer_loading_pct,
                "lv_bus_voltage_pu": before.lv_bus_voltage_pu,
                "min_bus_voltage_pu": before.min_bus_voltage_pu,
                "losses_kw": before.losses_kw,
                "status": before.status,
                "violations": before.violations,
                "feeder_load_kw": before.feeder_load_kw,
                "feeder_loading_pct": before.feeder_loading_pct,
                "total_load_kw": before.total_load_kw,
            },
            "network_after": {
                "transformer_loading_pct": after.transformer_loading_pct,
                "lv_bus_voltage_pu": after.lv_bus_voltage_pu,
                "min_bus_voltage_pu": after.min_bus_voltage_pu,
                "losses_kw": after.losses_kw,
                "status": after.status,
                "violations": after.violations,
                "feeder_load_kw": after.feeder_load_kw,
                "feeder_loading_pct": after.feeder_loading_pct,
                "total_load_kw": after.total_load_kw,
            },
            "provenance": {
                "optimisation": optimised(
                    units="kW",
                    processing=(
                        "linear program over HVAC reduction and EV shifting against "
                        "the transformer constraint"
                    ),
                    model_id="ecotwin-ems-peak-v1",
                    assumptions=[
                        f"HVAC flexibility capped at {HVAC_FLEXIBILITY_SHARE:.0%} of the "
                        "modelled HVAC feeder load.",
                        "EV energy is conserved over the horizon.",
                    ],
                ).model_dump(mode="json"),
                "network": self._network_provenance(
                    worst_time.to_pydatetime()
                ).model_dump(mode="json"),
                "injection": (
                    injected(
                        units="kW",
                        processing=ctx.injection.description,
                        scenario_id=ctx.scenario_id,
                    ).model_dump(mode="json")
                    if ctx.injection
                    else None
                ),
            },
            "verification_note": (
                "The transformer figures above are two separate pandapower solves at "
                "the worst instant, before and after the proposed dispatch. They are "
                "not the optimiser's own estimate."
            ),
        }

    # -- portfolio --------------------------------------------------------
    def portfolio(
        self, at: datetime | None = None, scenario_id: str = "ems_normal_day"
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        total_demand = 0.0
        total_expected = 0.0
        total_predicted_peak = 0.0
        above_baseline = 0
        anomalies = 0
        reduction_opportunity = 0.0

        for descriptor in self.facilities():
            facility_id = descriptor.facility_id
            try:
                ctx = self.context(facility_id, scenario_id)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("facility %s unavailable: %s", facility_id, exc)
                continue
            window = ctx.window
            if window.empty:
                continue
            stamp = (
                naive_instant(at)
                if at is not None
                else self.default_instant(facility_id, scenario_id)
            )
            stamp = min(max(stamp, window.index[0]), window.index[-1])
            row = window.loc[:stamp].iloc[-1]
            demand = float(row["load_kw"]) + float(row.get("injection_kw", 0.0))
            expected_series = ctx.expected.frame.loc[:stamp, "prediction"].dropna()
            expected = float(expected_series.iloc[-1]) if len(expected_series) else float("nan")

            risk = self.peak_risk(facility_id, at=stamp, scenario_id=scenario_id)
            insights = self.insights(facility_id, until=stamp, scenario_id=scenario_id)
            active = [i for i in insights if i.severity in (Severity.HIGH, Severity.CRITICAL)]

            deviation = demand - expected if np.isfinite(expected) else float("nan")
            headroom = ctx.cap_kw - risk["predicted_peak_kw"]
            if headroom < 0:
                reduction_opportunity += -headroom

            total_demand += demand
            if np.isfinite(expected):
                total_expected += expected
            total_predicted_peak += risk["predicted_peak_kw"]
            if np.isfinite(deviation) and deviation > 0.1 * max(expected, 1e-6):
                above_baseline += 1
            anomalies += len(active)

            rows.append(
                {
                    "facility_id": facility_id,
                    "name": descriptor.name,
                    "surface_m2": descriptor.surface_m2,
                    "transformer_kva": descriptor.transformer_kva,
                    "current_demand_kw": round(demand, 2),
                    "expected_demand_kw": round(expected, 2) if np.isfinite(expected) else None,
                    "deviation_kw": round(deviation, 2) if np.isfinite(deviation) else None,
                    "deviation_pct": round(100.0 * deviation / expected, 1)
                    if np.isfinite(deviation) and abs(expected) > 1e-6
                    else None,
                    "predicted_peak_kw": risk["predicted_peak_kw"],
                    "predicted_peak_at": risk["predicted_peak_at"],
                    "predicted_peak_loading_pct": risk["predicted_peak_loading_pct"],
                    "risk_level": risk["risk_level"],
                    "severity": risk["severity"],
                    "active_anomalies": len(active),
                    "served_by": ctx.expected.served_by,
                    "model_note": ctx.expected.gate_reason,
                }
            )

        kpis = [
            KpiValue(
                key="total_demand",
                label="Portfolio demand",
                value=round(total_demand, 1),
                unit="kW",
                display=f"{total_demand:,.0f} kW",
                status=Severity.INFO,
                provenance=self._load_provenance(),
                hint=f"Sum across {len(rows)} facilities at the replay instant.",
            ),
            KpiValue(
                key="predicted_peak",
                label="Predicted peak",
                value=round(total_predicted_peak, 1),
                unit="kW",
                display=f"{total_predicted_peak:,.0f} kW",
                status=Severity.INFO,
                provenance=derived(
                    "lightgbm_forecast",
                    field="load_kw",
                    units="kW",
                    processing="sum of per-facility forecast peaks over the next 8 hours",
                ),
                hint="Non-coincident sum: facilities do not necessarily peak together.",
            ),
            KpiValue(
                key="sites_above_baseline",
                label="Sites above expected",
                value=float(above_baseline),
                unit=None,
                display=f"{above_baseline} / {len(rows)}",
                status=Severity.MEDIUM if above_baseline else Severity.INFO,
                provenance=derived(
                    "residual_anomaly",
                    field="load_kw − expected",
                    units="count",
                    processing="facilities more than 10% above their expected demand",
                ),
            ),
            KpiValue(
                key="active_anomalies",
                label="Active anomalies",
                value=float(anomalies),
                unit=None,
                display=str(anomalies),
                status=Severity.HIGH if anomalies else Severity.INFO,
                provenance=derived(
                    "residual_anomaly",
                    field="load_kw residual",
                    units="count",
                    processing="HIGH and CRITICAL residual findings across the portfolio",
                ),
            ),
            KpiValue(
                key="peak_reduction_opportunity",
                label="Peak reduction needed",
                value=round(reduction_opportunity, 1),
                unit="kW",
                display=f"{reduction_opportunity:,.0f} kW",
                status=Severity.HIGH if reduction_opportunity > 0 else Severity.INFO,
                provenance=derived(
                    "pandapower",
                    field="predicted peak − transformer capacity",
                    units="kW",
                    processing="summed shortfall where a forecast peak exceeds its cap",
                    assumptions=["Transformer ratings are DERIVED from observed peaks."],
                ),
                hint="How much load must move for every transformer to stay inside rating.",
            ),
        ]

        return {
            "generated_at": datetime.now(timezone.utc),
            "scenario_id": scenario_id,
            "kpis": kpis,
            "facilities": rows,
        }

    # -- insights ---------------------------------------------------------
    def insights(
        self,
        facility_id: str,
        until: pd.Timestamp | None = None,
        scenario_id: str = "ems_normal_day",
    ) -> list[Insight]:
        ctx = self.context(facility_id, scenario_id)
        if ctx.window.empty:
            return []
        total = ctx.frame["load_kw"] + ctx.frame["injection_kw"].fillna(0.0)
        stats = self.detector.score(
            total, ctx.expected.frame["prediction"], reference_end=ctx.window_start
        )
        found = self.detector.detect(
            stats,
            asset_id=facility_id,
            module="EMS",
            metric="load_kw",
            unit="kW",
            max_insights=200,
        )
        end = pd.Timestamp(until) if until is not None else ctx.window_end
        inside = [i for i in found if ctx.window_start <= pd.Timestamp(i.timestamp) <= end]
        inside.sort(key=lambda i: pd.Timestamp(i.timestamp))
        return inside


@lru_cache(maxsize=1)
def get_ems_service() -> EmsService:
    return EmsService()
