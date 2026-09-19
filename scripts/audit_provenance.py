#!/usr/bin/env python3
"""Audit the provenance of every metric the UI puts on screen.

The provenance model is enforced at construction: a value cannot be tagged
MEASURED unless its registered source is a real measurement, and cannot be
tagged SIMULATED without naming an engine. That stops a *mislabelled* value.
It does not stop an *unlabelled* one -- a number that reaches a chart with no
provenance attached at all, because someone added a field and forgot.

This walks the served payloads against an explicit manifest: for each metric
that matters, where it lives and which categories it is allowed to carry. It
fails on a missing badge, on an unexpected category, and on a manifest entry
whose path no longer exists -- that last one being how a metric quietly
disappears from the audit rather than from the product.

    python scripts/audit_provenance.py [--json]

Exit code is 0 when every claim holds, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.enums import SourceType  # noqa: E402

VALID = {t.value for t in SourceType}

MEASUREMENT_OR_DERIVED = {"MEASURED", "DERIVED"}
MODEL_OUTPUT = {"PREDICTED"}
SIMULATION = {"SIMULATED"}
OPTIMISATION = {"OPTIMISED"}
#: A value computed from a measurement, a forecast or a simulation, depending
#: on the scenario. Widening the set is a decision, so each entry says why.
ANALYTIC = {"DERIVED", "PREDICTED", "SIMULATED"}


@dataclass(frozen=True)
class Claim:
    """One metric the UI shows, and what it is allowed to say about itself."""

    metric: str
    endpoint: str
    #: Dotted path to the object carrying `provenance`. `[]` walks a list,
    #: `[key=value]` selects the element whose field matches.
    path: str
    allowed: set[str]
    params: dict[str, str] = field(default_factory=dict)
    method: str = "GET"
    #: Some values are legitimately absent (no recommendation on a quiet day).
    optional: bool = False
    #: The path points at a provenance record itself, not at a value carrying
    #: one. A few endpoints publish a provenance block for a whole table.
    direct: bool = False


BMS_SCENARIO = {"scenario_id": "bms_hot_day"}
EMS_SCENARIO = {"scenario_id": "ems_ev_surge"}

CLAIMS: tuple[Claim, ...] = (
    # -- BMS ---------------------------------------------------------------
    Claim(
        "building load",
        "/bms/overview",
        "kpis[key=building_load]",
        MEASUREMENT_OR_DERIVED,
        BMS_SCENARIO,
    ),
    Claim(
        "expected load",
        "/bms/overview",
        "kpis[key=expected_load]",
        MODEL_OUTPUT | {"DERIVED"},
        BMS_SCENARIO,
    ),
    Claim(
        "outdoor air temperature",
        "/bms/overview",
        "kpis[key=outdoor_temp]",
        {"MEASURED"},
        BMS_SCENARIO,
    ),
    Claim(
        "occupancy proxy",
        "/bms/overview",
        "kpis[key=occupancy_proxy]",
        {"DERIVED"},
        BMS_SCENARIO,
    ),
    Claim(
        "power density (W/m²)",
        "/bms/overview",
        "kpis[key=energy_intensity]",
        {"DERIVED"},
        BMS_SCENARIO,
    ),
    Claim("every BMS KPI", "/bms/overview", "kpis[]", VALID, BMS_SCENARIO),
    Claim("metered load series", "/bms/overview", "timeline.series[]", VALID, BMS_SCENARIO),
    Claim("anomaly finding", "/bms/overview", "insights[]", VALID, BMS_SCENARIO),
    Claim("anomaly finding", "/bms/insights", "[]", VALID, BMS_SCENARIO),
    Claim(
        "recommended setpoint",
        "/bms/recommendations",
        "[]",
        OPTIMISATION,
        BMS_SCENARIO,
        optional=True,
    ),
    Claim(
        "expected impact of a recommendation",
        "/bms/recommendations",
        "[].expected_impact",
        ANALYTIC | OPTIMISATION,
        BMS_SCENARIO,
        optional=True,
    ),
    Claim(
        "energy and peak saving",
        "/bms/control-lab",
        ".",
        SIMULATION,
        BMS_SCENARIO,
    ),
    Claim("asset tree", "/bms/assets", "root", VALID, BMS_SCENARIO),
    # -- EMS ---------------------------------------------------------------
    Claim(
        "portfolio demand",
        "/ems/portfolio",
        "kpis[key=total_demand]",
        {"DERIVED"},
        EMS_SCENARIO,
    ),
    Claim(
        "predicted portfolio peak",
        "/ems/portfolio",
        "kpis[key=predicted_peak]",
        MODEL_OUTPUT | {"DERIVED"},
        EMS_SCENARIO,
    ),
    Claim("every EMS KPI", "/ems/portfolio", "kpis[]", VALID, EMS_SCENARIO),
    Claim(
        "facility demand column",
        "/ems/portfolio",
        "provenance.demand",
        MEASUREMENT_OR_DERIVED,
        EMS_SCENARIO,
        direct=True,
    ),
    Claim(
        "facility expected column",
        "/ems/portfolio",
        "provenance.expected",
        MODEL_OUTPUT | {"DERIVED"},
        EMS_SCENARIO,
        direct=True,
    ),
    Claim(
        "facility loading column",
        "/ems/portfolio",
        "provenance.loading",
        SIMULATION,
        EMS_SCENARIO,
        direct=True,
    ),
    Claim(
        "network state: loading, voltage, losses",
        "/ems/network",
        ".",
        SIMULATION,
        EMS_SCENARIO,
    ),
    Claim(
        "demand forecast",
        "/ems/risk",
        "provenance.forecast",
        MODEL_OUTPUT,
        EMS_SCENARIO,
        direct=True,
    ),
    Claim(
        "transformer loading",
        "/ems/risk",
        "provenance.loading",
        SIMULATION,
        EMS_SCENARIO,
        direct=True,
    ),
    Claim(
        "injected EV load",
        "/ems/optimise",
        "provenance.injection",
        {"INJECTED"},
        EMS_SCENARIO,
        method="POST",
        direct=True,
    ),
    Claim(
        "optimisation action",
        "/ems/optimise",
        "provenance.optimisation",
        OPTIMISATION,
        EMS_SCENARIO,
        method="POST",
        direct=True,
    ),
    Claim(
        "post-action network state",
        "/ems/optimise",
        "provenance.network",
        SIMULATION,
        EMS_SCENARIO,
        method="POST",
        direct=True,
    ),
    Claim("EMS findings", "/ems/insights", "[]", VALID, EMS_SCENARIO),
)


def resolve(payload: Any, path: str) -> list[tuple[str, Any]]:
    """Return `(where, node)` for every node the path selects."""
    if path == ".":
        return [("", payload)]
    nodes: list[tuple[str, Any]] = [("", payload)]
    for raw in path.split("."):
        token, bracket, selector = raw.partition("[")
        selector = selector.rstrip("]")
        stepped: list[tuple[str, Any]] = []
        for where, node in nodes:
            current = node
            if token:
                if not isinstance(current, dict) or token not in current:
                    continue
                current = current[token]
                where = f"{where}.{token}" if where else token
            if not bracket:
                stepped.append((where, current))
            elif not isinstance(current, list):
                continue
            elif "=" in selector:
                key, _, value = selector.partition("=")
                stepped.extend(
                    (f"{where}[{key}={value}]", item)
                    for item in current
                    if isinstance(item, dict) and str(item.get(key)) == value
                )
            else:
                stepped.extend((f"{where}[{i}]", item) for i, item in enumerate(current))
        nodes = stepped
    return nodes


def audit() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from fastapi.testclient import TestClient

    from apps.api.main import app

    passes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    with TestClient(app) as client:
        for claim in CLAIMS:
            request = client.post if claim.method == "POST" else client.get
            response = request(claim.endpoint, params=claim.params)
            if response.status_code != 200:
                failures.append(
                    {
                        "metric": claim.metric,
                        "where": f"{claim.endpoint} {claim.path}",
                        "problem": f"HTTP {response.status_code}",
                    }
                )
                continue

            nodes = resolve(response.json(), claim.path)
            if not nodes:
                if not claim.optional:
                    failures.append(
                        {
                            "metric": claim.metric,
                            "where": f"{claim.endpoint} {claim.path}",
                            "problem": "path selected nothing; the metric moved or vanished",
                        }
                    )
                continue

            for where, node in nodes:
                location = f"{claim.endpoint} {where or claim.path}"
                if node is None:
                    if not claim.optional:
                        failures.append(
                            {"metric": claim.metric, "where": location, "problem": "null value"}
                        )
                    continue
                if claim.direct:
                    provenance = node if isinstance(node, dict) else None
                else:
                    provenance = node.get("provenance") if isinstance(node, dict) else None
                if not isinstance(provenance, dict):
                    failures.append(
                        {"metric": claim.metric, "where": location, "problem": "no provenance"}
                    )
                    continue
                source_type = provenance.get("source_type")
                if source_type not in VALID:
                    failures.append(
                        {
                            "metric": claim.metric,
                            "where": location,
                            "problem": f"source_type {source_type!r} is outside the vocabulary",
                        }
                    )
                    continue
                if source_type not in claim.allowed:
                    failures.append(
                        {
                            "metric": claim.metric,
                            "where": location,
                            "problem": (
                                f"tagged {source_type}, expected one of " f"{sorted(claim.allowed)}"
                            ),
                        }
                    )
                    continue
                if source_type == "SIMULATED" and not provenance.get("engine"):
                    failures.append(
                        {
                            "metric": claim.metric,
                            "where": location,
                            "problem": "SIMULATED without naming an engine",
                        }
                    )
                    continue
                if not provenance.get("source_name") or not provenance.get("publisher"):
                    failures.append(
                        {
                            "metric": claim.metric,
                            "where": location,
                            "problem": "provenance names no source or no publisher",
                        }
                    )
                    continue
                passes.append(
                    {"metric": claim.metric, "where": location, "source_type": source_type}
                )

    return passes, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    passes, failures = audit()
    if args.json:
        print(json.dumps({"passed": passes, "failed": failures}, indent=2))
    else:
        by_metric: dict[str, set[str]] = {}
        for entry in passes:
            by_metric.setdefault(entry["metric"], set()).add(entry["source_type"])
        width = max((len(m) for m in by_metric), default=10)
        print(f"{len(passes)} values checked across {len(by_metric)} metrics\n")
        for metric in sorted(by_metric):
            print(f"  {metric:<{width}}  {', '.join(sorted(by_metric[metric]))}")
        if failures:
            print(f"\n{len(failures)} FAILURES")
            for failure in failures:
                print(f"  {failure['metric']}: {failure['problem']}\n    at {failure['where']}")
        else:
            print("\nEvery audited metric carries provenance from the closed vocabulary.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
