"""Data-quality reporting for the drawer."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.common.schemas import DataQualityReport

STEP_MINUTES = 15


def _flatline_runs(series: pd.Series, min_run: int = 4) -> int:
    values = series.to_numpy()
    if len(values) < min_run:
        return 0
    same = np.isclose(values[1:], values[:-1], equal_nan=False)
    runs, length = 0, 1
    for flag in same:
        if flag:
            length += 1
        else:
            if length >= min_run:
                runs += 1
            length = 1
    if length >= min_run:
        runs += 1
    return runs


def build_report(
    frame: pd.DataFrame,
    *,
    asset_id: str,
    units: dict[str, str],
    source_files: list[str],
    timezone: str = "UTC (naive; the publisher states no offset)",
    value_column: str = "load_kw",
) -> DataQualityReport:
    index = frame.index
    expected = (
        int((index.max() - index.min()).total_seconds() // (STEP_MINUTES * 60)) + 1
        if len(index)
        else 0
    )
    series = frame[value_column]
    actual = int(series.notna().sum())

    valid = series.dropna()
    if len(valid) >= 10:
        q1, q3 = np.percentile(valid, [25, 75])
        iqr = q3 - q1
        low, high = q1 - 3.0 * iqr, q3 + 3.0 * iqr
        outliers = int(((valid < low) | (valid > high)).sum())
        rule = f"outside [Q1 − 3·IQR, Q3 + 3·IQR] = [{low:.1f}, {high:.1f}]"
    else:
        outliers, rule = 0, "not enough data to fit an IQR rule"

    deltas = pd.Series(index).diff().dropna().dt.total_seconds() / 60.0
    sampling = float(deltas.median()) if len(deltas) else float(STEP_MINUTES)

    notes: list[str] = []
    quality_counts = frame["quality"].value_counts().to_dict() if "quality" in frame else {}
    interpolated = int(quality_counts.get("INTERPOLATED", 0))
    if interpolated:
        notes.append(
            f"{interpolated} samples ({100 * interpolated / max(len(frame), 1):.2f}%) "
            "were filled by time interpolation across gaps of at most one hour."
        )
    if "weather_quality" in frame:
        missing_weather = int((frame["weather_quality"] == "MISSING").sum())
        if missing_weather:
            notes.append(
                f"{missing_weather} samples have no nearest-station temperature; the "
                "forecaster drops those rows rather than imputing them."
            )
    notes.append(
        "Timestamps carry no timezone offset in the source. They are treated as a "
        "consistent local clock and never converted."
    )

    return DataQualityReport(
        asset_id=asset_id,
        window_start=index.min().to_pydatetime() if len(index) else pd.Timestamp(0),
        window_end=index.max().to_pydatetime() if len(index) else pd.Timestamp(0),
        expected_samples=expected,
        actual_samples=actual,
        missing_pct=round(100.0 * (1.0 - actual / max(expected, 1)), 4),
        duplicate_timestamps=int(index.duplicated().sum()),
        sampling_minutes=sampling,
        timezone=timezone,
        units=units,
        last_timestamp=index.max().to_pydatetime() if len(index) else None,
        outlier_count=outliers,
        outlier_rule=rule,
        flatline_runs=_flatline_runs(series.ffill().fillna(0.0)),
        notes=notes,
        source_files=source_files,
        extra={"quality_flags": {str(k): int(v) for k, v in quality_counts.items()}},
    )
