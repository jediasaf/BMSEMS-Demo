"""The curated demo path, asserted rather than hoped for.

Everything the guided interview shows is produced by the same code paths the
rest of the suite covers. What these tests add is the claim that the *story*
holds: the BMS scenario really does raise a finding that leads to an action a
simulator will accept, and the EMS scenario really does break the transformer
and then get fixed. If a model change quietly makes the demo boring, this is
what fails.
"""

from __future__ import annotations

import pytest

from apps.api.routers.interview import flagship
from core.scenarios import list_scenarios


def test_exactly_one_flagship_scenario_per_module() -> None:
    for module in ("BMS", "EMS"):
        flagships = [s for s in list_scenarios(module) if s.is_flagship]
        assert len(flagships) == 1, f"{module} needs exactly one curated scenario"
        assert not flagships[0].is_baseline, "the curated scenario must inject something"
        assert flagship(module) == flagships[0].scenario_id


def test_every_scenario_states_its_own_parameters() -> None:
    """A scenario that cannot describe itself cannot be defended in an interview."""
    for scenario in list_scenarios():
        assert scenario.injected_parameter, scenario.scenario_id
        assert scenario.magnitude, scenario.scenario_id
        assert scenario.duration, scenario.scenario_id
        assert scenario.expected_impact, scenario.scenario_id
        if scenario.is_baseline:
            assert scenario.injected_parameter == "none"
        else:
            assert scenario.parameters, "an injecting scenario needs numbers behind it"


def test_plan_names_the_curated_scenarios(client) -> None:
    plan = client.get("/interview/plan").json()
    assert plan["bms"]["scenario"]["is_flagship"]
    assert plan["ems"]["scenario"]["is_flagship"]
    assert plan["bms"]["baseline"]["is_baseline"]
    assert plan["ems"]["baseline"]["is_baseline"]
    assert [s["step"] for s in plan["steps"]] == list(range(1, 13))
    for step in plan["steps"]:
        assert step["route"].startswith("/")
        assert step["title"] and step["demonstrates"]


def test_plan_does_not_claim_boptest_it_does_not_have(client) -> None:
    plan = client.get("/interview/plan").json()
    if plan["simulation_engine"] != "BOPTEST":
        assert plan["simulation_mode"] == "local"


def test_preload_warms_every_stage(client) -> None:
    body = client.post("/interview/preload").json()
    assert body["preloaded"], body["failed"]
    assert body["stages"], "preload did nothing"
    assert all(stage["ok"] for stage in body["stages"])


def test_preload_is_idempotent_and_leaves_a_warm_cache(client) -> None:
    """The second call must be cheap: that is the whole point of preloading."""
    client.post("/interview/preload")
    second = client.post("/interview/preload").json()
    assert second["preloaded"]
    # Everything is cached by now, so the slowest stage should be modest. A
    # generous bound: this asserts "warm", not a benchmark.
    slowest = max(stage["ms"] for stage in second["stages"])
    assert slowest < 2500, f"a cached stage took {slowest} ms"


def test_the_demo_verifies(client) -> None:
    """Every claim the guided demo makes, checked against real computation."""
    body = client.get("/interview/verify").json()
    failures = [c for c in body["checks"] if not c["passed"]]
    assert body["ready"], "\n".join(f"{c['check']}: {c['detail']}" for c in failures)


@pytest.mark.parametrize(
    "check",
    [
        "bms_scenario_raises_an_insight",
        "bms_scenario_proposes_an_action",
        "bms_simulation_accepted_by_the_gate",
        "bms_baseline_stays_quiet",
        "ems_scenario_exceeds_transformer_capacity",
        "ems_optimiser_returns_below_capacity",
        "ems_baseline_has_no_violation",
    ],
)
def test_each_demo_claim_individually(client, check: str) -> None:
    """Named separately so a failure says which half of the story broke."""
    body = client.get("/interview/verify").json()
    result = next(c for c in body["checks"] if c["check"] == check)
    assert result["passed"], result["detail"]


def test_the_curated_scenarios_are_reproducible(client) -> None:
    """Two runs, same numbers. A demo that drifts is not a demo."""
    first = client.get("/interview/verify").json()
    client.post("/demo/reset")
    second = client.get("/interview/verify").json()
    assert [c["detail"] for c in first["checks"]] == [c["detail"] for c in second["checks"]]
