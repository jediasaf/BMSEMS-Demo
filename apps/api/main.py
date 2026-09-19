"""EcoTwin AI backend.

Not an official Schneider Electric product. EcoStruxure-ready architecture:
every source-specific detail lives in ``core/adapters``, so the analytics,
optimisation and simulation layers are already independent of where the data
came from.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.config import get_settings
from apps.api.routers import bms, crossmodule, ems, system

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("ecotwin")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Warm the caches at start-up so the first demo click is not the slow one."""
    from apps.api.services.bms import get_bms_service
    from apps.api.services.ems import get_ems_service

    start = time.perf_counter()
    try:
        bms_service = get_bms_service()
        site = bms_service.default_site_id()
        bms_service.context(site)
        bms_service.zone_params(site)
        ems_service = get_ems_service()
        facility = ems_service.default_facility_id()
        ems_service.context(facility)
        ems_service.network(facility)
        # The portfolio view calibrates a transformer capacity per facility by
        # bisection on the load flow. Doing that lazily makes the first click of
        # the demo the slow one, which is the one click that must not be.
        ems_service.portfolio()
        log.info(
            "warm-up complete in %.2fs (bms site %s, ems facility %s)",
            time.perf_counter() - start,
            site,
            facility,
        )
    except Exception as exc:  # pragma: no cover - never block start-up
        log.warning("warm-up skipped: %s", exc)
    yield


app = FastAPI(
    title="EcoTwin AI",
    description=(
        "AI Building & Power Operations Platform. This prototype does not connect "
        "to a live Schneider Electric customer environment; public Schneider data "
        "are used for analytics and control experiments run in simulation."
    ),
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    return response


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


app.include_router(system.router)
app.include_router(bms.router)
app.include_router(ems.router)
app.include_router(crossmodule.router)


@app.get("/", tags=["system"])
def root() -> dict[str, object]:
    return {
        "name": "EcoTwin AI",
        "subtitle": "AI Building & Power Operations Platform",
        "version": settings.version,
        "modules": ["EcoTwin BMS — AI Building Operator", "EcoTwin EMS — AI Power Operator"],
        "disclaimer": (
            "Not an official Schneider Electric product. EcoStruxure-ready "
            "architecture, designed for future integration with EcoStruxure "
            "Building Operation and EcoStruxure Power Monitoring Expert."
        ),
        "docs": "/docs",
    }
