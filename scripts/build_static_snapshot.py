"""Record the whole demo as static JSON, for a hosting target with no backend.

Why this exists: the interview demo is deterministic. Every scenario is seeded,
the replay window is fixed, and the optimisers return the same answer for the
same inputs. That makes it recordable -- and a recording can be served from a
CDN with no container, no cold start and no bill.

What it costs is honesty about what the viewer is looking at, so that is what
this script is careful about:

* Every response keeps the provenance it was served with. A value that was
  DERIVED is still DERIVED; the recording changes how it reached the browser,
  not what it is.
* Each file carries a ``_snapshot`` block naming when it was recorded and from
  which engine, and the UI reads that to say so on screen.
* Nothing is recomputed, adjusted or rounded into a nicer shape. The only
  transformation is float precision (see ``PRECISION``), which is applied to
  values that are already displayed to fewer digits than that.

Usage:
    python scripts/build_static_snapshot.py
    python scripts/build_static_snapshot.py --out apps/web/public/snapshot
    python scripts/build_static_snapshot.py --sites all --cursor-stride 4
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

#: Decimal places kept in recorded floats. The UI shows at most 4, and the
#: difference is invisible on screen while roughly halving the payload.
PRECISION = 6

#: Sites recorded unless --sites says otherwise. Four buildings rather than all
#: six: the recording's size is linear in the site count, and these four already
#: span three orders of magnitude of floor area (573 m2 to 65,578 m2) and both
#: outcomes of the simulator gate -- 227 is the curated lead site the guided
#: path walks through, and on 143 the gate refuses the proposal, which is worth
#: being able to show.
DEFAULT_SITES = "62,143,162,227"


def _log(msg: str) -> None:
    print(f"[snapshot] {msg}", flush=True)


def _round(value: Any) -> Any:
    """Trim float noise. Ints, strings, None and NaN are returned untouched."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return value
        return round(value, PRECISION)
    if isinstance(value, list):
        return [_round(v) for v in value]
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    return value


def _safe(text: str) -> str:
    """Filename-and-URL-safe, with no percent-encoding.

    urlencode would turn the colons in a timestamp into %3A, which survives as
    a literal in the filename and is then decoded back to ":" by the web server
    when the browser asks for it -- so the file is never found. Replacing the
    awkward characters outright keeps both sides talking about the same name.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "-", text)


def slug(path: str, query: dict[str, Any] | None) -> str:
    """The key the browser will look up. Mirrored by snapshotFile() in api.ts.

    The two must agree exactly, character for character, or the browser asks
    for a file nobody wrote.
    """
    clean = {k: str(v) for k, v in (query or {}).items() if v not in (None, "", "None")}
    parts = [_safe(path.lstrip("/").replace("/", "_"))]
    parts += [f"{_safe(k)}-{_safe(clean[k])}" for k in sorted(clean)]
    return "__".join(parts)


def prepare_out(out: Path, *, fill: bool) -> dict[str, Any]:
    """Ready the output directory, and return the index of what was kept.

    A fresh run starts from empty, so a renamed or removed endpoint cannot
    leave an orphan file behind still answering requests the product no longer
    makes. ``--fill`` instead keeps the recording and writes only what it is
    missing, and hands back its index so this run carries over what the
    recording already settled, such as its date and cursor stride.

    Split out and tested because the two branches are one line apart and
    getting them the wrong way round is silent: a fill that wipes the
    recording it was asked to top up still exits 0.
    """
    out.mkdir(parents=True, exist_ok=True)
    if not fill:
        stale = list(out.glob("*.json"))
        for file in stale:
            file.unlink()
        if stale:
            _log(f"cleared {len(stale)} file(s) from the previous recording")
        return {}
    index_file = out / "index.json"
    previous: dict[str, Any] = json.loads(index_file.read_text()) if index_file.exists() else {}
    kept = len([p for p in out.glob("*.json") if p.name != "index.json"])
    _log(f"fill mode: keeping {kept} recorded file(s), writing only what is missing")
    return previous


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="apps/web/public/snapshot")
    parser.add_argument(
        "--cursor-stride",
        type=int,
        default=None,
        help=(
            "record every Nth replay step (1 = every step); defaults to 1, or "
            "to whatever the existing recording used under --fill"
        ),
    )
    parser.add_argument(
        "--fill",
        action="store_true",
        help=(
            "keep the existing recording and only write files it is missing, "
            "rather than starting from empty"
        ),
    )
    parser.add_argument(
        "--sites",
        default=DEFAULT_SITES,
        help=(
            "comma-separated site ids to serve and record, or 'all' for every "
            f"prepared site (default: {DEFAULT_SITES})"
        ),
    )
    args = parser.parse_args()

    # Narrow the catalogue before anything reads it, so the API itself only
    # ever offers what this run is going to record. A UI-side filter would
    # leave the backend disagreeing with the browser; this way the dropdowns,
    # the portfolio table and its KPIs all describe the same buildings.
    from core.adapters.building.power_laws import DEMO_SITE_IDS_ENV, load_selection

    if args.sites.strip().lower() in ("all", ""):
        os.environ.pop(DEMO_SITE_IDS_ENV, None)
    else:
        os.environ[DEMO_SITE_IDS_ENV] = args.sites
    load_selection.cache_clear()
    catalogue = load_selection().get("catalogue")
    if catalogue:
        _log(
            f"catalogue: serving {catalogue['sites_served']} of "
            f"{catalogue['sites_prepared']} prepared sites "
            f"({', '.join(catalogue['site_ids'])})"
        )

    out = REPO_ROOT / args.out
    previous = prepare_out(out, fill=args.fill)

    # A fill at a coarser stride than the recording it is topping up would
    # leave index.json promising steps that are no longer all there, so the
    # stride carries over unless this run states one.
    stride = args.cursor_stride
    if stride is None:
        stride = int(previous.get("cursor_stride") or 1)
    if args.fill and previous.get("cursor_stride") and stride != previous["cursor_stride"]:
        _log(f"stride {stride} differs from the recording's {previous['cursor_stride']}")

    from fastapi.testclient import TestClient

    from apps.api.main import app

    started = time.perf_counter()
    now = datetime.now(UTC).isoformat()
    index: dict[str, Any] = {
        # What the UI puts on the Recorded chip. In fill mode most files came
        # from the original run, so that is the date to show; the files added
        # now carry their own timestamp, as every payload always has.
        "recorded_at": previous.get("recorded_at", now),
        "note": (
            "Static recording of a live run. Every value keeps the provenance it "
            "was served with; only the delivery is a replay."
        ),
        "entries": {},
    }
    total_bytes = 0

    with TestClient(app) as client:

        def capture(path: str, query: dict[str, Any] | None = None, method: str = "GET") -> Any:
            nonlocal total_bytes
            key = slug(path, query)
            file = out / f"{key}.json"
            if file.exists():
                return json.loads(file.read_text())
            params = {k: v for k, v in (query or {}).items() if v not in (None, "", "None")}
            response = (
                client.get(path, params=params)
                if method == "GET"
                else client.post(path, params=params)
            )
            if response.status_code != 200:
                _log(f"!! {path} {params} -> {response.status_code}, skipped")
                return None
            body = _round(response.json())
            if isinstance(body, dict):
                body["_snapshot"] = {
                    "recorded_at": now,
                    "path": path,
                    "live": False,
                }
            text = json.dumps(body, separators=(",", ":"), default=str)
            file.write_text(text)
            total_bytes += len(text)
            index["entries"][key] = len(text)
            return body

        # -- what the shell needs on every page ---------------------------
        for path in ("/status", "/replay-window", "/sources", "/dataset", "/health", "/healthz"):
            capture(path)
        capture("/scenarios")
        for module in ("BMS", "EMS"):
            capture("/scenarios", {"module": module})

        window = capture("/replay-window") or {}
        steps = int(window.get("n_steps", 0))
        start = window.get("start")

        bms_scenarios = ["bms_normal_day", "bms_hot_day", "bms_sensor_drift"]
        ems_scenarios = ["ems_normal_day", "ems_peak_demand", "ems_ev_surge"]

        # Every site the selector offers, not just the default one. Recording
        # one site while the UI listed six meant a 404 the moment anyone used
        # the Building dropdown or clicked a row in the facility table, which
        # is the first thing a curious viewer does. --sites narrows what the
        # API offers, so these two lists and the dropdowns cannot drift apart.
        sites = capture("/bms/sites") or {}
        site = str(sites.get("default_site_id", "227"))
        all_sites = [str(s["site_id"]) for s in sites.get("sites", [])] or [site]
        facilities = capture("/ems/facilities") or {}
        facility = str(facilities.get("default_facility_id", "227"))
        all_facilities = [str(f["facility_id"]) for f in facilities.get("facilities", [])] or [
            facility
        ]
        _log(f"{len(all_sites)} sites x {len(all_facilities)} facilities")

        # -- interview mode -----------------------------------------------
        capture("/demo/reset", method="POST")
        capture("/interview/plan")
        capture("/interview/verify")
        capture("/interview/preload", method="POST")

        # -- cursor-independent, per scenario ------------------------------
        for s_id in all_sites:
            capture("/bms/model-card", {"site_id": s_id})
            capture("/bms/data-quality", {"site_id": s_id})
            for scenario in bms_scenarios:
                capture("/bms/timeline", {"site_id": s_id, "scenario_id": scenario})
                capture("/bms/insights", {"site_id": s_id, "scenario_id": scenario})
                recs = (
                    capture("/bms/recommendations", {"site_id": s_id, "scenario_id": scenario})
                    or []
                )
                for rec in recs:
                    capture(
                        f"/bms/recommendations/{rec['recommendation_id']}/validate",
                        {"site_id": s_id, "scenario_id": scenario},
                        method="POST",
                    )
                for hours in (12, 24, 36, 48):
                    capture(
                        "/bms/control-lab",
                        {"site_id": s_id, "hours": hours, "scenario_id": scenario},
                    )
        for f_id in all_facilities:
            capture("/ems/data-quality", {"facility_id": f_id})
            for scenario in ems_scenarios:
                capture("/ems/insights", {"facility_id": f_id, "scenario_id": scenario})
                capture("/link/peak-to-building", {"facility_id": f_id, "scenario_id": scenario})
        for scenario in ems_scenarios:
            # The EMS landing page asks for risk across the whole portfolio,
            # with no facility and no cursor. A different call shape is a
            # different file; missing it showed up as an error panel, which is
            # what e2e/snapshot.spec.ts now fails on.
            capture("/ems/risk", {"scenario_id": scenario})
            # Per facility, not just the default one: the Scenario Lab runs
            # this chain for whichever facility is selected, so recording only
            # the default put a 404 behind its dropdown.
            for f_id in all_facilities:
                capture(
                    "/link/simulate-hvac-action",
                    {"facility_id": f_id, "scenario_id": scenario, "hours": 24},
                    method="POST",
                )

        # -- cursor-dependent ----------------------------------------------
        # These are what the replay slider drives. Recorded at every step the
        # slider can land on, so dragging it reads real recorded values rather
        # than the nearest thing we happened to keep.
        cursors: list[str | None] = [None]
        if start and steps:
            import pandas as pd

            base = pd.Timestamp(start)
            cursors += [
                (base + pd.Timedelta(minutes=15 * i)).strftime("%Y-%m-%dT%H:%M:%S")
                for i in range(0, steps + 1, max(1, stride))
            ]
        _log(f"{len(cursors)} cursor positions x scenarios")

        # /bms/overview is 60 kB, of which 54 kB is the timeline -- and the
        # timeline does not move when the cursor does. Recorded whole at every
        # step it would be 58% of the entire snapshot, the same chart written
        # out 74 times. So the invariant part is written once per scenario and
        # the cursor files carry only the KPIs, which the client merges.
        for s_id in all_sites:
            for scenario in bms_scenarios:
                body = capture("/bms/overview", {"site_id": s_id, "scenario_id": scenario})
                if body:
                    base = {k: v for k, v in body.items() if k != "kpis"}
                    text = json.dumps(base, separators=(",", ":"), default=str)
                    key = slug("/bms/overview__base", {"site_id": s_id, "scenario_id": scenario})
                    (out / f"{key}.json").write_text(text)
                    index["entries"][key] = len(text)
                    total_bytes += len(text)

        for i, at in enumerate(cursors):
            for s_id in all_sites:
                for scenario in bms_scenarios:
                    if at is None:
                        capture("/bms/overview", {"site_id": s_id, "scenario_id": scenario})
                    else:
                        key = slug(
                            "/bms/overview", {"site_id": s_id, "scenario_id": scenario, "at": at}
                        )
                        file = out / f"{key}.json"
                        if not file.exists():
                            r = client.get(
                                "/bms/overview",
                                params={"site_id": s_id, "scenario_id": scenario, "at": at},
                            )
                            if r.status_code == 200:
                                kpis = {
                                    "kpis": _round(r.json()["kpis"]),
                                    "_snapshot": {
                                        "recorded_at": now,
                                        "path": "/bms/overview",
                                        "live": False,
                                        "merge_with": "__base",
                                    },
                                }
                                text = json.dumps(kpis, separators=(",", ":"), default=str)
                                file.write_text(text)
                                index["entries"][key] = len(text)
                                total_bytes += len(text)
                    capture("/bms/assets", {"site_id": s_id, "scenario_id": scenario, "at": at})
            for scenario in ems_scenarios:
                capture("/ems/portfolio", {"scenario_id": scenario, "at": at})
                for f_id in all_facilities:
                    capture(
                        "/ems/network",
                        {"facility_id": f_id, "scenario_id": scenario, "at": at},
                    )
                    capture("/ems/risk", {"facility_id": f_id, "scenario_id": scenario, "at": at})
                    capture(
                        "/ems/optimise",
                        {"facility_id": f_id, "scenario_id": scenario, "at": at},
                        method="POST",
                    )
            if i and i % 25 == 0:
                _log(f"  {i}/{len(cursors)} cursors, {total_bytes / 1e6:.1f} MB so far")

    # The index has to describe the directory rather than the run: the base
    # files are written outside capture(), and in fill mode most of the
    # recording predates this process. Scanning is the only description of it
    # that cannot drift.
    index["entries"] = {}
    total_bytes = 0
    for file in sorted(out.glob("*.json")):
        if file.name == "index.json":
            continue
        size = file.stat().st_size
        index["entries"][file.stem] = size
        total_bytes += size
    if args.fill:
        index["filled_at"] = now

    # The client needs both to snap a dragged cursor onto a step that exists.
    index["cursor_stride"] = stride
    index["start"] = start
    index["bytes"] = total_bytes
    # What the recording covers, so a checker does not have to infer it from
    # filenames: these are the only sites the recorded API offers.
    index["sites"] = all_sites
    index["facilities"] = all_facilities
    index["default_site_id"] = site
    index["default_facility_id"] = facility
    if catalogue:
        index["catalogue"] = catalogue
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    _log(
        f"{len(index['entries'])} files, {total_bytes / 1e6:.1f} MB, "
        f"{time.perf_counter() - started:.0f}s -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
