"""Check that a recorded snapshot still says what the demo claims.

A recording can go stale in a way a live backend cannot: the files keep
answering long after the code that produced them changed. This reads the
snapshot as a browser would and asserts the same things `/interview/verify`
asserts against a running API, so a recording that no longer holds up fails
here rather than in front of an audience.

    python scripts/verify_snapshot.py
    python scripts/verify_snapshot.py --dir apps/web/public/snapshot
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="apps/web/public/snapshot")
    args = parser.parse_args()
    root = REPO_ROOT / args.dir

    if not root.exists():
        print(f"FAIL  no snapshot at {args.dir} — run scripts/build_static_snapshot.py")
        return 1

    index = json.loads((root / "index.json").read_text())
    failures: list[str] = []

    def read(name: str) -> Any:
        file = root / f"{name}.json"
        if not file.exists():
            failures.append(f"missing {name}.json")
            return None
        return json.loads(file.read_text())

    print(f"snapshot recorded {index.get('recorded_at')}")
    print(f"{len(index.get('entries', {}))} files, {index.get('bytes', 0) / 1e6:.1f} MB")

    # 1. The recorded verdict must itself be a pass.
    verify = read("interview_verify")
    if verify is not None:
        for check in verify.get("checks", []):
            if not check["passed"]:
                failures.append(f"recorded check failed: {check['check']} — {check['detail']}")
        if not verify.get("ready"):
            failures.append("recorded /interview/verify says ready=false")
        else:
            print(f"recorded verdict: ready, {len(verify.get('checks', []))} checks")

    # 2. Every file must declare itself a recording, so nothing can be mistaken
    #    for a live answer just because it is well formed.
    unlabelled = []
    for file in root.glob("*.json"):
        if file.name == "index.json":
            continue
        body = json.loads(file.read_text())
        if isinstance(body, dict) and not body.get("_snapshot"):
            unlabelled.append(file.name)
    if unlabelled:
        failures.append(
            f"{len(unlabelled)} file(s) carry no _snapshot marker, " f"e.g. {unlabelled[0]}"
        )
    else:
        print("every payload is marked as recorded")

    # 3. The claim the demo actually makes is about the curated position --
    #    the one /interview/verify checks and the guided path lands on. Other
    #    cursors are not required to resolve, and many correctly do not: the
    #    optimiser looks 12 hours ahead, so from early morning the afternoon
    #    surge is at the edge of the horizon and there is nowhere to shift the
    #    load to. The gate rejects those, which is the gate doing its job.
    ev = read("ems_optimise__facility_id-227__scenario_id-ems_ev_surge")
    if ev is not None:
        before = ev["network_before"]["transformer_loading_pct"]
        after = ev["network_after"]["transformer_loading_pct"]
        if not (before > 100 >= after):
            failures.append(f"curated EV surge no longer resolves: {before}% -> {after}%")
        elif not ev.get("acceptance", {}).get("accepted"):
            failures.append("curated EV-surge dispatch is rejected by the recorded network gate")
        else:
            print(f"EMS (curated): {before:.1f}% -> {after:.1f}%, network gate accepted")

    # How the gate behaves across the rest of the window, reported rather than
    # asserted: a recording in which nothing is ever rejected would mean the
    # gate had stopped being able to say no.
    over = accepted = rejected = 0
    for file in root.glob("ems_optimise__*ems_ev_surge*.json"):
        body = json.loads(file.read_text())
        if body.get("network_before", {}).get("transformer_loading_pct", 0) <= 100:
            continue
        over += 1
        if body.get("acceptance", {}).get("accepted"):
            accepted += 1
        else:
            rejected += 1
    if over:
        print(
            f"across {over} over-nameplate cursors: {accepted} dispatches accepted, "
            f"{rejected} rejected by the gate"
        )
        if not rejected:
            print("  (note: the gate never refused — worth checking it still can)")

    # The Control Lab claim is about the 24-hour horizon the demo runs.
    lab_file = next(iter(sorted(root.glob("bms_control-lab__hours-24__*bms_hot_day*.json"))), None)
    if lab_file is None:
        failures.append("no 24-hour Control Lab recording for the hot-day scenario")
    else:
        lab = json.loads(lab_file.read_text())
        if not lab.get("acceptance", {}).get("accepted"):
            failures.append("Control Lab proposal is not accepted by the recorded simulator gate")
        else:
            d = lab["delta_pct"]
            print(
                f"BMS: {d.get('energy_kwh'):+.2f}% energy, {d.get('peak_kw'):+.2f}% peak, "
                "simulator gate accepted"
            )

    if failures:
        print()
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print("\nsnapshot is consistent with what the demo claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
