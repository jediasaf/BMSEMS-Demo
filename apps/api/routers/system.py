"""Health, status bar, sources, scenarios and demo reset."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from apps.api.config import Settings, get_settings
from apps.api.schemas.common import HealthResponse, SystemStatus
from core.adapters.building import get_building_adapter
from core.adapters.building.power_laws import demo_window, load_selection
from core.adapters.building.simulation import get_simulation_engine
from core.adapters.power import get_power_adapter
from core.common import paths
from core.enums import DataMode, SimulationEngine
from core.provenance.sources import SOURCES
from core.scenarios import list_scenarios

router = APIRouter(tags=["system"])


def _model_count() -> int:
    if not paths.MODELS_DIR.exists():
        return 0
    return len(list(paths.MODELS_DIR.glob("*.joblib")))


def _pandapower_state() -> tuple[str, str | None]:
    """Solve the default facility's network, rather than assume it solves.

    A load-flow model that imports fine and diverges on contact is exactly the
    failure a health check exists to find before an audience does.
    """
    try:
        from apps.api.services.ems import get_ems_service

        ems = get_ems_service()
        state, _split, _stamp = ems.network_state(ems.default_facility_id())
    except Exception as exc:  # pragma: no cover - reported, never raised
        return "failed", str(exc)
    return ("ok", None) if state.converged else ("degraded", "load flow did not converge")


def _boptest_state(settings: Settings) -> str:
    """live, cached, or local -- and never a word the deployment cannot back up.

    "cached" means a recorded BOPTEST run is being replayed. With no such
    recording the honest answer is "local": an in-process RC model, labelled
    with its own engine everywhere it appears.
    """
    engine = get_simulation_engine(prefer_boptest=bool(settings.boptest_url))
    if engine.engine is SimulationEngine.BOPTEST:
        return "live"
    if engine.engine is SimulationEngine.REPLAY:
        return "cached"
    return "local"


@router.get("/health", response_model=HealthResponse)
@router.get("/api/health", response_model=HealthResponse, include_in_schema=False)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    building = get_building_adapter()
    power = get_power_adapter()
    engine = get_simulation_engine(prefer_boptest=bool(settings.boptest_url))
    models = _model_count()
    network_state, network_error = _pandapower_state()
    real_data = building.data_mode is DataMode.REAL_DATA

    checks = {
        "processed_data": paths.LOAD_PARQUET.exists(),
        "selection": paths.SELECTION_JSON.exists(),
        "models": models > 0,
        "boptest_configured": bool(settings.boptest_url),
        "boptest_reachable": engine.engine is SimulationEngine.BOPTEST,
        "load_flow_converges": network_state == "ok",
    }
    components = {
        "api": "ok",
        "data": "ok" if real_data else "fixture",
        "models": "ok" if models else "missing",
        "pandapower": network_state,
        "boptest": _boptest_state(settings),
    }

    notes: list[str] = []
    if not real_data:
        notes.append(
            "No source files present; values are SAMPLE FIXTURE and are synthetic. "
            "Run scripts/download_data.sh and scripts/prepare_data.py."
        )
    if not models:
        notes.append("No trained models; expected load falls back to a seasonal-naive reference.")
    if components["boptest"] == "local":
        notes.append(
            "BOPTEST is not reachable, so zone simulation uses the in-process EcoTwin "
            "RC engine. Results are labelled with the engine that produced them."
        )
    if network_error:
        notes.append(f"pandapower: {network_error}")

    degraded = not real_data or models == 0 or network_state != "ok"
    return HealthResponse(
        status="degraded" if degraded else "ok",
        version=settings.version,
        data_mode=building.data_mode,
        building_adapter=building.key,
        power_adapter=power.key,
        simulation_engine=engine.engine.value,
        models_loaded=models,
        demo_cache=(paths.DEMO_DIR / "index.json").exists(),
        components=components,
        checks=checks,
        notes=notes,
    )


@router.get("/status", response_model=SystemStatus)
def status(settings: Settings = Depends(get_settings)) -> SystemStatus:
    building = get_building_adapter()
    engine = get_simulation_engine(prefer_boptest=bool(settings.boptest_url))
    selection = load_selection()
    real = building.data_mode is DataMode.REAL_DATA
    descriptor = SOURCES.get(building.source_key)

    simulation_labels = {
        SimulationEngine.BOPTEST: "Live BOPTEST engine",
        SimulationEngine.ECOTWIN_RC: "EcoTwin RC engine",
        SimulationEngine.PANDAPOWER: "pandapower",
        SimulationEngine.REPLAY: "Simulation replay",
    }
    notes: list[str] = []
    if not real:
        notes.append("No source files present. Values are SAMPLE FIXTURE and are synthetic.")
    if engine.engine is not SimulationEngine.BOPTEST:
        notes.append(
            "BOPTEST is not reachable; building simulation uses the EcoTwin RC "
            "engine. Results are labelled with the engine that produced them."
        )
    if selection.get("unit_hypothesis", {}).get("publisher_states_unit") is False:
        notes.append(
            "The source does not publish a unit for its energy counter; kW series "
            "are DERIVED under a validated hypothesis."
        )

    return SystemStatus(
        data_label="Schneider public dataset" if real else "SAMPLE FIXTURE",
        data_mode=building.data_mode,
        data_ok=real,
        ai_label=f"{_model_count()} models online" if _model_count() else "No models",
        ai_ok=_model_count() > 0,
        simulation_label=simulation_labels[engine.engine],
        simulation_ok=True,
        simulation_engine=engine.engine.value,
        interview_mode=settings.interview_mode,
        demo_mode=settings.demo_mode,
        source_name=descriptor.name if descriptor else "unknown",
        source_url=descriptor.url if descriptor else None,
        notes=notes,
    )


@router.get("/sources")
def sources() -> dict[str, Any]:
    """Every source EcoTwin is allowed to cite, plus what was actually used."""
    building = get_building_adapter()
    power = get_power_adapter()
    return {
        "registry": [
            {
                "key": d.key,
                "name": d.name,
                "publisher": d.publisher,
                "url": d.url,
                "licence": d.licence,
                "description": d.description,
                "is_real_measurement": d.is_real_measurement,
            }
            for d in SOURCES.values()
        ],
        "active": {
            "building": building.describe_source(),
            "power": power.describe_source(),
        },
        "selection": load_selection(),
    }


@router.get("/dataset")
def dataset() -> dict[str, Any]:
    """Headline facts about the served dataset, counted rather than estimated.

    The UI shows a "Data source" panel; every figure in it comes from here, so
    it is the real row count of the real files, not a round number chosen to
    look impressive.
    """
    building = get_building_adapter()
    power = get_power_adapter()
    selection = load_selection()
    descriptor = SOURCES.get(building.source_key)

    counts: dict[str, int] = {}
    span: dict[str, str | None] = {"first": None, "last": None}
    try:
        import pandas as pd

        if paths.LOAD_PARQUET.exists():
            load = pd.read_parquet(paths.LOAD_PARQUET, columns=["site_id", "timestamp"])
            counts["load_records"] = int(len(load))
            counts["sites"] = int(load["site_id"].nunique())
            span = {
                "first": load["timestamp"].min().isoformat(),
                "last": load["timestamp"].max().isoformat(),
            }
        if paths.WEATHER_PARQUET.exists():
            counts["weather_records"] = int(
                len(pd.read_parquet(paths.WEATHER_PARQUET, columns=["site_id"]))
            )
        if paths.HOLIDAYS_PARQUET.exists():
            counts["holiday_records"] = int(
                len(pd.read_parquet(paths.HOLIDAYS_PARQUET, columns=["site_id"]))
            )
    except Exception as exc:  # pragma: no cover - defensive
        return {"available": False, "reason": str(exc)}

    counts["total_records"] = sum(v for k, v in counts.items() if k.endswith("_records"))
    return {
        "available": True,
        "name": descriptor.name if descriptor else building.key,
        "publisher": descriptor.publisher if descriptor else "unknown",
        "url": descriptor.url if descriptor else None,
        "licence": descriptor.licence if descriptor else None,
        "data_mode": building.data_mode.value,
        "counts": counts,
        "span": span,
        "sampling_minutes": 15,
        "update_cadence": "static historical archive",
        "access": "read-only",
        "buildings": len(building.list_sites()),
        "facilities": len(power.list_facilities()),
        "models": _model_count(),
        "prepared_at": selection.get("generated_at"),
        "unit_note": (
            selection.get("unit_hypothesis", {}).get("consequence")
            or "kW series are DERIVED from the published energy counter."
        ),
    }


@router.get("/replay-window")
def replay_window() -> dict[str, Any]:
    window = demo_window()
    selection = load_selection()
    if window is None:
        return {"available": False}
    start, end = window
    return {
        "available": True,
        "start": start.to_pydatetime(),
        "end": end.to_pydatetime(),
        "step_minutes": 15,
        "n_steps": int((end - start).total_seconds() // 900),
        "rule": selection.get("demo_window", {}).get("rule"),
        "speeds": [1, 5, 20, 60],
    }


def _scenario_payload(s: Any) -> dict[str, Any]:
    return {
        "scenario_id": s.scenario_id,
        "module": s.module,
        "name": s.name,
        "subtitle": s.subtitle,
        "description": s.description,
        "teaches": s.teaches,
        "is_baseline": s.is_baseline,
        "is_flagship": s.is_flagship,
        "parameters": s.parameters,
        "injected_parameter": s.injected_parameter,
        "magnitude": s.magnitude,
        "duration": s.duration,
        "expected_impact": s.expected_impact,
    }


@router.get("/scenarios")
def scenarios(module: str | None = None) -> dict[str, Any]:
    return {"scenarios": [_scenario_payload(s) for s in list_scenarios(module)]}


@router.post("/demo/reset")
def reset_demo() -> dict[str, Any]:
    """Drop every cache so the next request rebuilds from the source files."""
    from apps.api.services.bms import get_bms_service
    from apps.api.services.crossmodule import get_crossmodule_service
    from apps.api.services.ems import get_ems_service
    from core.adapters.building.power_laws import _load_tables
    from core.adapters.building.registry import reset_adapter_cache as reset_building
    from core.adapters.power.registry import reset_adapter_cache as reset_power

    bms = get_bms_service()
    ems = get_ems_service()
    bms.context.cache_clear()
    bms.zone_params.cache_clear()
    ems.context.cache_clear()
    ems._networks.clear()
    ems._caps.clear()
    get_bms_service.cache_clear()
    get_ems_service.cache_clear()
    get_crossmodule_service.cache_clear()
    reset_building()
    reset_power()
    _load_tables.cache_clear()
    return {
        "reset": True,
        "at": datetime.now(UTC),
        "note": "All service and adapter caches cleared; next request rebuilds from disk.",
    }
