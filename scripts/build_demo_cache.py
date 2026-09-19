"""Precompute the results the hosted demo serves.

Why this exists: a hosted demo must never be the slow one. Everything here is
produced by the *same code paths* the live API uses, then written to disk so a
cold container answers immediately. Nothing is invented for the cache, and a
replayed result keeps the engine that originally produced it in its provenance,
with the note ``SIMULATION REPLAY`` added.

The cache is a fallback and a warm-up aid, not a substitute: the API still
computes live wherever it is fast enough (pandapower load flows and the convex
programs are milliseconds), and the cache covers the expensive paths.

Usage:
    python scripts/build_demo_cache.py
    python scripts/build_demo_cache.py --out demo
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from apps.api.services.bms import get_bms_service  # noqa: E402
from apps.api.services.crossmodule import get_crossmodule_service  # noqa: E402
from apps.api.services.ems import get_ems_service  # noqa: E402
from core.scenarios import list_scenarios  # noqa: E402


def _log(msg: str) -> None:
    print(f"[cache] {msg}", flush=True)


def _write(path: Path, payload: Any) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, default=str)
    path.write_text(text)
    return len(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="demo")
    args = parser.parse_args()
    out = REPO_ROOT / args.out

    bms = get_bms_service()
    ems = get_ems_service()
    cross = get_crossmodule_service()

    site = bms.default_site_id()
    facility = ems.default_facility_id()
    index: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "bms_site": site,
        "ems_facility": facility,
        "note": (
            "Produced by the same code paths the live API uses. Replayed "
            "simulation results keep their originating engine in provenance and "
            "are marked SIMULATION REPLAY."
        ),
        "entries": [],
    }

    def record(name: str, path: Path, elapsed: float, size: int) -> None:
        index["entries"].append(
            {
                "key": name,
                "file": str(path.relative_to(REPO_ROOT)),
                "compute_seconds": round(elapsed, 3),
                "bytes": size,
            }
        )
        _log(f"{name}: {elapsed:.2f}s, {size / 1024:.0f} kB")

    bms_scenarios = [s.scenario_id for s in list_scenarios("BMS")]
    ems_scenarios = [s.scenario_id for s in list_scenarios("EMS")]

    # -- BMS ---------------------------------------------------------------
    for scenario in bms_scenarios:
        start = time.perf_counter()
        payload = {
            "site_id": site,
            "scenario_id": scenario,
            "timeline": bms.timeline(site, scenario),
            "kpis": [k.model_dump(mode="json") for k in bms.kpis(site, scenario_id=scenario)],
            "insights": [
                i.model_dump(mode="json") for i in bms.insights(site, scenario_id=scenario)
            ],
            "recommendations": [
                r.model_dump(mode="json") for r in bms.recommendations(site, scenario_id=scenario)
            ],
            "calibration": bms.calibration_report(site),
        }
        path = out / "bms" / f"overview_{scenario}.json"
        record(f"bms/{scenario}", path, time.perf_counter() - start, _write(path, payload))

    start = time.perf_counter()
    control = bms.control_lab(site)
    path = out / "bms" / "control_lab.json"
    record("bms/control-lab", path, time.perf_counter() - start, _write(path, control))

    start = time.perf_counter()
    tree = bms.asset_tree(site).model_dump(mode="json")
    path = out / "bms" / "assets.json"
    record("bms/assets", path, time.perf_counter() - start, _write(path, tree))

    # -- EMS ---------------------------------------------------------------
    for scenario in ems_scenarios:
        start = time.perf_counter()
        portfolio = ems.portfolio(scenario_id=scenario)
        portfolio["kpis"] = [k.model_dump(mode="json") for k in portfolio["kpis"]]
        path = out / "ems" / f"portfolio_{scenario}.json"
        record(
            f"ems/portfolio/{scenario}",
            path,
            time.perf_counter() - start,
            _write(path, portfolio),
        )

        start = time.perf_counter()
        state, split, stamp = ems.network_state(facility, scenario_id=scenario)
        payload = {
            "facility_id": facility,
            "scenario_id": scenario,
            "at": stamp.isoformat(),
            "topology": ems.network(facility).topology(),
            "state": state.__dict__,
            "split": split.as_dict(),
            "risk": ems.peak_risk(facility, scenario_id=scenario),
        }
        path = out / "ems" / f"network_{scenario}.json"
        record(f"ems/network/{scenario}", path, time.perf_counter() - start, _write(path, payload))

    for scenario in ("ems_ev_surge", "ems_peak_demand"):
        start = time.perf_counter()
        payload = ems.optimise(facility, scenario_id=scenario)
        path = out / "ems" / f"optimise_{scenario}.json"
        record(f"ems/optimise/{scenario}", path, time.perf_counter() - start, _write(path, payload))

    # -- cross-module ------------------------------------------------------
    start = time.perf_counter()
    chain = cross.simulate_hvac_action(facility, scenario_id="ems_ev_surge")
    path = out / "ems" / "crossmodule_ev_surge.json"
    record("link/cross-module", path, time.perf_counter() - start, _write(path, chain))

    total = sum(entry["compute_seconds"] for entry in index["entries"])
    total_kb = sum(entry["bytes"] for entry in index["entries"]) / 1024
    index["total_compute_seconds"] = round(total, 2)
    index["total_kilobytes"] = round(total_kb, 1)
    _write(out / "index.json", index)
    _log(f"{len(index['entries'])} entries, {total:.1f}s of compute, {total_kb:.0f} kB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
