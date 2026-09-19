"""EMS endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from apps.api.services.ems import get_ems_service
from apps.api.services.quality import build_report
from core.common import paths
from core.common.schemas import Insight

router = APIRouter(prefix="/ems", tags=["ems"])


@router.get("/facilities")
def facilities() -> dict[str, Any]:
    service = get_ems_service()
    default = service.default_facility_id()
    return {
        "default_facility_id": default,
        "facilities": [
            {
                "facility_id": f.facility_id,
                "name": f.name,
                "surface_m2": f.surface_m2,
                "main_meter_id": f.main_meter_id,
                "transformer_kva": f.transformer_kva,
                "baseline_kw": f.baseline_kw,
                "peak_kw": f.peak_kw,
                "data_mode": f.data_mode.value,
                "notes": f.notes,
                "is_default": f.facility_id == default,
            }
            for f in service.facilities()
        ],
    }


@router.get("/portfolio")
def portfolio(
    at: datetime | None = None, scenario_id: str = Query("ems_normal_day")
) -> dict[str, Any]:
    return get_ems_service().portfolio(at=at, scenario_id=scenario_id)


@router.get("/network")
def network(
    facility_id: str | None = None,
    at: datetime | None = None,
    scenario_id: str = Query("ems_normal_day"),
) -> dict[str, Any]:
    service = get_ems_service()
    fid = facility_id or service.default_facility_id()
    try:
        state, split, stamp = service.network_state(fid, at=at, scenario_id=scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ctx = service.context(fid, scenario_id)
    return {
        "facility_id": fid,
        "at": stamp.to_pydatetime(),
        "scenario_id": scenario_id,
        "topology": service.network(fid).topology(),
        "state": {
            "converged": state.converged,
            "total_load_kw": state.total_load_kw,
            "transformer_loading_pct": state.transformer_loading_pct,
            "transformer_kva": state.transformer_kva,
            "lv_bus_voltage_pu": state.lv_bus_voltage_pu,
            "min_bus_voltage_pu": state.min_bus_voltage_pu,
            "losses_kw": state.losses_kw,
            "feeder_load_kw": state.feeder_load_kw,
            "feeder_loading_pct": state.feeder_loading_pct,
            "bus_voltages_pu": state.bus_voltages_pu,
            "line_loading_pct": state.line_loading_pct,
            "status": state.status,
            "violations": state.violations,
            "assumptions": state.assumptions,
        },
        "split": split.as_dict(),
        "cap_kw": round(ctx.cap_kw, 2),
        "provenance": service._network_provenance(stamp.to_pydatetime()).model_dump(
            mode="json"
        ),
    }


@router.get("/risk")
def risk(
    facility_id: str | None = None,
    at: datetime | None = None,
    scenario_id: str = Query("ems_normal_day"),
) -> dict[str, Any]:
    service = get_ems_service()
    return service.peak_risk(
        facility_id or service.default_facility_id(), at=at, scenario_id=scenario_id
    )


@router.post("/optimise")
def optimise(
    facility_id: str | None = None,
    at: datetime | None = None,
    scenario_id: str = Query("ems_ev_surge"),
) -> dict[str, Any]:
    service = get_ems_service()
    return service.optimise(
        facility_id or service.default_facility_id(), at=at, scenario_id=scenario_id
    )


@router.get("/insights", response_model=list[Insight])
def insights(
    facility_id: str | None = None, scenario_id: str = Query("ems_normal_day")
) -> list[Insight]:
    service = get_ems_service()
    return service.insights(
        facility_id or service.default_facility_id(), scenario_id=scenario_id
    )


@router.get("/data-quality")
def data_quality(facility_id: str | None = None) -> dict[str, Any]:
    service = get_ems_service()
    fid = facility_id or service.default_facility_id()
    ctx = service.context(fid)
    report = build_report(
        ctx.window,
        asset_id=fid,
        units={"load_kw": "kW", "energy_wh_interval": "Wh", "outdoor_temp_c": "°C"},
        source_files=[str(paths.LOAD_PARQUET.name), str(paths.WEATHER_PARQUET.name)],
    )
    return {
        "asset_id": fid,
        "report": report.model_dump(mode="json"),
        "source": service.adapter.describe_source(),
    }
