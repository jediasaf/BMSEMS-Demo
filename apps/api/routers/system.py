"""Health, status bar, sources, scenarios and demo reset."""

from __future__ import annotations

from datetime import datetime, timezone
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


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    building = get_building_adapter()
    power = get_power_adapter()
    engine = get_simulation_engine(prefer_boptest=bool(settings.boptest_url))
    models = _model_count()
    checks = {
        "processed_data": paths.LOAD_PARQUET.exists(),
        "selection": paths.SELECTION_JSON.exists(),
        "models": models > 0,
        "boptest_configured": bool(settings.boptest_url),
        "boptest_reachable": engine.engine is SimulationEngine.BOPTEST,
    }
    degraded = building.data_mode is DataMode.SAMPLE_FIXTURE or models == 0
    return HealthResponse(
        status="degraded" if degraded else "ok",
        version=settings.version,
        data_mode=building.data_mode,
        building_adapter=building.key,
        power_adapter=power.key,
        simulation_engine=engine.engine.value,
        models_loaded=models,
        demo_cache=(paths.DEMO_DIR / "index.json").exists(),
        checks=checks,
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
        notes.append(
            "No source files present. Values are SAMPLE FIXTURE and are synthetic."
        )
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


@router.get("/scenarios")
def scenarios(module: str | None = None) -> dict[str, Any]:
    return {
        "scenarios": [
            {
                "scenario_id": s.scenario_id,
                "module": s.module,
                "name": s.name,
                "subtitle": s.subtitle,
                "description": s.description,
                "teaches": s.teaches,
                "is_baseline": s.is_baseline,
                "parameters": s.parameters,
            }
            for s in list_scenarios(module)
        ]
    }


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
        "at": datetime.now(timezone.utc),
        "note": "All service and adapter caches cleared; next request rebuilds from disk.",
    }
