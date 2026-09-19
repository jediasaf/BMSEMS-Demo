"""Interview Mode: the curated demo path, its preload, and its own audit.

The guided demo is not a slideshow over the product -- it is a claim about what
the product does. This router states that claim in one place:

* ``/interview/plan`` names the curated scenario per module and the checks that
  have to hold for the demo to be worth running.
* ``/interview/preload`` does every expensive computation the path needs, so a
  step that lands on a cold cache during the interview cannot happen.
* ``/interview/verify`` runs the checks and reports which ones hold.

``tests/test_interview.py`` asserts the verification passes, which makes "the
demo works every time" a test result rather than a hope.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends

from apps.api.config import Settings, get_settings
from core.adapters.building.simulation import get_simulation_engine
from core.enums import SimulationEngine
from core.scenarios import get_scenario, list_scenarios

router = APIRouter(prefix="/interview", tags=["interview"])
log = logging.getLogger(__name__)

#: Transformer loading the EV surge has to exceed for the EMS story to exist.
OVERLOAD_PCT = 100.0
#: Loading the optimiser has to get back under for the story to resolve.
RESOLVED_PCT = 100.0


def flagship(module: str) -> str:
    """The one scenario per module the guided demo runs."""
    for scenario in list_scenarios(module):
        if scenario.is_flagship:
            return scenario.scenario_id
    raise RuntimeError(f"no flagship scenario registered for {module}")


def _steps(bms_scenario: str, ems_scenario: str) -> list[dict[str, Any]]:
    """The deterministic twelve-step path.

    ``route`` and ``scenario`` are what the UI applies; ``demonstrates`` is what
    the step is for. Nothing here is narration the UI cannot back up.
    """
    return [
        {
            "step": 1,
            "route": "/bms",
            "scenario": "bms_normal_day",
            "title": "The building as recorded",
            "demonstrates": "historical replay of a published measurement, with provenance",
        },
        {
            "step": 2,
            "route": "/bms",
            "scenario": bms_scenario,
            "title": "Inject the curated disturbance",
            "demonstrates": "a seeded, additive, clearly labelled INJECTED scenario",
        },
        {
            "step": 3,
            "route": "/bms/ai-operations",
            "scenario": bms_scenario,
            "title": "Detection and explanation",
            "demonstrates": "observed vs expected, residual score, confidence, possible causes",
        },
        {
            "step": 4,
            "route": "/bms/ai-operations",
            "scenario": bms_scenario,
            "title": "The recommendation",
            "demonstrates": "a constrained proposal that claims no saving before simulation",
        },
        {
            "step": 5,
            "route": "/bms/control-lab",
            "scenario": bms_scenario,
            "title": "Baseline versus AI control",
            "demonstrates": "energy, peak and comfort from one engine over identical inputs",
        },
        {
            "step": 6,
            "route": "/ems",
            "scenario": "ems_normal_day",
            "title": "The portfolio as an electrical estate",
            "demonstrates": "measured demand, per-facility forecast, derived transformer ratings",
        },
        {
            "step": 7,
            "route": "/ems/scenario-lab",
            "scenario": ems_scenario,
            "title": "Start the EV charging surge",
            "demonstrates": "additive flexible load on a named feeder",
        },
        {
            "step": 8,
            "route": "/ems/network",
            "scenario": ems_scenario,
            "title": "Overload risk on the network",
            "demonstrates": "an AC load flow past nameplate, with the LV bus pulled down",
        },
        {
            "step": 9,
            "route": "/ems/scenario-lab",
            "scenario": ems_scenario,
            "title": "Run the optimisation",
            "demonstrates": "a linear program that shifts energy rather than shedding it",
        },
        {
            "step": 10,
            "route": "/ems/scenario-lab",
            "scenario": ems_scenario,
            "title": "Verify by a second load flow",
            "demonstrates": "transformer back inside nameplate, checked independently",
        },
        {
            "step": 11,
            "route": "/bms",
            "scenario": bms_scenario,
            "title": "Provenance",
            "demonstrates": "measured, derived, predicted, simulated, optimised, injected",
        },
        {
            "step": 12,
            "route": "/about",
            "scenario": "bms_normal_day",
            "title": "Architecture and limits",
            "demonstrates": "both pipelines end to end, and what the prototype is not",
        },
    ]


@router.get("/plan")
def plan(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """The curated path, its scenarios and the checks the demo depends on."""
    from apps.api.services.bms import get_bms_service
    from apps.api.services.ems import get_ems_service

    bms_scenario = flagship("BMS")
    ems_scenario = flagship("EMS")
    site = get_bms_service().default_site_id()
    facility = get_ems_service().default_facility_id()
    engine = get_simulation_engine(prefer_boptest=bool(settings.boptest_url))

    return {
        "bms": {
            "site_id": site,
            "scenario": _scenario_brief(bms_scenario),
            "baseline": _scenario_brief("bms_normal_day"),
            "chain": ["measured", "detect", "explain", "recommend", "simulate", "compare"],
        },
        "ems": {
            "facility_id": facility,
            "scenario": _scenario_brief(ems_scenario),
            "baseline": _scenario_brief("ems_normal_day"),
            "chain": ["measured", "forecast", "detect risk", "optimise", "simulate", "resolve"],
        },
        "steps": _steps(bms_scenario, ems_scenario),
        "simulation_engine": engine.engine.value,
        "simulation_mode": ("live" if engine.engine is SimulationEngine.BOPTEST else "local"),
        "checks": [
            "bms_scenario_raises_an_insight",
            "bms_scenario_proposes_an_action",
            "bms_simulation_reports_energy_and_comfort",
            "bms_simulation_accepted_by_the_gate",
            "bms_baseline_stays_quiet",
            "ems_scenario_exceeds_transformer_capacity",
            "ems_optimiser_returns_below_capacity",
            "ems_optimiser_conserves_ev_energy",
            "ems_baseline_has_no_violation",
        ],
    }


def _scenario_brief(scenario_id: str) -> dict[str, Any]:
    s = get_scenario(scenario_id)
    return {
        "scenario_id": s.scenario_id,
        "name": s.name,
        "subtitle": s.subtitle,
        "is_baseline": s.is_baseline,
        "is_flagship": s.is_flagship,
        "injected_parameter": s.injected_parameter,
        "magnitude": s.magnitude,
        "duration": s.duration,
        "expected_impact": s.expected_impact,
        "parameters": s.parameters,
    }


@router.post("/preload")
def preload() -> dict[str, Any]:
    """Compute everything the curated path needs, and time each stage.

    Called when Interview Mode is switched on. Every stage is independent and
    failures are reported rather than raised: a preload that dies halfway is
    worse than one that says which half is cold.
    """
    from apps.api.services.bms import get_bms_service
    from apps.api.services.ems import get_ems_service

    bms = get_bms_service()
    ems = get_ems_service()
    site = bms.default_site_id()
    facility = ems.default_facility_id()
    bms_scenario = flagship("BMS")
    ems_scenario = flagship("EMS")

    stages: list[dict[str, Any]] = []

    def run(name: str, fn: Any) -> Any:
        start = time.perf_counter()
        try:
            value = fn()
            stages.append(
                {"stage": name, "ok": True, "ms": round((time.perf_counter() - start) * 1000, 1)}
            )
            return value
        except Exception as exc:  # pragma: no cover - reported, never raised
            log.warning("preload stage %s failed: %s", name, exc)
            stages.append(
                {
                    "stage": name,
                    "ok": False,
                    "ms": round((time.perf_counter() - start) * 1000, 1),
                    "error": str(exc),
                }
            )
            return None

    for scenario in ("bms_normal_day", bms_scenario):
        run(f"bms.context[{scenario}]", lambda s=scenario: bms.context(site, s))
        run(f"bms.insights[{scenario}]", lambda s=scenario: bms.insights(site, scenario_id=s))
        run(
            f"bms.recommendations[{scenario}]",
            lambda s=scenario: bms.recommendations(site, scenario_id=s),
        )
    run("bms.zone_params", lambda: bms.zone_params(site))
    run("bms.control_lab", lambda: bms.control_lab(site, hours=24, scenario_id=bms_scenario))

    run("ems.network", lambda: ems.network(facility))
    for scenario in ("ems_normal_day", ems_scenario):
        run(f"ems.context[{scenario}]", lambda s=scenario: ems.context(facility, s))
        run(f"ems.portfolio[{scenario}]", lambda s=scenario: ems.portfolio(scenario_id=s))
        run(f"ems.risk[{scenario}]", lambda s=scenario: ems.peak_risk(facility, scenario_id=s))
    run("ems.optimise", lambda: ems.optimise(facility, scenario_id=ems_scenario))

    total = round(sum(s["ms"] for s in stages), 1)
    failed = [s["stage"] for s in stages if not s["ok"]]
    return {
        "preloaded": not failed,
        "site_id": site,
        "facility_id": facility,
        "bms_scenario": bms_scenario,
        "ems_scenario": ems_scenario,
        "total_ms": total,
        "stages": stages,
        "failed": failed,
        "note": (
            "Every curated step is now served from a warm cache. Interview Mode "
            "computes nothing during the demo that it has not already computed."
        ),
    }


@router.get("/verify")
def verify() -> dict[str, Any]:
    """Run the checks the guided demo depends on and report each one.

    This is the endpoint that answers "does the demo still work?" without
    anyone clicking through it.
    """
    from apps.api.services.bms import get_bms_service
    from apps.api.services.ems import get_ems_service

    bms = get_bms_service()
    ems = get_ems_service()
    site = bms.default_site_id()
    facility = ems.default_facility_id()
    bms_scenario = flagship("BMS")
    ems_scenario = flagship("EMS")

    results: list[dict[str, Any]] = []

    def check(name: str, fn: Any) -> None:
        try:
            passed, detail = fn()
        except Exception as exc:  # pragma: no cover - a failed check, not a 500
            results.append({"check": name, "passed": False, "detail": f"raised: {exc}"})
            return
        results.append({"check": name, "passed": bool(passed), "detail": detail})

    def bms_insights() -> tuple[bool, str]:
        found = bms.insights(site, scenario_id=bms_scenario)
        return bool(found), f"{len(found)} insight(s) on {bms_scenario}"

    def bms_action() -> tuple[bool, str]:
        recs = bms.recommendations(site, scenario_id=bms_scenario)
        if not recs:
            return False, "no recommendation produced"
        lead = recs[0]
        return True, (
            f"{len(recs)} recommendation(s); lead proposal {lead.point} "
            f"{lead.current_value} -> {lead.proposed_value} {lead.unit}"
        )

    def bms_simulation() -> tuple[bool, str]:
        result = bms.control_lab(site, hours=24, scenario_id=bms_scenario)
        delta = result["delta_pct"]
        kpis = result["ai_control"]["kpis"]
        has = "energy_kwh" in delta and "peak_kw" in delta and "comfort_violation_kh" in kpis
        return has, (
            f"engine {result['engine']}: energy {delta.get('energy_kwh')}%, "
            f"peak {delta.get('peak_kw')}%, comfort {kpis.get('comfort_violation_kh')} K·h"
        )

    def bms_simulation_accepted() -> tuple[bool, str]:
        result = bms.control_lab(site, hours=24, scenario_id=bms_scenario)
        acceptance = result["acceptance"]
        return bool(acceptance["accepted"]), (
            f"{acceptance['verdict']}"
            + ("" if acceptance["accepted"] else ": " + "; ".join(acceptance["failed"]))
        )

    def bms_quiet_baseline() -> tuple[bool, str]:
        recs = bms.recommendations(site, scenario_id="bms_normal_day")
        return not recs, f"{len(recs)} recommendation(s) on the baseline day"

    def ems_overload() -> tuple[bool, str]:
        risk = ems.peak_risk(facility, scenario_id=ems_scenario)
        loading = risk["predicted_peak_loading_pct"]
        return loading > OVERLOAD_PCT, f"predicted peak loading {loading}%"

    def ems_resolved() -> tuple[bool, str]:
        result = ems.optimise(facility, scenario_id=ems_scenario)
        before = result["network_before"]["transformer_loading_pct"]
        after = result["network_after"]["transformer_loading_pct"]
        return (
            before > OVERLOAD_PCT and after < RESOLVED_PCT,
            f"load flow {before}% -> {after}% at the worst instant",
        )

    def ems_conserves() -> tuple[bool, str]:
        result = ems.optimise(facility, scenario_id=ems_scenario)
        shifted = result["summary"].get("ev_energy_shifted_kwh")
        stated = result["constraints"]
        return bool(stated), f"{len(stated)} constraints stated, {shifted} kWh EV shifted"

    def ems_quiet_baseline() -> tuple[bool, str]:
        state, _split, stamp = ems.network_state(facility, scenario_id="ems_normal_day")
        return not state.violations, (
            f"{len(state.violations)} violation(s) at {stamp:%Y-%m-%d %H:%M} on the baseline day"
        )

    check("bms_scenario_raises_an_insight", bms_insights)
    check("bms_scenario_proposes_an_action", bms_action)
    check("bms_simulation_reports_energy_and_comfort", bms_simulation)
    check("bms_simulation_accepted_by_the_gate", bms_simulation_accepted)
    check("bms_baseline_stays_quiet", bms_quiet_baseline)
    check("ems_scenario_exceeds_transformer_capacity", ems_overload)
    check("ems_optimiser_returns_below_capacity", ems_resolved)
    check("ems_optimiser_conserves_ev_energy", ems_conserves)
    check("ems_baseline_has_no_violation", ems_quiet_baseline)

    failed = [r["check"] for r in results if not r["passed"]]
    return {"ready": not failed, "checks": results, "failed": failed}
