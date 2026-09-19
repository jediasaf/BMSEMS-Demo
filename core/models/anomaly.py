"""Residual anomaly detection.

The whole method is four lines of arithmetic, and that is the point: an
operator has to believe the alarm at 03:00. Every insight can be reduced to
"we expected X, we measured Y, that is Z robust deviations from how this
building normally misses, and here is the threshold".

    residual   = actual - expected
    centre/MAD = median and median absolute deviation of the residual
    score      = 0.6745 * (residual - centre) / MAD        (robust z)
    anomalous  = |score| > threshold, sustained for min_run steps

Median/MAD rather than mean/sigma because a handful of genuine faults must not
inflate the very band used to detect them. The sustain requirement removes
single-sample spikes, which are far more often telemetry than plant.

Where centre and MAD come from
------------------------------
Calibrated on a **reference period that ends before the period under test**,
conditioned on hour of day, and then held fixed. This matters more than it
looks. A trailing rolling baseline quietly adapts to whatever it is shown, so a
fault lasting longer than the window becomes the new normal and is never
flagged -- the failure mode that makes naive residual monitors useless in
practice. Hour-of-day conditioning is there because a building's forecast error
at 03:00 and at 14:00 are not the same random variable.

If no reference period is supplied the detector falls back to a trailing
rolling baseline, and says so in ``basis``.

Classification into ``AnomalyKind`` is rule-based on top of the score, so the
label is inspectable. No black box decides what an operator is told.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.common.schemas import FeatureContribution, Insight
from core.enums import AnomalyKind, Severity
from core.provenance import Provenance
from core.provenance.model import derived as derived_provenance

#: 0.6745 = Phi^-1(0.75); scales MAD to be comparable with a standard deviation.
MAD_TO_SIGMA = 0.6745
STEPS_PER_HOUR = 4
STEPS_PER_DAY = 96


@dataclass(frozen=True)
class AnomalyConfig:
    #: Trailing window for the fallback rolling baseline, in 15-minute steps.
    window: int = STEPS_PER_DAY * 3
    #: Minimum residuals in an hour-of-day bucket before it gets its own
    #: statistics; below this the bucket falls back to the pooled estimate.
    min_bucket: int = 40
    #: Robust-z magnitude that counts as anomalous.
    threshold: float = 3.5
    #: Consecutive steps the threshold must hold. 3 steps = 45 minutes.
    min_run: int = 3
    #: Ignore deviations smaller than this, whatever the score: a 0.2 kW miss on
    #: a quiet night is statistically large and operationally meaningless.
    min_absolute_kw: float = 2.0
    #: ... or smaller than this share of the expected value.
    min_relative: float = 0.08
    #: Lead-in inspected for drift, in steps (6 h).
    drift_run: int = STEPS_PER_HOUR * 6
    #: How far the bias must have grown across that lead-in, in MADs, before
    #: the finding is called drift rather than an event.
    drift_growth_mads: float = 1.5
    #: Identical consecutive readings that indicate a stuck sensor (1 h).
    flatline_run: int = STEPS_PER_HOUR * 4
    severity_bands: tuple[float, float, float] = (3.5, 5.0, 8.0)


@dataclass
class ResidualStats:
    """Per-timestamp detector state, returned for charting and audit."""

    frame: pd.DataFrame
    basis: str = "rolling"
    reference: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.reference is None:
            self.reference = {}

    @property
    def residual(self) -> pd.Series:
        return self.frame["residual"]

    @property
    def score(self) -> pd.Series:
        return self.frame["robust_z"]


def _runs(mask: pd.Series) -> list[tuple[int, int]]:
    """Contiguous ``True`` runs as (start, end) positional half-open pairs."""
    values = mask.to_numpy()
    if not values.any():
        return []
    padded = np.concatenate(([False], values, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(edges[0::2].tolist(), edges[1::2].tolist(), strict=True))


class ResidualAnomalyDetector:
    def __init__(self, config: AnomalyConfig | None = None) -> None:
        self.config = config or AnomalyConfig()

    # -- scoring ----------------------------------------------------------
    def _reference_stats(
        self, residual: pd.Series, reference_end: pd.Timestamp
    ) -> tuple[pd.Series, pd.Series, dict[str, float], str]:
        """Hour-of-day median and MAD of the residual, from history only."""
        history = residual[residual.index < reference_end].dropna()
        index = residual.index
        hours = pd.Series(index.hour, index=index)
        if len(history) < self.config.min_bucket:
            return (
                pd.Series(0.0, index=index),
                pd.Series(float("nan"), index=index),
                {"n_reference": float(len(history))},
                "insufficient-history",
            )

        pooled_centre = float(history.median())
        pooled_mad = float((history - pooled_centre).abs().median())

        history_hours = history.index.hour
        centre_by_hour: dict[int, float] = {}
        mad_by_hour: dict[int, float] = {}
        for hour in range(24):
            bucket = history[history_hours == hour]
            if len(bucket) >= self.config.min_bucket:
                centre = float(bucket.median())
                centre_by_hour[hour] = centre
                mad_by_hour[hour] = float((bucket - centre).abs().median())
            else:
                centre_by_hour[hour] = pooled_centre
                mad_by_hour[hour] = pooled_mad

        return (
            hours.map(centre_by_hour).astype(float),
            hours.map(mad_by_hour).astype(float),
            {
                "n_reference": float(len(history)),
                "pooled_centre": round(pooled_centre, 4),
                "pooled_mad": round(pooled_mad, 4),
                "reference_end": reference_end.isoformat(),
            },
            "reference-period, hour-of-day conditioned",
        )

    def score(
        self,
        actual: pd.Series,
        expected: pd.Series,
        reference_end: pd.Timestamp | None = None,
    ) -> ResidualStats:
        cfg = self.config
        actual = actual.astype(float)
        expected = expected.astype(float).reindex(actual.index)
        residual = actual - expected

        if reference_end is not None:
            centre, mad, reference, basis = self._reference_stats(
                residual, pd.Timestamp(reference_end)
            )
        else:
            centre = residual.rolling(cfg.window, min_periods=cfg.window // 6).median()
            mad = (residual - centre).abs().rolling(
                cfg.window, min_periods=cfg.window // 6
            ).median()
            reference, basis = {}, "trailing rolling window"

        # A perfectly modelled stretch gives MAD = 0 and an infinite score;
        # floor it on the series' own scale so quiet periods stay quiet.
        floor = float(np.nanmax([np.nanmedian(actual.abs()) * 0.01, 0.05]))
        mad = mad.clip(lower=floor)

        score = MAD_TO_SIGMA * (residual - centre) / mad
        relative = residual / expected.replace(0, np.nan)

        frame = pd.DataFrame(
            {
                "actual": actual,
                "expected": expected,
                "residual": residual,
                "centre": centre,
                "mad": mad,
                "robust_z": score,
                "relative": relative,
                "upper_band": expected + centre + mad * cfg.threshold / MAD_TO_SIGMA,
                "lower_band": expected + centre - mad * cfg.threshold / MAD_TO_SIGMA,
            }
        )
        frame["is_material"] = (residual.abs() >= cfg.min_absolute_kw) & (
            relative.abs() >= cfg.min_relative
        )
        frame["is_anomalous"] = (frame["robust_z"].abs() > cfg.threshold) & frame["is_material"]
        return ResidualStats(frame=frame, basis=basis, reference=reference)

    # -- classification ---------------------------------------------------
    def _severity(self, peak_score: float) -> Severity:
        low, mid, high = self.config.severity_bands
        magnitude = abs(peak_score)
        if magnitude >= high:
            return Severity.CRITICAL
        if magnitude >= mid:
            return Severity.HIGH
        if magnitude >= low:
            return Severity.MEDIUM
        return Severity.LOW

    @staticmethod
    def _confidence(peak_score: float, threshold: float) -> float:
        """Map |z| to 0.5..0.99. Saturating, so nothing ever reads as certain."""
        excess = max(abs(peak_score) - threshold, 0.0)
        return round(min(0.5 + 0.49 * (1.0 - np.exp(-excess / 2.5)), 0.99), 3)

    def _classify(
        self,
        window: pd.DataFrame,
        *,
        is_closed: pd.Series | None,
        context: pd.DataFrame | None = None,
        start_pos: int = 0,
    ) -> tuple[AnomalyKind, list[str]]:
        cfg = self.config
        residual = window["residual"]
        actual = window["actual"]
        mean_residual = float(residual.mean())

        unique_readings = actual.round(6).nunique()
        if unique_readings <= 1 and len(window) >= cfg.flatline_run:
            return AnomalyKind.FLATLINE, [
                "meter or sensor reporting a stuck value",
                "communication loss with the point holding the last reading",
                "plant genuinely off with a constant parasitic load",
            ]
        if actual.isna().all():
            return AnomalyKind.MISSING_DATA, [
                "gap in the source telemetry",
                "device offline during this window",
            ]

        # Drift is judged on the *run of hours before* the finding, not on the
        # finding itself: a bias that has been building for six hours is a
        # different fault from a sudden step, and the run alone cannot tell
        # them apart.
        if context is not None and start_pos >= cfg.drift_run:
            lead_in = context["residual"].iloc[start_pos - cfg.drift_run : start_pos].dropna()
            if len(lead_in) >= cfg.drift_run // 2:
                one_sided = (lead_in > 0).mean() if mean_residual > 0 else (lead_in < 0).mean()
                slope = float(np.polyfit(range(len(lead_in)), lead_in.to_numpy(), 1)[0])
                # The bias must have grown by at least one MAD across the
                # lead-in. Without that scale test, ordinary autocorrelation in
                # the residual reads as drift and every finding gets the label.
                growth = abs(slope) * len(lead_in)
                scale = float(window["mad"].median())
                if (
                    one_sided > 0.92
                    and growth >= cfg.drift_growth_mads * scale
                    and np.sign(slope) == np.sign(mean_residual)
                ):
                    return AnomalyKind.SENSOR_DRIFT, [
                        "measurement drift or a mis-scaled point",
                        "a step change in connected load not yet learned by the model",
                        "sustained equipment inefficiency",
                    ]

        closed = bool(is_closed.loc[window.index].mean() > 0.5) if is_closed is not None else False
        if closed and mean_residual > 0:
            return AnomalyKind.OFF_HOURS_LOAD, [
                "plant left running outside the occupancy schedule",
                "schedule override or holiday calendar not applied",
                "unusual out-of-hours occupancy",
            ]
        if mean_residual > 0:
            return AnomalyKind.OVER_CONSUMPTION, [
                "higher thermal load than the conditions imply",
                "equipment operating outside its expected schedule",
                "control loop hunting or simultaneous heating and cooling",
            ]
        return AnomalyKind.UNDER_CONSUMPTION, [
            "plant unavailable or tripped",
            "occupancy lower than the calendar implies",
            "partial metering loss",
        ]

    # -- insights ---------------------------------------------------------
    def detect(
        self,
        stats: ResidualStats,
        *,
        asset_id: str,
        module: str = "BMS",
        metric: str = "load_kw",
        unit: str = "kW",
        zone_id: str | None = None,
        is_closed: pd.Series | None = None,
        provenance: Provenance | None = None,
        max_insights: int = 25,
    ) -> list[Insight]:
        cfg = self.config
        frame = stats.frame
        prov = provenance or derived_provenance(
            "residual_anomaly",
            field=metric,
            units=unit,
            processing=(
                "robust z of the forecast residual against an hour-of-day "
                f"median/MAD baseline ({stats.basis}); |z| > {cfg.threshold} "
                f"sustained for {cfg.min_run} steps"
            ),
            assumptions=[
                f"material deviation floor: {cfg.min_absolute_kw} {unit} and "
                f"{cfg.min_relative:.0%} of expected",
                "MAD floored at 1% of the median level to avoid infinite scores",
            ],
        )

        insights: list[Insight] = []
        for start, end in _runs(frame["is_anomalous"].fillna(False)):
            if end - start < cfg.min_run:
                continue
            window = frame.iloc[start:end]
            peak_idx = window["robust_z"].abs().idxmax()
            peak = window.loc[peak_idx]
            kind, causes = self._classify(
                window, is_closed=is_closed, context=frame, start_pos=start
            )
            severity = self._severity(float(peak["robust_z"]))
            duration_min = int((end - start) * 15)

            observed = float(peak["actual"])
            expected = float(peak["expected"])
            deviation = observed - expected
            insight_id = "ins-" + hashlib.sha1(
                f"{asset_id}|{metric}|{window.index[0]}|{kind.value}".encode()
            ).hexdigest()[:10]

            evidence = [
                FeatureContribution(
                    feature="robust_z",
                    label="Robust deviation score",
                    contribution=round(float(peak["robust_z"]), 2),
                    direction="up" if peak["robust_z"] > 0 else "down",
                    detail=f"threshold ±{cfg.threshold}",
                ),
                FeatureContribution(
                    feature="residual",
                    label="Residual (measured − expected)",
                    contribution=round(deviation, 2),
                    direction="up" if deviation > 0 else "down",
                    detail=f"{unit}",
                ),
                FeatureContribution(
                    feature="duration",
                    label="Sustained for",
                    contribution=float(duration_min),
                    direction="flat",
                    detail=f"{duration_min} min ({end - start} intervals)",
                ),
                FeatureContribution(
                    feature="mad",
                    label="Normal miss for this asset (MAD)",
                    contribution=round(float(peak["mad"]), 3),
                    direction="flat",
                    detail=f"rolling {cfg.window // STEPS_PER_DAY}-day median absolute deviation",
                ),
            ]

            pct = (deviation / expected * 100.0) if expected not in (0, None) else None
            insights.append(
                Insight(
                    insight_id=insight_id,
                    timestamp=peak_idx.to_pydatetime(),
                    asset_id=asset_id,
                    zone_id=zone_id,
                    module="BMS" if module == "BMS" else "EMS",
                    kind=kind,
                    severity=severity,
                    metric=metric,
                    unit=unit,
                    observed=round(observed, 3),
                    expected=round(expected, 3),
                    deviation=round(deviation, 3),
                    deviation_pct=round(pct, 2) if pct is not None else None,
                    robust_z=round(float(peak["robust_z"]), 3),
                    threshold=cfg.threshold,
                    confidence=self._confidence(float(peak["robust_z"]), cfg.threshold),
                    title=_title(kind, deviation, unit),
                    description=(
                        f"Measured {observed:,.1f} {unit} against an expected "
                        f"{expected:,.1f} {unit} "
                        f"({deviation:+,.1f} {unit}"
                        + (f", {pct:+.0f}%" if pct is not None else "")
                        + f"). Deviation held for {duration_min} minutes at "
                        f"{abs(float(peak['robust_z'])):.1f}× this asset's normal "
                        "forecast miss."
                    ),
                    possible_causes=causes,
                    recommended_next_step=_next_step(kind),
                    provenance=prov,
                    evidence=evidence,
                )
            )

        insights.sort(key=lambda i: (abs(i.robust_z or 0.0)), reverse=True)
        return insights[:max_insights]


def _title(kind: AnomalyKind, deviation: float, unit: str) -> str:
    titles = {
        AnomalyKind.OVER_CONSUMPTION: f"Consumption {deviation:+,.0f} {unit} above expected",
        AnomalyKind.UNDER_CONSUMPTION: f"Consumption {deviation:+,.0f} {unit} below expected",
        AnomalyKind.OFF_HOURS_LOAD: f"Out-of-hours load {deviation:+,.0f} {unit} above expected",
        AnomalyKind.FLATLINE: "Reading held constant — possible stuck point",
        AnomalyKind.SENSOR_DRIFT: "Sustained one-sided deviation — possible drift",
        AnomalyKind.MISSING_DATA: "Telemetry gap",
        AnomalyKind.PEAK_EXCURSION: f"Peak excursion {deviation:+,.0f} {unit}",
    }
    return titles[kind]


def _next_step(kind: AnomalyKind) -> str:
    steps = {
        AnomalyKind.OVER_CONSUMPTION: (
            "Check HVAC plant status and zone setpoints over this window before "
            "attributing the deviation to occupancy."
        ),
        AnomalyKind.UNDER_CONSUMPTION: (
            "Confirm the plant is available and that no meter channel is missing."
        ),
        AnomalyKind.OFF_HOURS_LOAD: (
            "Review the occupancy schedule and any active overrides for this period."
        ),
        AnomalyKind.FLATLINE: "Verify the point is live and the device is communicating.",
        AnomalyKind.SENSOR_DRIFT: (
            "Compare against a neighbouring point and check the last calibration."
        ),
        AnomalyKind.MISSING_DATA: "Check the data path from the device to the historian.",
        AnomalyKind.PEAK_EXCURSION: "Identify which feeder contributed the excursion.",
    }
    return steps[kind]


def summarise(insights: list[Insight]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for insight in insights:
        counts[insight.severity.value] = counts.get(insight.severity.value, 0) + 1
    return counts
