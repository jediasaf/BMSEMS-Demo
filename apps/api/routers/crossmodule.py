"""BMS ↔ EMS workflow endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from apps.api.schemas.params import AssetId, HorizonHours, ScenarioId

router = APIRouter(prefix="/link", tags=["cross-module"])

# Deferred for the same reason as the BMS router: importing the service layer
# costs ~5 s locally and 94 s on a cold shared vCPU, well past the ~8 s Fly's
# router waits. See apps/api/routers/bms.py.


def _service():
    from apps.api.services.crossmodule import get_crossmodule_service

    return get_crossmodule_service()


@router.get("/peak-to-building")
def peak_to_building(
    facility_id: AssetId = None, scenario_id: ScenarioId = "ems_ev_surge"
) -> dict[str, Any]:
    service = _service()
    fid = facility_id or service.ems.default_facility_id()
    return service.link(fid, scenario_id=scenario_id)


@router.post("/simulate-hvac-action")
def simulate_hvac_action(
    facility_id: AssetId = None,
    scenario_id: ScenarioId = "ems_ev_surge",
    hours: HorizonHours = 24,
) -> dict[str, Any]:
    service = _service()
    fid = facility_id or service.ems.default_facility_id()
    return service.simulate_hvac_action(fid, scenario_id=scenario_id, hours=hours)
