"""BMS endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from apps.api.services.bms import get_bms_service
from apps.api.services.quality import build_report
from apps.api.services.timeparse import naive_instant
from core.common import paths
from core.common.schemas import Insight, KpiValue, Recommendation
from core.models.anomaly import summarise
from core.optimisation.validation import ControlValidator

router = APIRouter(prefix="/bms", tags=["bms"])


@router.get("/sites")
def sites() -> dict[str, Any]:
    service = get_bms_service()
    default = service.default_site_id()
    return {
        "default_site_id": default,
        "sites": [
            {
                "site_id": s.site_id,
                "name": s.name,
                "surface_m2": s.surface_m2,
                "base_temperature_c": s.base_temperature_c,
                "day_off": s.day_off,
                "sampling_minutes": s.sampling_minutes,
                "first_timestamp": s.first_timestamp,
                "last_timestamp": s.last_timestamp,
                "metrics": list(s.metrics),
                "data_mode": s.data_mode.value,
                "notes": s.notes,
                "is_default": s.site_id == default,
            }
            for s in service.adapter.list_sites()
        ],
    }


@router.get("/overview")
def overview(
    site_id: str | None = None,
    at: datetime | None = None,
    scenario_id: str = Query("bms_normal_day"),
) -> dict[str, Any]:
    service = get_bms_service()
    site = site_id or service.default_site_id()
    try:
        ctx = service.context(site, scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    kpis: list[KpiValue] = service.kpis(site, at=naive_instant(at), scenario_id=scenario_id)
    timeline = service.timeline(site, scenario_id)
    insights = service.insights(site, scenario_id=scenario_id)
    return {
        "site_id": site,
        "site": {
            "name": service.adapter.site(site).name,
            "surface_m2": service.adapter.site(site).surface_m2,
        },
        "scenario_id": scenario_id,
        "injection": ctx.injection.__dict__ if ctx.injection else None,
        "kpis": kpis,
        "timeline": timeline,
        "insights": insights[:6],
        "counts_by_severity": summarise(insights),
        "calibration": service.calibration_report(site),
    }


@router.get("/timeline")
def timeline(
    site_id: str | None = None, scenario_id: str = Query("bms_normal_day")
) -> dict[str, Any]:
    service = get_bms_service()
    return service.timeline(site_id or service.default_site_id(), scenario_id)


@router.get("/insights", response_model=list[Insight])
def insights(
    site_id: str | None = None, scenario_id: str = Query("bms_normal_day")
) -> list[Insight]:
    service = get_bms_service()
    return service.insights(site_id or service.default_site_id(), scenario_id=scenario_id)


@router.get("/recommendations", response_model=list[Recommendation])
def recommendations(
    site_id: str | None = None, scenario_id: str = Query("bms_normal_day")
) -> list[Recommendation]:
    service = get_bms_service()
    return service.recommendations(
        site_id or service.default_site_id(), scenario_id=scenario_id
    )


@router.post("/recommendations/{recommendation_id}/validate")
def validate_recommendation(
    recommendation_id: str,
    site_id: str | None = None,
    scenario_id: str = Query("bms_normal_day"),
) -> dict[str, Any]:
    """Run the safety gate. Nothing is ever written outside a simulator."""
    service = get_bms_service()
    site = site_id or service.default_site_id()
    matches = [
        r
        for r in service.recommendations(site, scenario_id=scenario_id)
        if r.recommendation_id == recommendation_id
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="unknown recommendation")
    outcome = ControlValidator().validate(matches[0], simulation_mode=True)
    return {
        "recommendation_id": recommendation_id,
        "valid": outcome.valid,
        "mode": outcome.mode,
        "checks": outcome.checks,
        "messages": outcome.messages,
        "action": outcome.action.model_dump() if outcome.action else None,
        "note": (
            "Real historical mode is read-only. A validated action may only be "
            "executed against the building simulator."
        ),
    }


@router.get("/assets")
def assets(
    site_id: str | None = None, scenario_id: str = Query("bms_normal_day")
) -> dict[str, Any]:
    service = get_bms_service()
    site = site_id or service.default_site_id()
    return {"root": service.asset_tree(site, scenario_id), "site_id": site}


@router.get("/control-lab")
def control_lab(
    site_id: str | None = None,
    hours: int = Query(24, ge=4, le=48),
    scenario_id: str = Query("bms_normal_day"),
) -> dict[str, Any]:
    service = get_bms_service()
    site = site_id or service.default_site_id()
    result = service.control_lab(site, hours=hours, scenario_id=scenario_id)
    result["calibration"] = service.calibration_report(site)
    return result


@router.get("/model-card")
def model_card(site_id: str | None = None) -> dict[str, Any]:
    service = get_bms_service()
    site = site_id or service.default_site_id()
    ctx = service.context(site)
    return {
        "asset_id": site,
        "served_by": ctx.expected.served_by,
        "gate_reason": ctx.expected.gate_reason,
        "model_id": ctx.expected.model_id,
        "card": ctx.expected.model.card() if ctx.expected.model else None,
    }


@router.get("/data-quality")
def data_quality(site_id: str | None = None) -> dict[str, Any]:
    service = get_bms_service()
    site = site_id or service.default_site_id()
    ctx = service.context(site)
    report = build_report(
        ctx.window,
        asset_id=site,
        units={"load_kw": "kW", "energy_wh_interval": "Wh", "outdoor_temp_c": "°C"},
        source_files=[
            str(paths.LOAD_PARQUET.name),
            str(paths.WEATHER_PARQUET.name),
            str(paths.HOLIDAYS_PARQUET.name),
        ],
    )
    return {
        "asset_id": site,
        "report": report.model_dump(mode="json"),
        "source": service.adapter.describe_source(),
    }
