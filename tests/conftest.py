"""Shared fixtures.

Tests run against whatever the adapter registry resolves: real processed data
when it is present, the fixture adapters otherwise. Tests that genuinely need
real data are skipped rather than failed, so a fresh clone without
``data/processed`` still gets a meaningful signal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.adapters.building import get_building_adapter  # noqa: E402
from core.adapters.building.power_laws import processed_data_available  # noqa: E402
from core.adapters.power import get_power_adapter  # noqa: E402
from core.common import paths  # noqa: E402


@pytest.fixture(scope="session")
def building_adapter():
    return get_building_adapter()


@pytest.fixture(scope="session")
def power_adapter():
    return get_power_adapter()


@pytest.fixture(scope="session")
def has_real_data() -> bool:
    return processed_data_available()


@pytest.fixture(scope="session")
def has_models() -> bool:
    return paths.MODELS_DIR.exists() and any(paths.MODELS_DIR.glob("*.joblib"))


requires_real_data = pytest.mark.skipif(
    not processed_data_available(),
    reason="processed dataset not present; run scripts/prepare_data.py",
)

requires_models = pytest.mark.skipif(
    not (paths.MODELS_DIR.exists() and any(paths.MODELS_DIR.glob("*.joblib"))),
    reason="no trained models; run scripts/train_models.py",
)
