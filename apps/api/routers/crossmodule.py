"""BMS ↔ EMS workflow endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from apps.api.services.crossmodule import get_crossmodule_service

router = APIRouter(prefix="/link", tags=["cross-module"])


@router.get("/peak-to-building")
def peak_to_building(
    facility_id: str | None = None, scenario_id: str = Query("ems_ev_surge")
) -> dict[str, Any]:
    service = get_crossmodule_service()
    fid = facility_id or service.ems.default_facility_id()
    return service.link(fid, scenario_id=scenario_id)


@router.post("/simulate-hvac-action")
def simulate_hvac_action(
    facility_id: str | None = None,
    scenario_id: str = Query("ems_ev_surge"),
    hours: int = Query(24, ge=4, le=48),
) -> dict[str, Any]:
    service = get_crossmodule_service()
    fid = facility_id or service.ems.default_facility_id()
    return service.simulate_hvac_action(fid, scenario_id=scenario_id, hours=hours)
