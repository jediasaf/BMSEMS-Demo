"""Pick the best available building adapter.

Order matters: a real source always wins, and the fixture is the last resort so
the application never shows an empty state.
"""

from __future__ import annotations

import functools
import logging

from core.adapters.building.base import BuildingSourceAdapter
from core.adapters.building.fixture import FixtureBuildingAdapter
from core.adapters.building.power_laws import PowerLawsBuildingAdapter
from core.adapters.building.technopole import TechnopoleAdapter

log = logging.getLogger(__name__)

#: Highest priority first.
ADAPTER_ORDER: tuple[type[BuildingSourceAdapter], ...] = (
    TechnopoleAdapter,
    PowerLawsBuildingAdapter,
    FixtureBuildingAdapter,
)


@functools.lru_cache(maxsize=1)
def get_building_adapter() -> BuildingSourceAdapter:
    for cls in ADAPTER_ORDER:
        adapter = cls()
        if adapter.available():
            log.info("building adapter: %s (%s)", adapter.key, adapter.data_mode.value)
            return adapter
    raise RuntimeError("no building adapter available, not even the fixture")


def reset_adapter_cache() -> None:
    """Used by tests and by the demo-reset endpoint."""
    get_building_adapter.cache_clear()
