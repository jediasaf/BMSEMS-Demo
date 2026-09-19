"""Feature engineering for the load forecaster.

**Leakage rule, enforced by construction:** every feature is either a calendar
value, a weather value, or a lag of the target no shorter than
``MIN_LAG_STEPS``. With ``MIN_LAG_STEPS`` set to one day, a forecast issued at
midnight for any hour of the following day uses only information that existed
when it was issued. Nothing here reads the target at or after the stamp it is
predicting.

Weather is treated as a *forecast input*: in production this is the vendor
weather forecast; on historical replay it is the recorded observation. That
substitution is stated in the model card and in provenance rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

STEPS_PER_HOUR = 4
STEPS_PER_DAY = 96
STEPS_PER_WEEK = STEPS_PER_DAY * 7

#: Shortest lag any feature may use, in 15-minute steps. One day.
MIN_LAG_STEPS = STEPS_PER_DAY

#: Lag depth is bounded by the source: every usable stretch of this dataset is
#: a contiguous 10-day block, so a feature reaching back more than 7 days would
#: be unavailable for most of any window we could replay. See
#: ``docs/modelling.md`` for the lookback/replay budget.
MAX_LAG_DAYS = 5

LAG_STEPS: tuple[int, ...] = (
    STEPS_PER_DAY,          # same time yesterday
    STEPS_PER_DAY + 1,      # +15 min, smooths a one-step phase shift
    STEPS_PER_DAY * 2,
    STEPS_PER_DAY * 3,
    STEPS_PER_DAY * 4,
    STEPS_PER_DAY * 5,
)

ROLLING_WINDOWS: tuple[int, ...] = (STEPS_PER_DAY, STEPS_PER_DAY * 3, STEPS_PER_DAY * 5)


@dataclass(frozen=True)
class FeatureSpec:
    """The feature contract, exposed to the UI for the explanation drawer."""

    names: tuple[str, ...]
    labels: dict[str, str] = field(default_factory=dict)

    def label(self, name: str) -> str:
        return self.labels.get(name, name)


def _calendar(index: pd.DatetimeIndex) -> pd.DataFrame:
    minutes = index.hour * 60 + index.minute
    frac = minutes / 1440.0
    return pd.DataFrame(
        {
            "tod_sin": np.sin(2 * np.pi * frac),
            "tod_cos": np.cos(2 * np.pi * frac),
            "dow_sin": np.sin(2 * np.pi * index.dayofweek / 7.0),
            "dow_cos": np.cos(2 * np.pi * index.dayofweek / 7.0),
            "doy_sin": np.sin(2 * np.pi * index.dayofyear / 365.25),
            "doy_cos": np.cos(2 * np.pi * index.dayofyear / 365.25),
            "hour": index.hour.astype(float),
            "dayofweek": index.dayofweek.astype(float),
            "is_weekend": (index.dayofweek >= 5).astype(float),
        },
        index=index,
    )


def build_features(
    frame: pd.DataFrame,
    *,
    target: str = "load_kw",
    base_temperature_c: float | None = 18.0,
) -> pd.DataFrame:
    """Build the model matrix. ``frame`` must be on the strict 15-minute grid."""
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("build_features expects a DatetimeIndex")
    index = frame.index
    out = _calendar(index)

    if "is_day_off" in frame:
        out["is_day_off"] = frame["is_day_off"].astype(float).to_numpy()
    else:
        out["is_day_off"] = (index.dayofweek >= 5).astype(float)
    out["is_holiday"] = (
        frame["is_holiday"].astype(float).to_numpy() if "is_holiday" in frame else 0.0
    )
    # A day that is "off" only because of a public holiday behaves like a
    # weekend even on a Tuesday; give the model that interaction directly.
    out["is_closed"] = np.clip(out["is_day_off"] + out["is_holiday"], 0.0, 1.0)

    if "outdoor_temp_c" in frame:
        temp = frame["outdoor_temp_c"].astype(float)
        out["outdoor_temp_c"] = temp.to_numpy()
        out["temp_lag_1h"] = temp.shift(STEPS_PER_HOUR).to_numpy()
        out["temp_roll_6h"] = temp.rolling(6 * STEPS_PER_HOUR, min_periods=1).mean().to_numpy()
        out["temp_roll_24h"] = temp.rolling(STEPS_PER_DAY, min_periods=1).mean().to_numpy()
        if base_temperature_c is not None:
            # Degree-hours around the site's published base temperature: the
            # standard way to linearise a building's thermal response.
            out["hdh"] = np.clip(base_temperature_c - temp.to_numpy(), 0, None)
            out["cdh"] = np.clip(temp.to_numpy() - base_temperature_c, 0, None)
            out["hdh_roll_24h"] = (
                pd.Series(out["hdh"], index=index).rolling(STEPS_PER_DAY, min_periods=1).mean()
            )
            out["cdh_roll_24h"] = (
                pd.Series(out["cdh"], index=index).rolling(STEPS_PER_DAY, min_periods=1).mean()
            )

    series = frame[target].astype(float)
    for lag in LAG_STEPS:
        if lag < MIN_LAG_STEPS:  # pragma: no cover - guarded by construction
            raise ValueError(f"lag {lag} is shorter than the leakage floor {MIN_LAG_STEPS}")
        if lag > MAX_LAG_DAYS * STEPS_PER_DAY:  # pragma: no cover
            raise ValueError(f"lag {lag} exceeds the {MAX_LAG_DAYS}-day lookback budget")
        out[f"lag_{lag}"] = series.shift(lag).to_numpy()
    for window in ROLLING_WINDOWS:
        shifted = series.shift(MIN_LAG_STEPS)
        out[f"roll_mean_{window}"] = shifted.rolling(window, min_periods=window // 4).mean()
        out[f"roll_std_{window}"] = shifted.rolling(window, min_periods=window // 4).std()
    # Yesterday's profile at this time relative to yesterday's whole-day mean:
    # separates "the building ran hot all day" from "this hour was unusual".
    day_mean = series.shift(MIN_LAG_STEPS).rolling(STEPS_PER_DAY, min_periods=24).mean()
    out["lag_1d_ratio"] = out[f"lag_{STEPS_PER_DAY}"] / day_mean.replace(0, np.nan)

    out.index.name = "timestamp"
    return out


FEATURE_LABELS: dict[str, str] = {
    "tod_sin": "Time of day",
    "tod_cos": "Time of day",
    "dow_sin": "Day of week",
    "dow_cos": "Day of week",
    "doy_sin": "Season",
    "doy_cos": "Season",
    "hour": "Hour of day",
    "dayofweek": "Day of week",
    "is_weekend": "Weekend",
    "is_day_off": "Scheduled day off",
    "is_holiday": "Public holiday",
    "is_closed": "Building closed",
    "outdoor_temp_c": "Outdoor air temperature",
    "temp_lag_1h": "Outdoor temperature, 1 h earlier",
    "temp_roll_6h": "Outdoor temperature, 6 h mean",
    "temp_roll_24h": "Outdoor temperature, 24 h mean",
    "hdh": "Heating degree-hours",
    "cdh": "Cooling degree-hours",
    "hdh_roll_24h": "Heating degree-hours, 24 h mean",
    "cdh_roll_24h": "Cooling degree-hours, 24 h mean",
    "lag_96": "Load at this time yesterday",
    "lag_97": "Load yesterday, +15 min",
    "lag_192": "Load at this time 2 days ago",
    "lag_288": "Load at this time 3 days ago",
    "lag_384": "Load at this time 4 days ago",
    "lag_480": "Load at this time 5 days ago",
    "roll_mean_96": "Mean load, previous day",
    "roll_std_96": "Load variability, previous day",
    "roll_mean_288": "Mean load, previous 3 days",
    "roll_std_288": "Load variability, previous 3 days",
    "roll_mean_480": "Mean load, previous 5 days",
    "roll_std_480": "Load variability, previous 5 days",
    "lag_1d_ratio": "Yesterday's shape at this hour",
}


class FeatureBuilder:
    """Stateful wrapper so the trained column order is reproduced exactly."""

    def __init__(self, base_temperature_c: float | None = 18.0, target: str = "load_kw") -> None:
        self.base_temperature_c = base_temperature_c
        self.target = target
        self.columns: list[str] | None = None

    def fit_transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        features = build_features(
            frame, target=self.target, base_temperature_c=self.base_temperature_c
        )
        self.columns = list(features.columns)
        return features

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        features = build_features(
            frame, target=self.target, base_temperature_c=self.base_temperature_c
        )
        if self.columns is None:
            self.columns = list(features.columns)
        for missing in set(self.columns) - set(features.columns):
            features[missing] = np.nan
        return features[self.columns]


FEATURE_SPEC = FeatureSpec(names=tuple(FEATURE_LABELS), labels=FEATURE_LABELS)
