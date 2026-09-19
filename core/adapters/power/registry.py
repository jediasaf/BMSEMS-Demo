"""Pick the best available power adapter."""

from __future__ import annotations

import functools
import logging

from core.adapters.power.base import PowerSourceAdapter
from core.adapters.power.facility import FacilityPowerAdapter
from core.adapters.power.fixture import FixturePowerAdapter

log = logging.getLogger(__name__)

ADAPTER_ORDER: tuple[type[PowerSourceAdapter], ...] = (
    FacilityPowerAdapter,
    FixturePowerAdapter,
)


@functools.lru_cache(maxsize=1)
def get_power_adapter() -> PowerSourceAdapter:
    for cls in ADAPTER_ORDER:
        adapter = cls()
        if adapter.available():
            log.info("power adapter: %s (%s)", adapter.key, adapter.data_mode.value)
            return adapter
    raise RuntimeError("no power adapter available, not even the fixture")


def reset_adapter_cache() -> None:
    get_power_adapter.cache_clear()
