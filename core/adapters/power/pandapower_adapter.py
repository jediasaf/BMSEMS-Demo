"""LV network model and AC load flow.

The source publishes one whole-site meter and no electrical topology, so the
network here is a *model*, and every value it returns is SIMULATED. What keeps
it credible is that nothing is invented freely: the transformer rating comes
from the observed peak by standard sizing practice, the cable impedances are
real catalogue values for the chosen cross-sections, and the split of the
measured total into feeders is a stated disaggregation rather than a set of
fake sub-meters.

Topology::

    External grid (20 kV)
        │
      TR-01  20 kV / 0.4 kV, Dyn11
        │
    LV main busbar (0.4 kV)
        ├── F1  HVAC / chiller plant
        ├── F2  Lighting and small power
        ├── F3  Office / IT
        └── F4  EV charging and flexible load

Feeder disaggregation
---------------------
Weather-dependent and occupancy-dependent components are separated from the
base load first, then shared out over the feeders:

* base  = the site's overnight, unoccupied floor (a robust low quantile);
* hvac  = the part of the load that tracks degree-hours above/below the site's
          published base temperature;
* the remainder is split between lighting/small power and office/IT on a fixed,
  stated ratio.

This is a model of where the measured energy goes, tagged DERIVED. It is not a
claim that four sub-meters exist.
"""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandapower as pp

# pandapower logs a numba advisory on every solve in environments without it;
# the networks here are six buses, so the speed-up is irrelevant.
warnings.filterwarnings("ignore", message=".*numba.*")
logging.getLogger("pandapower.pf.runpp_3ph").setLevel(logging.ERROR)
logging.getLogger("pandapower.auxiliary").setLevel(logging.ERROR)
logging.getLogger("pandapower").setLevel(logging.ERROR)

log = logging.getLogger(__name__)

NOMINAL_LV_KV = 0.4
NOMINAL_MV_KV = 20.0
#: Displacement power factor assumed for every feeder.
POWER_FACTOR = 0.95
#: Statutory LV voltage band, EN 50160: nominal +/- 10%.
VOLTAGE_LIMITS = (0.90, 1.10)
#: Transformer loading above which EcoTwin raises a risk.
LOADING_WARN_PCT = 85.0
LOADING_CRITICAL_PCT = 100.0

#: Design share of the transformer rating each feeder is sized for. They sum to
#: more than 1 on purpose: feeders do not peak together, so each is sized for
#: its own maximum rather than for a pro-rata slice of the total.
FEEDER_DESIGN_SHARE: dict[str, float] = {
    "F1_HVAC": 0.45,
    "F2_LIGHTING": 0.30,
    "F3_OFFICE": 0.35,
    "F4_FLEXIBLE": 0.45,
}

#: Base cable selections, with catalogue values for XLPE aluminium at 0.4 kV.
#: A single run of these carries a small facility; larger ones get parallel
#: circuits of the same cable, which is what is actually installed rather than
#: an implausibly large single conductor.
FEEDER_CABLES: dict[str, dict[str, float]] = {
    "F1_HVAC": {"length_km": 0.055, "r_ohm_per_km": 0.253, "x_ohm_per_km": 0.08, "max_i_ka": 0.29},
    "F2_LIGHTING": {
        "length_km": 0.080,
        "r_ohm_per_km": 0.443,
        "x_ohm_per_km": 0.083,
        "max_i_ka": 0.207,
    },
    "F3_OFFICE": {
        "length_km": 0.065,
        "r_ohm_per_km": 0.443,
        "x_ohm_per_km": 0.083,
        "max_i_ka": 0.207,
    },
    "F4_FLEXIBLE": {
        "length_km": 0.045,
        "r_ohm_per_km": 0.253,
        "x_ohm_per_km": 0.08,
        "max_i_ka": 0.29,
    },
}

FEEDER_LABELS = {
    "F1_HVAC": "HVAC / chiller plant",
    "F2_LIGHTING": "Lighting and small power",
    "F3_OFFICE": "Office and IT",
    "F4_FLEXIBLE": "EV charging / flexible load",
}


def parallel_circuits(transformer_kva: float, feeder: str) -> int:
    """How many parallel runs of the base cable this feeder needs.

    Without this the model uses one cable size for every facility, and on a
    large site the feeders bind long before the transformer does -- the load
    flow then diverges at loads the transformer could comfortably carry, and
    the calibrated capacity comes out at a fraction of nameplate.
    """
    cable = FEEDER_CABLES[feeder]
    design_kva = transformer_kva * FEEDER_DESIGN_SHARE[feeder]
    design_ka = design_kva / (math.sqrt(3.0) * NOMINAL_LV_KV * 1000.0)
    return max(1, int(math.ceil(design_ka / cable["max_i_ka"])))


@dataclass
class FeederSplit:
    """One instant's disaggregation of the measured total, in kW."""

    hvac_kw: float
    lighting_kw: float
    office_kw: float
    flexible_kw: float

    def total(self) -> float:
        return self.hvac_kw + self.lighting_kw + self.office_kw + self.flexible_kw

    def as_dict(self) -> dict[str, float]:
        return {
            "F1_HVAC": self.hvac_kw,
            "F2_LIGHTING": self.lighting_kw,
            "F3_OFFICE": self.office_kw,
            "F4_FLEXIBLE": self.flexible_kw,
        }


@dataclass
class NetworkState:
    """Load-flow result for one instant. Every field is SIMULATED."""

    converged: bool
    total_load_kw: float
    transformer_loading_pct: float
    transformer_kva: float
    lv_bus_voltage_pu: float
    min_bus_voltage_pu: float
    losses_kw: float
    feeder_loading_pct: dict[str, float]
    feeder_load_kw: dict[str, float]
    bus_voltages_pu: dict[str, float]
    line_loading_pct: dict[str, float]
    status: str
    violations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


def disaggregate(
    load_kw: float,
    *,
    base_kw: float,
    outdoor_temp_c: float | None,
    base_temperature_c: float,
    hvac_sensitivity_kw_per_k: float,
    flexible_kw: float = 0.0,
    lighting_share: float = 0.42,
) -> FeederSplit:
    """Split one measured total across the modelled feeders.

    ``load_kw`` is the *measured* site total. ``flexible_kw`` is load added on
    top of it -- an EV charging session, or a scenario injection -- so the
    feeder total is ``load_kw + flexible_kw``. Injected load is never netted
    out of the measurement.

    ``hvac_sensitivity_kw_per_k`` is estimated from the site's own history (see
    ``estimate_hvac_sensitivity``), so the HVAC share is fitted to the building
    rather than assumed.
    """
    degree_hours = 0.0
    if outdoor_temp_c is not None and not np.isnan(outdoor_temp_c):
        degree_hours = max(outdoor_temp_c - base_temperature_c, 0.0) + max(
            base_temperature_c - 4.0 - outdoor_temp_c, 0.0
        )
    hvac = float(np.clip(degree_hours * hvac_sensitivity_kw_per_k, 0.0, max(load_kw, 0.0)))
    remainder = max(load_kw - hvac, 0.0)
    floor = min(base_kw, remainder)
    variable = max(remainder - floor, 0.0)
    lighting = floor * lighting_share + variable * lighting_share
    office = remainder - lighting
    return FeederSplit(
        hvac_kw=round(hvac, 4),
        lighting_kw=round(max(lighting, 0.0), 4),
        office_kw=round(max(office, 0.0), 4),
        flexible_kw=round(max(flexible_kw, 0.0), 4),
    )


def estimate_hvac_sensitivity(
    load_kw: np.ndarray,
    outdoor_temp_c: np.ndarray,
    base_temperature_c: float,
) -> float:
    """kW of load per degree-hour, by least squares on the site's own history.

    A single robust slope, not a per-hour model: this feeds a topology split,
    not a forecast, and an over-fitted disaggregation would be harder to defend
    than a transparent one.
    """
    mask = np.isfinite(load_kw) & np.isfinite(outdoor_temp_c)
    if mask.sum() < 200:
        return 0.0
    load = load_kw[mask]
    temp = outdoor_temp_c[mask]
    degree_hours = np.maximum(temp - base_temperature_c, 0.0) + np.maximum(
        base_temperature_c - 4.0 - temp, 0.0
    )
    if degree_hours.std() < 1e-6:
        return 0.0
    design = np.column_stack([degree_hours, np.ones_like(degree_hours)])
    slope, _ = np.linalg.lstsq(design, load, rcond=None)[0]
    return float(np.clip(slope, 0.0, np.nanpercentile(load, 95) / 10.0))


class PandapowerNetwork:
    """Builds and solves the LV model for one facility."""

    def __init__(self, facility_id: str, transformer_kva: float) -> None:
        self.facility_id = facility_id
        self.transformer_kva = float(transformer_kva)
        self._net: Any | None = None
        self._load_index: dict[str, int] = {}
        self._parallel: dict[str, int] = {}

    # -- construction -----------------------------------------------------
    def build(self) -> Any:
        net = pp.create_empty_network(name=f"EcoTwin LV {self.facility_id}", sn_mva=1.0)

        mv_bus = pp.create_bus(net, vn_kv=NOMINAL_MV_KV, name="MV-GRID")
        lv_bus = pp.create_bus(net, vn_kv=NOMINAL_LV_KV, name="LV-MAIN")
        pp.create_ext_grid(net, bus=mv_bus, vm_pu=1.0, name="Grid supply")

        # Standard distribution transformer characteristics for this rating.
        pp.create_transformer_from_parameters(
            net,
            hv_bus=mv_bus,
            lv_bus=lv_bus,
            sn_mva=self.transformer_kva / 1000.0,
            vn_hv_kv=NOMINAL_MV_KV,
            vn_lv_kv=NOMINAL_LV_KV,
            vkr_percent=1.0,
            vk_percent=6.0,
            pfe_kw=self.transformer_kva * 0.0013,
            i0_percent=0.35,
            shift_degree=150,
            name="TR-01",
            tap_side="hv",
            tap_neutral=0,
            tap_min=-2,
            tap_max=2,
            tap_step_percent=2.5,
            tap_pos=0,
        )

        for feeder, cable in FEEDER_CABLES.items():
            bus = pp.create_bus(net, vn_kv=NOMINAL_LV_KV, name=feeder)
            n = parallel_circuits(self.transformer_kva, feeder)
            self._parallel[feeder] = n
            pp.create_line_from_parameters(
                net,
                from_bus=lv_bus,
                to_bus=bus,
                length_km=cable["length_km"],
                # Parallel runs share the current, so impedance divides and
                # ampacity multiplies.
                r_ohm_per_km=cable["r_ohm_per_km"] / n,
                x_ohm_per_km=cable["x_ohm_per_km"] / n,
                c_nf_per_km=210.0 * n,
                max_i_ka=cable["max_i_ka"] * n,
                name=f"LINE-{feeder}",
            )
            self._load_index[feeder] = pp.create_load(
                net,
                bus=bus,
                p_mw=0.0,
                q_mvar=0.0,
                name=FEEDER_LABELS[feeder],
            )
        self._net = net
        return net

    # -- solving ----------------------------------------------------------
    def solve(self, split: FeederSplit, *, quiet: bool = False) -> NetworkState:
        net = self._net or self.build()
        tan_phi = float(np.tan(np.arccos(POWER_FACTOR)))
        for feeder, kw in split.as_dict().items():
            idx = self._load_index[feeder]
            net.load.at[idx, "p_mw"] = kw / 1000.0
            net.load.at[idx, "q_mvar"] = kw / 1000.0 * tan_phi

        try:
            # Defaults on purpose: a flat start does not converge against the
            # Dyn11 phase shift on this topology.
            pp.runpp(net, algorithm="nr", max_iteration=50)
            converged = bool(net.converged)
        except Exception as exc:
            # `quiet` is for the capacity bisection, which deliberately probes
            # loads past the point where Newton-Raphson can find a solution.
            # There, non-convergence is the answer, not a fault.
            if not quiet:
                log.warning("load flow failed for %s: %s", self.facility_id, exc)
            converged = False

        if not converged:
            return NetworkState(
                converged=False,
                total_load_kw=split.total(),
                transformer_loading_pct=float("nan"),
                transformer_kva=self.transformer_kva,
                lv_bus_voltage_pu=float("nan"),
                min_bus_voltage_pu=float("nan"),
                losses_kw=float("nan"),
                feeder_loading_pct={},
                feeder_load_kw=split.as_dict(),
                bus_voltages_pu={},
                line_loading_pct={},
                status="NOT_CONVERGED",
                violations=["Load flow did not converge"],
            )

        transformer_loading = float(net.res_trafo["loading_percent"].iloc[0])
        bus_names = net.bus["name"].tolist()
        voltages = {
            str(name): round(float(v), 5)
            for name, v in zip(bus_names, net.res_bus["vm_pu"], strict=True)
        }
        line_loading = {
            str(name): round(float(v), 3)
            for name, v in zip(net.line["name"], net.res_line["loading_percent"], strict=True)
        }
        lv_bus_voltage = voltages.get("LV-MAIN", float("nan"))
        lv_only = {k: v for k, v in voltages.items() if k != "MV-GRID"}
        losses = float(net.res_line["pl_mw"].sum() + net.res_trafo["pl_mw"].iloc[0]) * 1000.0

        violations: list[str] = []
        if transformer_loading >= LOADING_CRITICAL_PCT:
            violations.append(f"TR-01 loading {transformer_loading:.1f}% exceeds nameplate")
        for name, value in lv_only.items():
            if not VOLTAGE_LIMITS[0] <= value <= VOLTAGE_LIMITS[1]:
                violations.append(f"{name} voltage {value:.3f} pu outside EN 50160 band")
        for name, value in line_loading.items():
            if value >= 100.0:
                violations.append(f"{name} loading {value:.1f}% exceeds rating")

        if transformer_loading >= LOADING_CRITICAL_PCT or violations:
            status = "CRITICAL"
        elif transformer_loading >= LOADING_WARN_PCT:
            status = "WARNING"
        else:
            status = "NORMAL"

        return NetworkState(
            converged=True,
            total_load_kw=round(split.total(), 3),
            transformer_loading_pct=round(transformer_loading, 3),
            transformer_kva=self.transformer_kva,
            lv_bus_voltage_pu=round(lv_bus_voltage, 5),
            min_bus_voltage_pu=round(min(lv_only.values()), 5) if lv_only else float("nan"),
            losses_kw=round(losses, 4),
            feeder_loading_pct={str(k).replace("LINE-", ""): v for k, v in line_loading.items()},
            feeder_load_kw=split.as_dict(),
            bus_voltages_pu=voltages,
            line_loading_pct=line_loading,
            status=status,
            violations=violations,
            assumptions=[
                f"Transformer rating {self.transformer_kva:.0f} kVA is DERIVED from the "
                "observed peak; the dataset publishes no nameplate data.",
                f"Displacement power factor assumed {POWER_FACTOR} on every feeder.",
                "Feeder split is a stated disaggregation of the measured total, not a "
                "set of measured sub-meters.",
                "Cable impedances are catalogue values for XLPE aluminium at "
                "0.4 kV; each feeder uses as many parallel runs as its design "
                "share of the transformer rating requires.",
            ],
        )

    def capacity_kw(
        self,
        reference: FeederSplit,
        target_loading_pct: float = LOADING_CRITICAL_PCT,
        tolerance_pct: float = 0.05,
        max_iterations: int = 40,
    ) -> float:
        """Real power at which this transformer reaches ``target_loading_pct``.

        Solved by bisection on the load flow rather than computed as
        ``kVA x power_factor``. That shortcut ignores transformer losses and the
        reactive flow the network actually draws, and the error is large enough
        to matter: an optimiser told to hold 147 kW on a 160 kVA unit still
        lands at 100.8% loading. Calibrating against the model the result will
        be judged by removes the discrepancy instead of papering over it with a
        larger safety margin.

        ``reference`` fixes the *shape* of the feeder split; the total is scaled.
        A probe that fails to converge is treated as beyond capacity, which is
        what divergence at extreme loading means physically.
        """
        base_total = reference.total()
        if base_total <= 1e-6:
            return self.transformer_kva * POWER_FACTOR

        def loading_at(total_kw: float) -> float:
            scale = total_kw / base_total
            scaled = FeederSplit(
                hvac_kw=reference.hvac_kw * scale,
                lighting_kw=reference.lighting_kw * scale,
                office_kw=reference.office_kw * scale,
                flexible_kw=reference.flexible_kw * scale,
            )
            state = self.solve(scaled, quiet=True)
            return state.transformer_loading_pct if state.converged else float("inf")

        low = base_total * 0.05
        high = self.transformer_kva * 1.5
        for _ in range(max_iterations):
            mid = 0.5 * (low + high)
            loading = loading_at(mid)
            if abs(loading - target_loading_pct) <= tolerance_pct:
                return float(mid)
            if loading < target_loading_pct:
                low = mid
            else:
                high = mid
        return float(0.5 * (low + high))

    def topology(self) -> dict[str, Any]:
        """Single-line-diagram description for the UI."""
        return {
            "facility_id": self.facility_id,
            "transformer": {
                "id": "TR-01",
                "kva": self.transformer_kva,
                "hv_kv": NOMINAL_MV_KV,
                "lv_kv": NOMINAL_LV_KV,
                "vector_group": "Dyn11",
                "vk_percent": 6.0,
            },
            "buses": ["MV-GRID", "LV-MAIN", *FEEDER_CABLES.keys()],
            "feeders": [
                {
                    "id": feeder,
                    "label": FEEDER_LABELS[feeder],
                    "cable": FEEDER_CABLES[feeder],
                    "parallel_circuits": self._parallel.get(
                        feeder, parallel_circuits(self.transformer_kva, feeder)
                    ),
                    "design_share": FEEDER_DESIGN_SHARE[feeder],
                    "flexible": feeder in ("F1_HVAC", "F4_FLEXIBLE"),
                }
                for feeder in FEEDER_CABLES
            ],
            "limits": {
                "voltage_pu": list(VOLTAGE_LIMITS),
                "transformer_warn_pct": LOADING_WARN_PCT,
                "transformer_critical_pct": LOADING_CRITICAL_PCT,
            },
        }
