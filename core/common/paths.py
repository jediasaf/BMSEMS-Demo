"""Filesystem layout, resolved once."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("ECOTWIN_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FIXTURES_DIR = DATA_DIR / "fixtures"
MODELS_DIR = REPO_ROOT / "models"
DEMO_DIR = REPO_ROOT / "demo"

SELECTION_JSON = PROCESSED_DIR / "selection.json"
LOAD_PARQUET = PROCESSED_DIR / "load_15min.parquet"
WEATHER_PARQUET = PROCESSED_DIR / "weather_15min.parquet"
HOLIDAYS_PARQUET = PROCESSED_DIR / "holidays.parquet"
SITE_PROFILES_JSON = PROCESSED_DIR / "site_profiles.json"
