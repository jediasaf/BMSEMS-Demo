"""The BMS ↔ EMS workflow.

    Power risk  →  Building analysis  →  AI recommendation
                →  Control simulation  →  Power impact

This is the piece that makes the two modules one platform rather than two
dashboards. The chain is closed with real computation at every link:

1. EMS finds a transformer risk and names the flexible contributors.
2. BMS is asked what an HVAC action on that asset would actually do -- and
   answers by running the *simulator*, baseline and proposal, not by applying a
   rule of thumb.
3. The simulated HVAC reduction in kW is handed back to EMS.
4. EMS re-solves the load flow with that reduction applied, and reports the new
   transformer state.

The number that reaches the operator at step 4 is therefore the output of a
thermal simulation feeding an electrical simulation. Nothing in the chain is a
percentage someone typed in.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from apps.api.services.bms import get_bms_service
from apps.api.services.ems import get_ems_service
from core.adapters.power.pandapower_adapter import disaggregate

log = logging.getLogger(__name__)


class CrossModuleService:
    def __init__(self) -> None:
        self.bms = get_bms_service()
        self.ems = get_ems_service()

    def link(self, facility_id: str, scenario_id: str = "ems_ev_surge") -> dict[str, Any]:
        """Step 1→2: the power risk, and the building it points at."""
        risk = self.ems.peak_risk(facility_id, scenario_id=scenario_id)
        building_available = any(
            site.site_id == facility_id for site in self.bms.adapter.list_sites()
        )
        hvac = next((c for c in risk["contributors"] if c["feeder"] == "F1_HVAC"), None)
        return {
            "facility_id": facility_id,
            "risk_level": risk["risk_level"],
            "predicted_peak_kw": risk["predicted_peak_kw"],
            "predicted_peak_loading_pct": risk["predicted_peak_loading_pct"],
            "predicted_peak_at": risk["predicted_peak_at"],
            "transformer_id": risk["transformer_id"],
            "contributors": risk["contributors"],
            "hvac_contribution_kw": hvac["kw"] if hvac else 0.0,
            "hvac_share_pct": hvac["share_pct"] if hvac else 0.0,
            "building_analysis_available": building_available,
            "bms_site_id": facility_id if building_available else None,
            "call_to_action": (
                "Open the BMS analysis for this asset and test an HVAC action against "
                "the building simulator."
            ),
        }

    def simulate_hvac_action(
        self,
        facility_id: str,
        *,
        scenario_id: str = "ems_ev_surge",
        hours: int = 24,
        prefer_boptest: bool = True,
    ) -> dict[str, Any]:
        """Steps 2→4: simulate the building action and price it in the network."""
        link = self.link(facility_id, scenario_id=scenario_id)
        if not link["building_analysis_available"]:
            return {
                "available": False,
                "reason": (
                    f"No building data adapter serves asset {facility_id}; the "
                    "cross-module workflow needs both a meter and a building model."
                ),
                "link": link,
            }

        control = self.bms.control_lab(facility_id, hours=hours, prefer_boptest=prefer_boptest)
        baseline_hvac = np.asarray(control["baseline"]["hvac_kw"], dtype=float)
        ai_hvac = np.asarray(control["ai_control"]["hvac_kw"], dtype=float)
        timestamps = pd.DatetimeIndex(control["timestamps"])
        reduction = baseline_hvac - ai_hvac

        peak_time = pd.Timestamp(link["predicted_peak_at"])
        # Line the simulated day up with the risk window by time of day: the
        # Control Lab runs a 24 h case, the risk horizon is a few hours inside it.
        minutes = timestamps.hour * 60 + timestamps.minute
        target_minutes = peak_time.hour * 60 + peak_time.minute
        position = int(np.argmin(np.abs(minutes - target_minutes)))
        reduction_at_peak = float(reduction[position])

        ctx = self.ems.context(facility_id, scenario_id)
        row = ctx.frame.loc[peak_time]
        outdoor = float(row.get("outdoor_temp_c", float("nan")))
        expected_series = ctx.expected.frame.loc[:peak_time, "prediction"].dropna()
        site_kw = float(expected_series.iloc[-1]) if len(expected_series) else float(row["load_kw"])
        flexible_kw = float(row.get("injection_kw", 0.0))
        network = self.ems.network(facility_id)

        before_split = disaggregate(
            site_kw,
            base_kw=ctx.base_kw,
            outdoor_temp_c=outdoor,
            base_temperature_c=18.0,
            hvac_sensitivity_kw_per_k=ctx.hvac_sensitivity_kw_per_k,
            flexible_kw=flexible_kw,
        )
        before = network.solve(before_split)

        # Apply the simulated reduction to the HVAC feeder only, never below zero.
        applied = float(np.clip(reduction_at_peak, 0.0, before_split.hvac_kw))
        after_split = disaggregate(
            site_kw - applied,
            base_kw=ctx.base_kw,
            outdoor_temp_c=outdoor,
            base_temperature_c=18.0,
            hvac_sensitivity_kw_per_k=ctx.hvac_sensitivity_kw_per_k,
            flexible_kw=flexible_kw,
        )
        after = network.solve(after_split)

        return {
            "available": True,
            "link": link,
            "facility_id": facility_id,
            "scenario_id": scenario_id,
            "building": {
                "engine": control["engine"],
                "engine_label": control["engine_label"],
                "is_boptest": control["is_boptest"],
                "baseline_kpis": control["baseline"]["kpis"],
                "ai_kpis": control["ai_control"]["kpis"],
                "delta": control["delta"],
                "delta_pct": control["delta_pct"],
                "optimisation": control["optimisation"],
            },
            "hvac_reduction": {
                "at_peak_kw": round(applied, 3),
                "requested_kw": round(reduction_at_peak, 3),
                "clipped": bool(applied < reduction_at_peak - 1e-6),
                "peak_reduction_kw": round(float(np.max(reduction)), 3),
                "mean_reduction_kw": round(float(np.mean(reduction)), 3),
                "energy_kwh": round(float(np.sum(reduction)) / 4.0, 3),
                "aligned_at": timestamps[position].to_pydatetime(),
                "provenance": control["provenance"],
            },
            "power_impact": {
                "instant": peak_time.to_pydatetime(),
                "before": {
                    "transformer_loading_pct": before.transformer_loading_pct,
                    "lv_bus_voltage_pu": before.lv_bus_voltage_pu,
                    "losses_kw": before.losses_kw,
                    "status": before.status,
                    "total_load_kw": before.total_load_kw,
                    "feeder_load_kw": before.feeder_load_kw,
                },
                "after": {
                    "transformer_loading_pct": after.transformer_loading_pct,
                    "lv_bus_voltage_pu": after.lv_bus_voltage_pu,
                    "losses_kw": after.losses_kw,
                    "status": after.status,
                    "total_load_kw": after.total_load_kw,
                    "feeder_load_kw": after.feeder_load_kw,
                },
                "delta_loading_pct": round(
                    after.transformer_loading_pct - before.transformer_loading_pct, 3
                ),
                "provenance": self.ems._network_provenance(peak_time.to_pydatetime()).model_dump(
                    mode="json"
                ),
            },
            "chain": [
                {
                    "step": "Power risk",
                    "module": "EMS",
                    "detail": (
                        f"{link['transformer_id']} forecast to reach "
                        f"{link['predicted_peak_loading_pct']:.1f}% at "
                        f"{peak_time:%H:%M}."
                    ),
                    "source_type": "SIMULATED",
                },
                {
                    "step": "Building analysis",
                    "module": "BMS",
                    "detail": (
                        f"HVAC contributes {link['hvac_contribution_kw']:.1f} kW "
                        f"({link['hvac_share_pct']:.0f}% of site demand) at that instant."
                    ),
                    "source_type": "DERIVED",
                },
                {
                    "step": "AI recommendation",
                    "module": "BMS",
                    "detail": (
                        "Setpoint trajectory proposed by the convex optimiser under "
                        "comfort, rate and range constraints."
                    ),
                    "source_type": "OPTIMISED",
                },
                {
                    "step": "Control simulation",
                    "module": "BMS",
                    "detail": (
                        f"{control['engine_label']} ran baseline and proposal: "
                        f"{applied:.1f} kW less HVAC power at the risk instant."
                    ),
                    "source_type": "SIMULATED",
                },
                {
                    "step": "Power impact",
                    "module": "EMS",
                    "detail": (
                        f"Load flow re-solved: {before.transformer_loading_pct:.1f}% → "
                        f"{after.transformer_loading_pct:.1f}% transformer loading."
                    ),
                    "source_type": "SIMULATED",
                },
            ],
        }


@lru_cache(maxsize=1)
def get_crossmodule_service() -> CrossModuleService:
    return CrossModuleService()
