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
"""

from __future__ import annotations

import argparse
import json
import math
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="apps/web/public/snapshot")
    parser.add_argument(
        "--cursor-stride",
        type=int,
        default=1,
        help="record every Nth replay step (1 = every step)",
    )
    args = parser.parse_args()
    out = REPO_ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json"):
        stale.unlink()

    from fastapi.testclient import TestClient

    from apps.api.main import app

    started = time.perf_counter()
    index: dict[str, Any] = {
        "recorded_at": datetime.now(UTC).isoformat(),
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
                    "recorded_at": index["recorded_at"],
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

        sites = capture("/bms/sites") or {}
        site = str(sites.get("default_site_id", "227"))
        facilities = capture("/ems/facilities") or {}
        facility = str(facilities.get("default_facility_id", "227"))

        # -- interview mode -----------------------------------------------
        capture("/demo/reset", method="POST")
        capture("/interview/plan")
        capture("/interview/verify")
        capture("/interview/preload", method="POST")

        # -- cursor-independent, per scenario ------------------------------
        capture("/bms/model-card", {"site_id": site})
        capture("/bms/data-quality", {"site_id": site})
        capture("/ems/data-quality", {"facility_id": facility})
        for scenario in bms_scenarios:
            capture("/bms/timeline", {"site_id": site, "scenario_id": scenario})
            capture("/bms/insights", {"site_id": site, "scenario_id": scenario})
            recs = capture("/bms/recommendations", {"site_id": site, "scenario_id": scenario}) or []
            for rec in recs:
                capture(
                    f"/bms/recommendations/{rec['recommendation_id']}/validate",
                    {"site_id": site, "scenario_id": scenario},
                    method="POST",
                )
            for hours in (12, 24, 36, 48):
                capture(
                    "/bms/control-lab",
                    {"site_id": site, "hours": hours, "scenario_id": scenario},
                )
        for scenario in ems_scenarios:
            # The EMS landing page asks for risk across the whole portfolio,
            # with no facility and no cursor. A different call shape is a
            # different file; missing it showed up as an error panel, which is
            # what e2e/snapshot.spec.ts now fails on.
            capture("/ems/risk", {"scenario_id": scenario})
            capture("/ems/insights", {"facility_id": facility, "scenario_id": scenario})
            capture("/link/peak-to-building", {"facility_id": facility, "scenario_id": scenario})
            capture(
                "/link/simulate-hvac-action",
                {"facility_id": facility, "scenario_id": scenario, "hours": 24},
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
                for i in range(0, steps + 1, max(1, args.cursor_stride))
            ]
        _log(f"{len(cursors)} cursor positions x scenarios")

        # /bms/overview is 60 kB, of which 54 kB is the timeline -- and the
        # timeline does not move when the cursor does. Recorded whole at every
        # step it would be 58% of the entire snapshot, the same chart written
        # out 74 times. So the invariant part is written once per scenario and
        # the cursor files carry only the KPIs, which the client merges.
        for scenario in bms_scenarios:
            body = capture("/bms/overview", {"site_id": site, "scenario_id": scenario})
            if body:
                base = {k: v for k, v in body.items() if k != "kpis"}
                text = json.dumps(base, separators=(",", ":"), default=str)
                key = slug("/bms/overview__base", {"site_id": site, "scenario_id": scenario})
                (out / f"{key}.json").write_text(text)
                index["entries"][key] = len(text)
                total_bytes += len(text)

        for i, at in enumerate(cursors):
            for scenario in bms_scenarios:
                if at is None:
                    capture("/bms/overview", {"site_id": site, "scenario_id": scenario})
                else:
                    key = slug(
                        "/bms/overview", {"site_id": site, "scenario_id": scenario, "at": at}
                    )
                    file = out / f"{key}.json"
                    if not file.exists():
                        r = client.get(
                            "/bms/overview",
                            params={"site_id": site, "scenario_id": scenario, "at": at},
                        )
                        if r.status_code == 200:
                            kpis = {
                                "kpis": _round(r.json()["kpis"]),
                                "_snapshot": {
                                    "recorded_at": index["recorded_at"],
                                    "path": "/bms/overview",
                                    "live": False,
                                    "merge_with": "__base",
                                },
                            }
                            text = json.dumps(kpis, separators=(",", ":"), default=str)
                            file.write_text(text)
                            index["entries"][key] = len(text)
                            total_bytes += len(text)
                capture("/bms/assets", {"site_id": site, "scenario_id": scenario, "at": at})
            for scenario in ems_scenarios:
                capture("/ems/portfolio", {"scenario_id": scenario, "at": at})
                capture(
                    "/ems/network",
                    {"facility_id": facility, "scenario_id": scenario, "at": at},
                )
                capture("/ems/risk", {"facility_id": facility, "scenario_id": scenario, "at": at})
                capture(
                    "/ems/optimise",
                    {"facility_id": facility, "scenario_id": scenario, "at": at},
                    method="POST",
                )
            if i and i % 25 == 0:
                _log(f"  {i}/{len(cursors)} cursors, {total_bytes / 1e6:.1f} MB so far")

    # The client needs both to snap a dragged cursor onto a step that exists.
    index["cursor_stride"] = args.cursor_stride
    index["start"] = start
    index["bytes"] = total_bytes
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    _log(
        f"{len(index['entries'])} files, {total_bytes / 1e6:.1f} MB, "
        f"{time.perf_counter() - started:.0f}s -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
