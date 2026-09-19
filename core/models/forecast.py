"""Day-ahead load forecasting with LightGBM.

One model family, deliberately. The interesting engineering here is not the
learner, it is (a) the leakage discipline in ``features.py``, (b) an honest
time-based split, and (c) a calibrated interval rather than a bare point
forecast, because every downstream decision -- anomaly thresholds, peak risk,
setpoint proposals -- is a decision under uncertainty.

Intervals come from two extra LightGBM boosters trained on the pinball loss at
the 10th and 90th percentile, then **conformalised** (Romano et al., 2019):
a held-out calibration split fixes a single offset that restores the nominal
coverage the raw quantile heads lose under distribution shift. The result has
a finite-sample marginal-coverage guarantee, and the card reports the coverage
actually achieved on a third split the calibration never saw -- so an
over-confident band is visible instead of assumed.

Splits are strictly chronological: train | calibrate | test. When a ``cutoff``
is supplied -- and the training script always supplies the first instant of the
demo window -- everything at or after it is held out entirely. The replay the
demo shows is therefore genuinely out-of-sample, which is the only version of
this claim worth making in an interview.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from core.common import paths
from core.models.features import FeatureBuilder, FEATURE_LABELS

log = logging.getLogger(__name__)

DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "regression",
    "metric": "l1",
    "learning_rate": 0.05,
    "num_leaves": 48,
    "min_data_in_leaf": 40,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "num_boost_round": 500,
    "verbosity": -1,
    "seed": 42,
    "deterministic": True,
}

#: Naive references the learner is scored against. The *best* of these is the
#: baseline, so the reported skill is never flattered by a weak straw man.
BASELINE_FEATURES = ("lag_96", "lag_288", "lag_480")

LOWER_Q = 0.1
UPPER_Q = 0.9
NOMINAL_COVERAGE = UPPER_Q - LOWER_Q
#: Chronological split: the last 20% is never seen by training or calibration.
TRAIN_FRACTION = 0.6
CALIBRATION_FRACTION = 0.2
#: With a cutoff, the pre-cutoff history splits fit | calibrate | backtest.
FIT_FRACTION_OF_HISTORY = 0.6
CALIB_FRACTION_OF_HISTORY = 0.2


def _conformalise(
    actual: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    coverage: float = NOMINAL_COVERAGE,
) -> float:
    """Conformalised quantile regression offset (Romano, Patterson & Candes, 2019).

    The nonconformity score of a calibration point is how far outside the raw
    interval it fell (negative when comfortably inside). Widening both edges by
    the ``coverage`` quantile of those scores gives marginal coverage of at
    least ``coverage`` on exchangeable data, with no assumption about the
    residual distribution. Time series are not exchangeable, which is why the
    achieved coverage is then measured on a later split rather than claimed.
    """
    if len(actual) == 0:
        return 0.0
    scores = np.maximum(lower - actual, actual - upper)
    n = len(scores)
    # Finite-sample correction: the ceil((n+1)*coverage)-th order statistic.
    rank = min(int(np.ceil((n + 1) * coverage)), n)
    offset = float(np.sort(scores)[rank - 1])
    return max(offset, 0.0)


@dataclass
class SplitMetrics:
    """Performance on one evaluation split."""

    label: str
    n: int
    start: str
    end: str
    mae_kw: float
    rmse_kw: float
    mape_pct: float
    #: Weighted APE: sum|e| / sum|y|. Unlike MAPE it does not explode when the
    #: series legitimately passes through zero, which several sites do.
    wape_pct: float
    r2: float
    #: MAE of the strongest naive reference; the bar the tree must clear.
    baseline_mae_kw: float
    baseline_name: str
    skill_vs_baseline_pct: float
    interval_coverage_pct: float
    raw_interval_coverage_pct: float
    mean_interval_width_kw: float
    interval_target_pct: float = NOMINAL_COVERAGE * 100.0


@dataclass
class ForecastMetrics:
    """Held-out performance. Written into the model card and shown in the UI.

    Two evaluations, because they answer different questions:

    ``backtest`` -- a full chronological holdout inside the training history.
    Large enough for the numbers to mean something; this is the model quality.

    ``live`` -- everything at or after the cutoff, i.e. the window the demo
    actually replays. Usually small, so it is reported as evidence rather than
    as a performance claim.
    """

    n_train: int
    n_calib: int
    train_start: str
    train_end: str
    calib_start: str
    calib_end: str
    conformal_offset_kw: float
    backtest: SplitMetrics
    live: SplitMetrics | None = None

    @property
    def headline(self) -> SplitMetrics:
        return self.backtest


@dataclass
class ForecastModel:
    """A trained per-asset forecaster plus everything needed to explain it."""

    model_id: str
    asset_id: str
    target: str
    unit: str
    feature_columns: list[str]
    base_temperature_c: float | None
    metrics: ForecastMetrics
    feature_importance: dict[str, float] = field(default_factory=dict)
    trained_at: str = ""
    cutoff: str | None = None
    source_key: str = "power_laws_forecasting"
    notes: list[str] = field(default_factory=list)
    booster: Any = None
    booster_lower: Any = None
    booster_upper: Any = None
    #: Additive widening applied to both interval edges (kW). See ``_conformalise``.
    conformal_offset: float = 0.0

    def top_features(self, n: int = 6) -> list[tuple[str, str, float]]:
        ranked = sorted(self.feature_importance.items(), key=lambda kv: kv[1], reverse=True)
        return [(k, FEATURE_LABELS.get(k, k), v) for k, v in ranked[:n]]

    def card(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "asset_id": self.asset_id,
            "target": self.target,
            "unit": self.unit,
            "family": "LightGBM gradient-boosted trees",
            "trained_at": self.trained_at,
            "training_cutoff": self.cutoff,
            "n_features": len(self.feature_columns),
            "metrics": asdict(self.metrics),
            "conformal_offset": round(self.conformal_offset, 4),
            "top_features": [
                {"feature": k, "label": label, "importance": round(v, 4)}
                for k, label, v in self.top_features(10)
            ],
            "notes": self.notes,
            "interval_method": (
                f"LightGBM pinball loss at q={LOWER_Q} and q={UPPER_Q}, conformalised "
                f"on a held-out calibration split (offset {self.conformal_offset:.2f} "
                f"{self.unit}); coverage reported on a further unseen test split"
            ),
            "leakage_control": (
                "every feature is calendar, weather, or a lag of at least 24 h of "
                "the target; split is by time, never shuffled"
            ),
        }


class LoadForecaster:
    """Trains and serves the per-asset forecasters."""

    def __init__(self, models_dir: Path | None = None) -> None:
        self.models_dir = models_dir or paths.MODELS_DIR
        self._cache: dict[str, ForecastModel] = {}

    # -- training ---------------------------------------------------------
    def train(
        self,
        frame: pd.DataFrame,
        *,
        asset_id: str,
        target: str = "load_kw",
        unit: str = "kW",
        base_temperature_c: float | None = 18.0,
        params: dict[str, Any] | None = None,
        notes: list[str] | None = None,
        cutoff: pd.Timestamp | None = None,
    ) -> ForecastModel:
        builder = FeatureBuilder(base_temperature_c=base_temperature_c, target=target)
        features = builder.fit_transform(frame)
        y = frame[target].astype(float)

        usable = features.dropna(how="any").index.intersection(y.dropna().index)
        if len(usable) < 2000:
            raise ValueError(
                f"asset {asset_id}: only {len(usable)} usable rows after feature "
                "construction; need at least 2000"
            )
        features = features.loc[usable]
        y = y.loc[usable]

        # Chronological split. Shuffling here would leak tomorrow into today
        # and make every metric below meaningless.
        n = len(usable)
        if cutoff is not None:
            n_history = int((features.index < pd.Timestamp(cutoff)).sum())
            if n_history < 2000:
                raise ValueError(
                    f"asset {asset_id}: only {n_history} usable rows before the "
                    f"cutoff {cutoff}; cannot train on history alone"
                )
            fit_end = int(n_history * FIT_FRACTION_OF_HISTORY)
            calib_end = int(n_history * (FIT_FRACTION_OF_HISTORY + CALIB_FRACTION_OF_HISTORY))
            backtest_slice = slice(calib_end, n_history)
            live_slice: slice | None = slice(n_history, n)
        else:
            fit_end = int(n * TRAIN_FRACTION)
            calib_end = int(n * (TRAIN_FRACTION + CALIBRATION_FRACTION))
            backtest_slice = slice(calib_end, n)
            live_slice = None

        x_fit, y_fit = features.iloc[:fit_end], y.iloc[:fit_end]
        x_calib, y_calib = features.iloc[fit_end:calib_end], y.iloc[fit_end:calib_end]
        x_back, y_back = features.iloc[backtest_slice], y.iloc[backtest_slice]
        if len(x_back) < 500:
            raise ValueError(
                f"asset {asset_id}: backtest split has only {len(x_back)} rows"
            )

        merged = {**DEFAULT_PARAMS, **(params or {})}
        rounds = int(merged.pop("num_boost_round"))
        fit_set = lgb.Dataset(x_fit, label=y_fit, free_raw_data=False)
        # Early stopping watches the calibration split; the backtest and live
        # splits stay untouched by every fitting decision, including when to stop.
        watch_set = lgb.Dataset(x_calib, label=y_calib, reference=fit_set, free_raw_data=False)
        booster = lgb.train(
            merged,
            fit_set,
            num_boost_round=rounds,
            valid_sets=[watch_set],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
        )

        quantile_params = {**merged, "objective": "quantile", "metric": "quantile"}
        boosters: dict[str, lgb.Booster] = {}
        for name, alpha in (("lower", LOWER_Q), ("upper", UPPER_Q)):
            boosters[name] = lgb.train(
                {**quantile_params, "alpha": alpha},
                fit_set,
                num_boost_round=rounds,
                valid_sets=[watch_set],
                callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
            )

        def _bounds(x: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
            lo = boosters["lower"].predict(x, num_iteration=boosters["lower"].best_iteration)
            hi = boosters["upper"].predict(x, num_iteration=boosters["upper"].best_iteration)
            return np.minimum(lo, hi), np.maximum(lo, hi)

        calib_lo, calib_hi = _bounds(x_calib)
        offset = _conformalise(y_calib.to_numpy(), calib_lo, calib_hi)

        def _evaluate(label: str, x: pd.DataFrame, target: pd.Series) -> SplitMetrics:
            actual = target.to_numpy()
            pred = booster.predict(x, num_iteration=booster.best_iteration)
            raw_lo, raw_hi = _bounds(x)
            lo, hi = raw_lo - offset, raw_hi + offset
            residual = actual - pred
            denom = np.where(np.abs(actual) < 1e-6, np.nan, actual)
            ss_res = float(np.sum(residual**2))
            ss_tot = float(np.sum((actual - actual.mean()) ** 2))
            mae = float(np.mean(np.abs(residual)))
            total_actual = float(np.sum(np.abs(actual)))
            baseline_errors = {
                name: float(np.nanmean(np.abs(actual - x[name].to_numpy())))
                for name in BASELINE_FEATURES
                if name in x.columns
            }
            baseline_name = min(baseline_errors, key=lambda k: baseline_errors[k])
            baseline_mae = baseline_errors[baseline_name]
            return SplitMetrics(
                label=label,
                n=len(x),
                start=str(x.index.min()),
                end=str(x.index.max()),
                mae_kw=round(mae, 4),
                rmse_kw=round(float(np.sqrt(np.mean(residual**2))), 4),
                mape_pct=round(float(np.nanmean(np.abs(residual / denom)) * 100.0), 3),
                wape_pct=round(
                    100.0 * float(np.sum(np.abs(residual))) / total_actual
                    if total_actual
                    else 0.0,
                    3,
                ),
                r2=round(1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"), 4),
                baseline_mae_kw=round(baseline_mae, 4),
                baseline_name=baseline_name,
                skill_vs_baseline_pct=round(
                    100.0 * (1.0 - mae / baseline_mae) if baseline_mae > 0 else 0.0, 2
                ),
                interval_coverage_pct=round(
                    100.0 * float(np.mean((actual >= lo) & (actual <= hi))), 2
                ),
                raw_interval_coverage_pct=round(
                    100.0 * float(np.mean((actual >= raw_lo) & (actual <= raw_hi))), 2
                ),
                mean_interval_width_kw=round(float(np.mean(hi - lo)), 3),
            )

        live: SplitMetrics | None = None
        if live_slice is not None:
            x_live, y_live = features.iloc[live_slice], y.iloc[live_slice]
            if len(x_live) >= 48:
                live = _evaluate("live", x_live, y_live)

        metrics = ForecastMetrics(
            n_train=len(x_fit),
            n_calib=len(x_calib),
            train_start=str(x_fit.index.min()),
            train_end=str(x_fit.index.max()),
            calib_start=str(x_calib.index.min()),
            calib_end=str(x_calib.index.max()),
            conformal_offset_kw=round(float(offset), 4),
            backtest=_evaluate("backtest", x_back, y_back),
            live=live,
        )

        gain = booster.feature_importance(importance_type="gain")
        total = float(gain.sum()) or 1.0
        importance = {
            name: float(value) / total
            for name, value in zip(booster.feature_name(), gain, strict=True)
        }

        model = ForecastModel(
            model_id=f"lgbm-{target}-{asset_id}-v1",
            asset_id=asset_id,
            target=target,
            unit=unit,
            feature_columns=list(features.columns),
            base_temperature_c=base_temperature_c,
            metrics=metrics,
            feature_importance=importance,
            trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            cutoff=str(cutoff) if cutoff is not None else None,
            notes=notes or [],
            booster=booster,
            booster_lower=boosters["lower"],
            booster_upper=boosters["upper"],
            conformal_offset=float(offset),
        )
        return model

    # -- persistence ------------------------------------------------------
    def save(self, model: ForecastModel) -> Path:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        path = self.models_dir / f"{model.model_id}.joblib"
        joblib.dump(model, path, compress=3)
        (self.models_dir / f"{model.model_id}.card.json").write_text(
            json.dumps(model.card(), indent=2)
        )
        return path

    def load(self, model_id: str) -> ForecastModel:
        if model_id in self._cache:
            return self._cache[model_id]
        path = self.models_dir / f"{model_id}.joblib"
        if not path.exists():
            raise FileNotFoundError(f"no trained model at {path}")
        model: ForecastModel = joblib.load(path)
        self._cache[model_id] = model
        return model

    def for_asset(self, asset_id: str, target: str = "load_kw") -> ForecastModel:
        return self.load(f"lgbm-{target}-{asset_id}-v1")

    def has_model(self, asset_id: str, target: str = "load_kw") -> bool:
        return (self.models_dir / f"lgbm-{target}-{asset_id}-v1.joblib").exists()

    # -- inference --------------------------------------------------------
    def predict(self, model: ForecastModel, frame: pd.DataFrame) -> pd.DataFrame:
        """Point forecast plus interval, aligned to ``frame``'s index.

        Rows whose features are not fully available (the warm-up period) come
        back as NaN rather than being silently filled.
        """
        builder = FeatureBuilder(
            base_temperature_c=model.base_temperature_c, target=model.target
        )
        builder.columns = model.feature_columns
        features = builder.transform(frame)
        complete = features.dropna(how="any")
        out = pd.DataFrame(
            index=frame.index,
            columns=["prediction", "lower", "upper"],
            dtype="float64",
        )
        if complete.empty:
            return out
        point = model.booster.predict(complete, num_iteration=model.booster.best_iteration)
        lower = model.booster_lower.predict(
            complete, num_iteration=model.booster_lower.best_iteration
        )
        upper = model.booster_upper.predict(
            complete, num_iteration=model.booster_upper.best_iteration
        )
        lower, upper = np.minimum(lower, upper), np.maximum(lower, upper)
        lower = lower - model.conformal_offset
        upper = upper + model.conformal_offset
        out.loc[complete.index, "prediction"] = point
        out.loc[complete.index, "lower"] = np.minimum(lower, point)
        out.loc[complete.index, "upper"] = np.maximum(upper, point)
        return out


_FORECASTER: LoadForecaster | None = None


def load_forecaster() -> LoadForecaster:
    global _FORECASTER
    if _FORECASTER is None:
        _FORECASTER = LoadForecaster()
    return _FORECASTER
