"""Feature construction, leakage control, forecasting and anomaly detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.enums import AnomalyKind, Severity
from core.models.anomaly import AnomalyConfig, ResidualAnomalyDetector
from core.models.features import (
    LAG_STEPS,
    MAX_LAG_DAYS,
    MIN_LAG_STEPS,
    STEPS_PER_DAY,
    FeatureBuilder,
    build_features,
)
from core.models.forecast import LOWER_Q, NOMINAL_COVERAGE, UPPER_Q, _conformalise
from tests.conftest import requires_models, requires_real_data


def _frame(n: int = STEPS_PER_DAY * 20, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2017-01-01", periods=n, freq="15min", name="timestamp")
    hours = index.hour + index.minute / 60.0
    occupancy = np.clip(np.sin(np.pi * (hours - 7) / 11), 0, 1)
    outdoor = 12 + 8 * np.sin(2 * np.pi * (hours - 9) / 24)
    load = 20 + 55 * occupancy + 0.9 * np.clip(outdoor - 18, 0, None)
    load = load * (1 + rng.normal(0, 0.02, n))
    return pd.DataFrame(
        {
            "load_kw": load,
            "outdoor_temp_c": outdoor,
            "is_day_off": index.dayofweek >= 5,
            "is_holiday": False,
        },
        index=index,
    )


# -- features --------------------------------------------------------------
def test_no_feature_uses_a_lag_shorter_than_a_day() -> None:
    assert MIN_LAG_STEPS == STEPS_PER_DAY
    assert all(lag >= MIN_LAG_STEPS for lag in LAG_STEPS)


def test_lag_depth_respects_the_source_block_budget() -> None:
    """Every usable stretch of the source is a contiguous 10-day block."""
    assert max(LAG_STEPS) <= MAX_LAG_DAYS * STEPS_PER_DAY


def test_features_do_not_leak_the_target() -> None:
    """Perturbing only the final value must not change any earlier feature row.

    This is the property that matters: a feature that reads the present would
    move a row it has no business moving.
    """
    frame = _frame()
    baseline = build_features(frame)
    tampered = frame.copy()
    tampered.iloc[-1, tampered.columns.get_loc("load_kw")] *= 5.0
    after = build_features(tampered)
    pd.testing.assert_frame_equal(baseline.iloc[:-1], after.iloc[:-1])


def test_features_are_finite_once_warmed_up() -> None:
    features = build_features(_frame())
    warm = features.iloc[max(LAG_STEPS) + STEPS_PER_DAY :]
    assert warm.notna().all().all()
    assert np.isfinite(warm.to_numpy()).all()


def test_degree_hours_respond_to_the_base_temperature() -> None:
    frame = _frame()
    cold = build_features(frame, base_temperature_c=25.0)
    warm = build_features(frame, base_temperature_c=10.0)
    assert cold["hdh"].mean() > warm["hdh"].mean()
    assert cold["cdh"].mean() < warm["cdh"].mean()


def test_builder_reproduces_the_trained_column_order() -> None:
    builder = FeatureBuilder()
    trained = builder.fit_transform(_frame())
    builder2 = FeatureBuilder()
    builder2.columns = list(trained.columns)
    served = builder2.transform(_frame())
    assert list(served.columns) == list(trained.columns)


# -- conformal calibration -------------------------------------------------
def test_conformal_offset_restores_coverage() -> None:
    rng = np.random.default_rng(3)
    actual = rng.normal(100, 12, 4000)
    # Intentionally over-confident band.
    lower, upper = actual * 0 + 97.0, actual * 0 + 103.0
    raw = float(np.mean((actual >= lower) & (actual <= upper)))
    offset = _conformalise(actual, lower, upper, coverage=NOMINAL_COVERAGE)
    calibrated = float(np.mean((actual >= lower - offset) & (actual <= upper + offset)))
    assert raw < NOMINAL_COVERAGE
    assert calibrated >= NOMINAL_COVERAGE - 0.02
    assert offset > 0


def test_conformal_offset_is_zero_for_an_already_wide_band() -> None:
    actual = np.full(500, 50.0)
    offset = _conformalise(actual, np.full(500, 0.0), np.full(500, 100.0))
    assert offset == 0.0


def test_quantiles_bracket_the_median() -> None:
    assert LOWER_Q < 0.5 < UPPER_Q


# -- anomaly detection -----------------------------------------------------
def _scored(actual: pd.Series, expected: pd.Series, reference_end=None):
    return ResidualAnomalyDetector(AnomalyConfig()).score(
        actual, expected, reference_end=reference_end
    )


def test_clean_residuals_raise_nothing() -> None:
    frame = _frame()
    expected = frame["load_kw"].rolling(3, center=True, min_periods=1).mean()
    detector = ResidualAnomalyDetector()
    stats = detector.score(frame["load_kw"], expected, reference_end=frame.index[500])
    insights = detector.detect(stats, asset_id="t")
    assert all(i.severity is not Severity.CRITICAL for i in insights)


def test_a_sustained_excursion_is_detected() -> None:
    frame = _frame()
    expected = frame["load_kw"].copy()
    actual = frame["load_kw"].copy()
    window = slice(1200, 1240)
    actual.iloc[window] = actual.iloc[window] + 45.0
    detector = ResidualAnomalyDetector()
    stats = detector.score(actual, expected, reference_end=frame.index[1100])
    insights = detector.detect(stats, asset_id="t")
    assert insights
    hit = [i for i in insights if abs(i.robust_z or 0) > 3.5]
    assert hit
    assert hit[0].kind in {AnomalyKind.OVER_CONSUMPTION, AnomalyKind.SENSOR_DRIFT}
    assert 0.5 <= hit[0].confidence <= 0.99


def test_a_single_spike_is_not_an_alarm() -> None:
    """One sample is telemetry far more often than it is plant."""
    frame = _frame()
    expected = frame["load_kw"].copy()
    actual = frame["load_kw"].copy()
    actual.iloc[1500] += 200.0
    detector = ResidualAnomalyDetector()
    stats = detector.score(actual, expected, reference_end=frame.index[1400])
    insights = detector.detect(stats, asset_id="t")
    assert not [i for i in insights if pd.Timestamp(i.timestamp) == frame.index[1500]]


def test_a_tiny_deviation_is_not_material() -> None:
    frame = _frame()
    expected = frame["load_kw"].copy()
    actual = expected + 0.2  # below the absolute floor
    stats = _scored(actual, expected, reference_end=frame.index[500])
    assert not stats.frame["is_anomalous"].any()


def test_reference_baseline_does_not_absorb_a_window_long_fault() -> None:
    """The bug this design exists to prevent.

    A trailing rolling baseline adapts to a fault that lasts longer than its
    window, and stops flagging it. The reference-period baseline must not.
    """
    frame = _frame()
    expected = frame["load_kw"].copy()
    actual = frame["load_kw"].copy()
    fault = slice(1400, len(actual))  # runs to the end, far longer than the window
    actual.iloc[fault] = actual.iloc[fault] * 1.6

    detector = ResidualAnomalyDetector()
    rolling = detector.score(actual, expected)
    referenced = detector.score(actual, expected, reference_end=frame.index[1300])

    late = slice(1700, len(actual))
    assert referenced.frame["is_anomalous"].iloc[late].sum() > (
        rolling.frame["is_anomalous"].iloc[late].sum()
    )
    assert referenced.basis.startswith("reference-period")


def test_flatline_is_classified_as_a_stuck_point() -> None:
    frame = _frame()
    expected = frame["load_kw"].copy()
    actual = frame["load_kw"].copy()
    actual.iloc[1200:1260] = 42.0
    detector = ResidualAnomalyDetector()
    stats = detector.score(actual, expected, reference_end=frame.index[1100])
    insights = detector.detect(stats, asset_id="t")
    kinds = {i.kind for i in insights}
    assert kinds & {AnomalyKind.FLATLINE, AnomalyKind.UNDER_CONSUMPTION}


def test_insight_ids_are_stable() -> None:
    frame = _frame()
    expected = frame["load_kw"].copy()
    actual = frame["load_kw"].copy()
    actual.iloc[1200:1240] += 45.0
    detector = ResidualAnomalyDetector()
    first = detector.detect(
        detector.score(actual, expected, reference_end=frame.index[1100]), asset_id="t"
    )
    second = detector.detect(
        detector.score(actual, expected, reference_end=frame.index[1100]), asset_id="t"
    )
    assert [i.insight_id for i in first] == [i.insight_id for i in second]


def test_insights_never_claim_a_cause() -> None:
    frame = _frame()
    expected = frame["load_kw"].copy()
    actual = frame["load_kw"].copy()
    actual.iloc[1200:1240] += 45.0
    detector = ResidualAnomalyDetector()
    insights = detector.detect(
        detector.score(actual, expected, reference_end=frame.index[1100]), asset_id="t"
    )
    for insight in insights:
        assert insight.possible_causes, "a finding must offer possible causes"
        assert insight.recommended_next_step
        assert insight.expected is not None and insight.observed is not None


# -- trained models --------------------------------------------------------
@requires_models
@requires_real_data
def test_trained_models_beat_their_own_baseline_or_are_gated(building_adapter) -> None:
    """Either the model is better than naive, or the serving layer refuses it."""
    from apps.api.services.expected import MIN_SKILL_PCT, ExpectedLoadService

    service = ExpectedLoadService()
    for site in building_adapter.list_sites():
        frame = building_adapter.load_frame(site.site_id)
        expected = service.expected(frame, asset_id=site.site_id)
        if expected.served_by == "model":
            assert expected.model is not None
            assert (
                expected.model.metrics.backtest.skill_vs_baseline_pct > MIN_SKILL_PCT
            ), f"site {site.site_id} served a model that failed its own gate"
        else:
            assert "seasonal-naive" in expected.gate_reason.lower()


@requires_models
@requires_real_data
def test_predictions_are_absent_rather_than_guessed(building_adapter) -> None:
    """Warm-up rows must come back NaN, not silently filled."""
    from core.models.forecast import load_forecaster

    forecaster = load_forecaster()
    site = building_adapter.list_sites()[0]
    if not forecaster.has_model(site.site_id):
        pytest.skip("no model for this site")
    frame = building_adapter.load_frame(site.site_id)
    model = forecaster.for_asset(site.site_id)
    predictions = forecaster.predict(model, frame)
    assert predictions["prediction"].isna().iloc[0]
    assert predictions["prediction"].notna().any()
    complete = predictions.dropna()
    assert (complete["lower"] <= complete["prediction"] + 1e-9).all()
    assert (complete["upper"] >= complete["prediction"] - 1e-9).all()
