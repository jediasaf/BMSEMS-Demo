"""BOPTEST client.

A real client for the BOPTEST REST API (IBPSA Project 1). It is kept in its own
module so the distinction stays structural, not just a comment: everything in
``simulation.py`` runs in-process, everything here needs a service to answer.

The class only ever reports ``SimulationEngine.BOPTEST``. If the instance is
unreachable, ``available()`` returns False and the Control Lab falls back to the
in-process RC engine — which is then labelled as the RC engine, never as this.

Local Docker mode starts an instance:

    docker compose --profile boptest up
    ECOTWIN_BOPTEST_URL=http://boptest:5000
"""

from __future__ import annotations

import contextlib
import logging
import os
from datetime import datetime, timedelta

import numpy as np

from core.adapters.building.simulation import (
    STEP_MINUTES,
    STEP_SECONDS,
    STEPS_PER_HOUR,
    BuildingSimulationEngine,
    SimulationRequest,
    SimulationResult,
)
from core.enums import SimulationEngine

log = logging.getLogger(__name__)


class BoptestEngine(BuildingSimulationEngine):
    """Client for a BOPTEST REST instance (IBPSA Project 1).

    Only reports ``SimulationEngine.BOPTEST`` when a BOPTEST instance actually
    answered. ``available()`` probes the service; if the probe fails the Control
    Lab falls back to the RC engine and says so.
    """

    engine = SimulationEngine.BOPTEST
    version = "boptest-rest"

    #: Test case shipped with BOPTEST that matches this use case: a single
    #: conditioned zone with an air-source heat pump and a settable setpoint.
    TESTCASE = "bestest_hydronic_heat_pump"

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or os.environ.get("BOPTEST_URL", "")).rstrip("/")
        self.timeout = timeout
        self._testid: str | None = None

    def available(self) -> bool:
        if not self.base_url:
            return False
        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/version")
                if response.status_code != 200:
                    return False
                self.version = f"boptest-{response.json().get('version', 'unknown')}"
                return True
        except Exception as exc:  # pragma: no cover - network dependent
            log.info("BOPTEST not reachable at %s: %s", self.base_url, exc)
            return False

    def _select(self, client: object) -> str:  # pragma: no cover - network dependent
        response = client.post(  # type: ignore[attr-defined]
            f"{self.base_url}/testcases/{self.TESTCASE}/select"
        )
        response.raise_for_status()
        return str(response.json()["testid"])

    def simulate(self, request: SimulationRequest) -> SimulationResult:  # pragma: no cover
        import httpx

        horizon = request.horizon()
        with httpx.Client(timeout=self.timeout) as client:
            testid = self._select(client)
            try:
                client.put(
                    f"{self.base_url}/initialize/{testid}",
                    json={"start_time": 0, "warmup_period": 86400},
                ).raise_for_status()
                client.put(
                    f"{self.base_url}/step/{testid}", json={"step": STEP_SECONDS}
                ).raise_for_status()

                zone_temp: list[float] = []
                power: list[float] = []
                outdoor: list[float] = []
                timestamps: list[datetime] = []
                for step in range(horizon):
                    payload = {
                        "reaTSetHea_u": request.setpoints_c[step] - 1.0 + 273.15,
                        "reaTSetHea_activate": 1,
                        "reaTSetCoo_u": request.setpoints_c[step] + 273.15,
                        "reaTSetCoo_activate": 1,
                    }
                    response = client.post(f"{self.base_url}/advance/{testid}", json=payload)
                    response.raise_for_status()
                    point = response.json()["payload"]
                    zone_temp.append(float(point.get("reaTZon_y", 293.15)) - 273.15)
                    power.append(float(point.get("reaPHeaPum_y", 0.0)) / 1000.0)
                    outdoor.append(float(request.outdoor_temp_c[step]))
                    timestamps.append(request.start + timedelta(minutes=STEP_MINUTES * step))
            finally:
                with contextlib.suppress(Exception):
                    client.put(f"{self.base_url}/stop/{testid}")

        violation_kh = 0.0
        violations = 0
        for step, temp in enumerate(zone_temp):
            lower, upper = request.comfort.bounds(request.occupancy[step] > 0.15)
            if temp > upper:
                violation_kh += (temp - upper) / STEPS_PER_HOUR
                violations += 1
            elif temp < lower:
                violation_kh += (lower - temp) / STEPS_PER_HOUR
                violations += 1

        return SimulationResult(
            engine=self.engine,
            engine_version=self.version,
            label=request.label,
            asset_id=request.asset_id,
            zone_id=request.zone_id,
            timestamps=timestamps,
            zone_temp_c=zone_temp,
            mass_temp_c=zone_temp,
            setpoint_c=[float(s) for s in request.setpoints_c],
            hvac_electrical_kw=power,
            outdoor_temp_c=outdoor,
            energy_kwh=float(np.sum(power) / STEPS_PER_HOUR),
            peak_kw=float(np.max(power)) if power else 0.0,
            comfort_violation_kh=violation_kh,
            comfort_violation_steps=violations,
            mean_zone_temp_c=float(np.mean(zone_temp)) if zone_temp else 0.0,
            cop_mean=float("nan"),
            parameters={"testcase": self.TESTCASE, "step_seconds": STEP_SECONDS},
            notes=[f"BOPTEST test case {self.TESTCASE} over the REST API."],
        )
