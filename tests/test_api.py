"""API contract tests, run in-process against the real service layer.

These use the actual adapters rather than mocks: the thing worth checking is
that the whole stack answers, with provenance attached to every value.
"""

from __future__ import annotations

import pytest

from core.enums import SourceType
from tests.conftest import requires_models, requires_real_data

VALID_BADGES = {t.value for t in SourceType}


def _check_provenance(provenance: dict) -> None:
    assert provenance["source_type"] in VALID_BADGES
    assert provenance["source_name"]
    assert provenance["publisher"]
    if provenance["source_type"] == "SIMULATED":
        assert provenance["engine"], "SIMULATED must name its engine"


# -- system ---------------------------------------------------------------
def test_health(client) -> None:
    body = client.get("/health").json()
    assert body["status"] in {"ok", "degraded"}
    assert body["data_mode"] in {"REAL_DATA", "SAMPLE_FIXTURE"}
    assert body["building_adapter"] and body["power_adapter"]


def test_status_reports_the_actual_simulation_engine(client) -> None:
    body = client.get("/status").json()
    assert body["simulation_engine"] in {"BOPTEST", "ECOTWIN_RC", "PANDAPOWER", "REPLAY"}
    if body["simulation_engine"] != "BOPTEST":
        # The wording is operator-facing and may be reworded; what must hold is
        # that the status says BOPTEST is not what answered, and names what did.
        notes = " ".join(body["notes"])
        assert "BOPTEST" in notes
        assert "RC engine" in notes


def test_root_carries_the_disclaimer(client) -> None:
    body = client.get("/").json()
    assert "not connect to a live" in body["disclaimer"].lower() or (
        "Not an official" in body["disclaimer"]
    )


def test_sources_lists_the_whole_registry(client) -> None:
    body = client.get("/sources").json()
    keys = {entry["key"] for entry in body["registry"]}
    assert {"power_laws_forecasting", "pandapower", "ecotwin_rc", "cvxpy"} <= keys
    for entry in body["registry"]:
        assert isinstance(entry["is_real_measurement"], bool)


def test_scenarios_are_exposed_per_module(client) -> None:
    bms = client.get("/scenarios", params={"module": "BMS"}).json()["scenarios"]
    ems = client.get("/scenarios", params={"module": "EMS"}).json()["scenarios"]
    assert len(bms) == 3 and len(ems) == 3
    assert all(s["module"] == "BMS" for s in bms)


def test_demo_reset_succeeds(client) -> None:
    assert client.post("/demo/reset").json()["reset"] is True


# -- BMS ------------------------------------------------------------------
@requires_real_data
def test_bms_sites(client) -> None:
    body = client.get("/bms/sites").json()
    assert body["default_site_id"]
    assert body["sites"]


@requires_real_data
@requires_models
def test_bms_overview_attaches_provenance_to_every_value(client) -> None:
    body = client.get("/bms/overview").json()
    assert body["kpis"]
    for kpi in body["kpis"]:
        _check_provenance(kpi["provenance"])
    for series in body["timeline"]["series"]:
        _check_provenance(series["provenance"])
        assert len(series["timestamps"]) == len(series["values"])


@requires_real_data
@requires_models
def test_load_is_derived_never_measured(client) -> None:
    """The publisher states no unit, so a kW value cannot claim to be measured."""
    body = client.get("/bms/overview").json()
    load = next(k for k in body["kpis"] if k["key"] == "building_load")
    assert load["provenance"]["source_type"] == "DERIVED"
    assert load["provenance"]["assumptions"]


@requires_real_data
@requires_models
def test_outdoor_temperature_is_measured(client) -> None:
    body = client.get("/bms/overview").json()
    temp = next(k for k in body["kpis"] if k["key"] == "outdoor_temp")
    assert temp["provenance"]["source_type"] == "MEASURED"


@requires_real_data
@requires_models
def test_scenario_injection_is_reported(client) -> None:
    body = client.get("/bms/overview", params={"scenario_id": "bms_hot_day"}).json()
    assert body["injection"] is not None
    assert body["injection"]["peak_injection"] > 0
    assert body["injection"]["seed"]


@requires_real_data
@requires_models
def test_bms_accepts_a_utc_instant(client) -> None:
    """A client that serialises with a Z must not break the replay."""
    response = client.get("/bms/overview", params={"at": "2017-08-25T12:00:00.000Z"})
    assert response.status_code == 200


@requires_real_data
@requires_models
def test_insights_never_assert_a_cause(client) -> None:
    insights = client.get("/bms/insights", params={"scenario_id": "bms_hot_day"}).json()
    for insight in insights:
        assert insight["possible_causes"]
        assert insight["recommended_next_step"]
        assert 0.0 <= insight["confidence"] <= 1.0
        _check_provenance(insight["provenance"])


@requires_real_data
@requires_models
def test_recommendations_are_advisory_and_claim_no_saving(client) -> None:
    recommendations = client.get(
        "/bms/recommendations", params={"scenario_id": "bms_hot_day"}
    ).json()
    for recommendation in recommendations:
        assert recommendation["mode"] == "ADVISORY"
        assert recommendation["constraints_checked"]
        impact = recommendation["expected_impact"]
        if impact:
            assert impact["energy_kwh"] is None, "no number before the simulator runs"
            assert "simulat" in impact["basis"].lower()


@requires_real_data
@requires_models
def test_validation_endpoint_gates_an_action(client) -> None:
    recommendations = client.get(
        "/bms/recommendations", params={"scenario_id": "bms_hot_day"}
    ).json()
    if not recommendations:
        pytest.skip("no recommendation in this window")
    body = client.post(
        f"/bms/recommendations/{recommendations[0]['recommendation_id']}/validate",
        params={"scenario_id": "bms_hot_day"},
    ).json()
    assert body["mode"] in {"SIMULATION", "BLOCKED"}
    assert body["checks"]
    assert "read-only" in body["note"]


def test_validation_of_an_unknown_recommendation_is_404(client) -> None:
    assert client.post("/bms/recommendations/nope/validate").status_code == 404


@requires_real_data
@requires_models
def test_control_lab_compares_two_runs_of_one_engine(client) -> None:
    body = client.get("/bms/control-lab").json()
    assert body["engine"] in {"BOPTEST", "ECOTWIN_RC"}
    assert body["baseline"]["kpis"] and body["ai_control"]["kpis"]
    assert len(body["timestamps"]) == len(body["baseline"]["zone_temp_c"])
    assert len(body["timestamps"]) == len(body["ai_control"]["zone_temp_c"])
    _check_provenance(body["provenance"])
    assert "same simulator" in body["comparison_note"]
    if body["engine"] != "BOPTEST":
        assert body["is_boptest"] is False


@requires_real_data
@requires_models
def test_model_card_states_how_the_series_is_served(client) -> None:
    body = client.get("/bms/model-card").json()
    assert body["served_by"] in {"model", "seasonal_naive"}
    assert body["gate_reason"]


@requires_real_data
def test_data_quality_reports_missingness(client) -> None:
    body = client.get("/bms/data-quality").json()
    report = body["report"]
    assert report["expected_samples"] >= report["actual_samples"]
    assert 0.0 <= report["missing_pct"] <= 100.0
    assert report["notes"]


@requires_real_data
def test_asset_tree_marks_synthesised_nodes(client) -> None:
    root = client.get("/bms/assets").json()["root"]
    # The site node reads DERIVED, not MEASURED: the meter is a measurement,
    # but the kW figure shown on it is a unit conversion of an energy counter.
    _check_provenance(root["provenance"])
    assert root["provenance"]["source_type"] == "DERIVED"
    assert root["children"]
    floor = root["children"][0]
    _check_provenance(floor["provenance"])
    assert floor["provenance"]["source_type"] in {"DERIVED", "SIMULATED"}
    assert floor["detail"]

    # Equipment and points are modelled, and must name the engine that models
    # them rather than borrowing the building's credibility.
    zone = floor["children"][0]
    equipment = zone["children"][0]
    assert equipment["provenance"]["source_type"] == "SIMULATED"
    assert equipment["provenance"]["engine"]


# -- EMS ------------------------------------------------------------------
@requires_real_data
@requires_models
def test_portfolio_returns_rows_and_kpis(client) -> None:
    body = client.get("/ems/portfolio").json()
    assert body["facilities"]
    for kpi in body["kpis"]:
        _check_provenance(kpi["provenance"])
    for row in body["facilities"]:
        assert row["transformer_kva"] > 0
        assert row["risk_level"]


@requires_real_data
def test_network_state_is_simulated(client) -> None:
    body = client.get("/ems/network").json()
    assert body["state"]["converged"]
    _check_provenance(body["provenance"])
    assert body["provenance"]["source_type"] == "SIMULATED"
    assert body["provenance"]["engine"] == "PANDAPOWER"
    assert body["state"]["assumptions"]


@requires_real_data
@requires_models
def test_ev_surge_creates_a_risk_the_optimiser_resolves(client) -> None:
    risk = client.get("/ems/risk", params={"scenario_id": "ems_ev_surge"}).json()
    assert risk["predicted_peak_loading_pct"] > 100
    assert risk["risk_level"] == "OVERLOAD RISK"

    body = client.post("/ems/optimise", params={"scenario_id": "ems_ev_surge"}).json()
    summary = body["summary"]
    assert summary["peak_reduction_kw"] > 0
    # This has failed on CI and never here, so a bare `assert False` is not
    # enough to tell a different solve from a different problem. Print both:
    # if the inputs match and the outcome does not, it is the solver.
    assert summary["feasible_within_cap"], (
        f"dispatch left {summary['residual_overload_kw']} kW above the "
        f"{summary['cap_kw']:.3f} kW cap.\n"
        f"  inputs   horizon={len(body['baseline_kw'])} "
        f"baseline_sum={sum(body['baseline_kw']):.3f} "
        f"baseline_peak={summary['baseline_peak_kw']:.3f} "
        f"target={summary['target_kw']:.3f}\n"
        f"  solve    status={summary.get('status')} solver={summary.get('solver')} "
        f"optimised_peak={summary['optimised_peak_kw']:.3f} "
        f"deferred_kwh={summary['ev_energy_shifted_kwh']:.3f}"
    )
    # Verified by a second load flow, not by the optimiser's own estimate.
    before = body["network_before"]["transformer_loading_pct"]
    after = body["network_after"]["transformer_loading_pct"]
    assert after < before
    assert after <= 100.0
    assert "not the optimiser" in body["verification_note"]
    # Energy is conserved.
    assert sum(body["ev_reduction_kw"]) == pytest.approx(
        sum(body["ev_recovery_kw"]), rel=1e-3, abs=1e-3
    )

    # And the network -- not the solver -- has the last word on whether the
    # dispatch worked. Every criterion is read off the post-action load flow.
    acceptance = body["acceptance"]
    assert acceptance["accepted"] is True
    assert acceptance["failed"] == []
    checked = " ".join(c["criterion"] for c in acceptance["criteria"])
    assert "transformer loading" in checked
    assert "EN 50160" in checked
    assert "conserved" in checked
    assert "second pandapower solve" in acceptance["note"]


# -- cross-module ---------------------------------------------------------
@requires_real_data
@requires_models
def test_cross_module_chain_is_five_real_steps(client) -> None:
    body = client.post("/link/simulate-hvac-action", params={"scenario_id": "ems_ev_surge"}).json()
    if not body["available"]:
        pytest.skip(body["reason"])
    assert len(body["chain"]) == 5
    modules = [step["module"] for step in body["chain"]]
    assert modules == ["EMS", "BMS", "BMS", "BMS", "EMS"]
    for step in body["chain"]:
        assert step["source_type"] in VALID_BADGES
    # The reduction handed over must come from the simulator, and be applied.
    assert body["hvac_reduction"]["at_peak_kw"] >= 0
    assert body["power_impact"]["after"]["transformer_loading_pct"] <= (
        body["power_impact"]["before"]["transformer_loading_pct"] + 1e-6
    )
    _check_provenance(body["power_impact"]["provenance"])


# -- graceful degradation --------------------------------------------------
def test_control_lab_falls_back_to_a_recording_and_says_so(client, monkeypatch) -> None:
    """A failed simulation degrades to a recording, clearly relabelled."""
    from apps.api.services import demo_cache
    from apps.api.services.bms import BmsService

    if not demo_cache.load("bms/control-lab/bms_hot_day"):
        pytest.skip("no demo cache; run scripts/build_demo_cache.py")

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulation backend unavailable")

    monkeypatch.setattr(BmsService, "control_lab", boom)
    body = client.get("/bms/control-lab", params={"scenario_id": "bms_hot_day"}).json()

    assert body["served_from"] == "demo_cache"
    assert body["provenance"]["source_type"] == "SIMULATED"
    assert body["provenance"]["engine"] == "REPLAY"
    assert "SIMULATION REPLAY" in body["replay_note"]
    # The recording still carries real KPIs; it is stale, not empty.
    assert body["baseline"]["kpis"]["energy_kwh"] > 0


def test_a_recording_is_never_served_for_a_different_scenario(client, monkeypatch) -> None:
    """The failure mode this guards: a hot-day request answered with a quiet day."""
    from apps.api.services.bms import BmsService

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulation backend unavailable")

    monkeypatch.setattr(BmsService, "control_lab", boom)
    # The error reaches the caller rather than a recording for some other
    # scenario. TestClient re-raises server exceptions, so this is the shape
    # a 500 takes in-process.
    with pytest.raises(RuntimeError, match="simulation backend unavailable"):
        client.get("/bms/control-lab", params={"scenario_id": "bms_no_such_scenario"})


def test_a_live_result_says_it_is_live(client) -> None:
    body = client.get("/bms/control-lab", params={"scenario_id": "bms_hot_day"}).json()
    assert body["served_from"] == "live"
    assert "replay_note" not in body
