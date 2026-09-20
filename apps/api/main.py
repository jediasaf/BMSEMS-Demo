"""EcoTwin AI backend.

Not an official Schneider Electric product. EcoStruxure-ready architecture:
every source-specific detail lives in ``core/adapters``, so the analytics,
optimisation and simulation layers are already independent of where the data
came from.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from apps.api import errors
from apps.api.config import get_settings
from apps.api.routers import bms, crossmodule, ems, interview, system

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("ecotwin")


def _warm_caches() -> None:
    """Fill the caches the demo reads, so the first click is not the slow one."""
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
        ems_service.network(facility)
        # The portfolio view calibrates a transformer capacity per facility by
        # bisection on the load flow. Doing that lazily makes the first click of
        # the demo the slow one, which is the one click that must not be.
        #
        # Each scenario gets its own context, so warming only the baseline
        # leaves the scenario the demo actually runs cold. Three cheap calls
        # here buy a responsive demo throughout.
        for scenario in ("ems_normal_day", "ems_peak_demand", "ems_ev_surge"):
            ems_service.context(facility, scenario)
            ems_service.portfolio(scenario_id=scenario)
        for scenario in ("bms_normal_day", "bms_hot_day", "bms_sensor_drift"):
            bms_service.context(site, scenario)
        log.info(
            "warm-up complete in %.2fs (bms site %s, ems facility %s)",
            time.perf_counter() - start,
            site,
            facility,
        )
    except Exception as exc:  # pragma: no cover - never block start-up
        log.warning("warm-up skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Accept connections immediately; warm the caches behind that.

    The warm-up takes about 19 s against the real dataset. Doing it before
    yielding means uvicorn does not bind until it finishes, and on a host that
    scales to zero the router gives up long before that -- Fly's proxy waits
    about 8 s, so a woken machine refused the very request that woke it.

    Binding first inverts that: `/healthz` answers in milliseconds, the router
    connects, and the caches fill on a worker thread. A request that arrives
    mid-warm-up computes what it needs itself; the caches are keyed and
    idempotent, so the worst case is duplicated work, never a wrong answer.
    """
    task = asyncio.create_task(asyncio.to_thread(_warm_caches))
    try:
        yield
    finally:
        task.cancel()


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

# A closed origin list, and no credentials. The previous `or ["*"]` fallback
# meant a deployment that forgot to configure CORS silently became open to
# every origin on the internet; an empty list now means exactly what it says.
# There are no cookies or auth headers in this API, so allow_credentials stays
# False and `*` is never paired with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["accept", "content-type"],
    max_age=600,
)
if not settings.cors_origin_list:
    log.warning("no CORS origins configured; browsers will block cross-origin requests")


@app.middleware("http")
async def add_timing(request: Request, call_next):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
    return response


app.add_exception_handler(KeyError, errors.key_error_handler)
# FastAPI re-raises anything it has no handler for, which in a hosted
# deployment means whatever the ASGI server decides to print. Owning the
# handler means owning what reaches the browser: an id, never a traceback.
app.add_exception_handler(Exception, errors.unhandled_error_handler)


app.include_router(system.router)
app.include_router(bms.router)
app.include_router(ems.router)
app.include_router(crossmodule.router)
app.include_router(interview.router)


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
