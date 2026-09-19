"""Serving the "expected" series, with a model-quality gate.

A trained model is not automatically the thing we serve. If a model failed to
beat the strongest naive baseline on its own backtest, serving it would make
every downstream anomaly and recommendation worse than doing nothing. So the
gate is explicit:

* skill over the best naive baseline > ``MIN_SKILL_PCT``  -> serve the model;
* otherwise                                               -> serve the
  seasonal-naive reference the model failed to beat, and say so in provenance
  and in the UI.

This is ordinary production hygiene, and it means the platform degrades to
something defensible rather than to something wrong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from core.models.features import STEPS_PER_DAY
from core.models.forecast import ForecastModel, LoadForecaster, load_forecaster
from core.provenance import Provenance
from core.provenance.model import derived, predicted

log = logging.getLogger(__name__)

#: Minimum backtest skill over the best naive baseline, in percent.
MIN_SKILL_PCT = 1.0
#: Lag used by the fallback, in 15-minute steps. One day.
FALLBACK_LAG = STEPS_PER_DAY


@dataclass
class ExpectedSeries:
    """Expected load plus the interval, and how it was produced."""

    frame: pd.DataFrame  # columns: prediction, lower, upper
    served_by: Literal["model", "seasonal_naive"]
    model: ForecastModel | None
    model_id: str
    gate_reason: str
    provenance: Provenance

    @property
    def prediction(self) -> pd.Series:
        return self.frame["prediction"]


class ExpectedLoadService:
    def __init__(self, forecaster: LoadForecaster | None = None) -> None:
        self.forecaster = forecaster or load_forecaster()

    def _fallback(self, frame: pd.DataFrame, target: str) -> pd.DataFrame:
        """Same time yesterday, with an empirical interval from its own error."""
        series = frame[target].astype(float)
        prediction = series.shift(FALLBACK_LAG)
        residual = (series - prediction).dropna()
        spread = float(np.nanpercentile(np.abs(residual), 80)) if len(residual) else 0.0
        return pd.DataFrame(
            {
                "prediction": prediction,
                "lower": prediction - spread,
                "upper": prediction + spread,
            },
            index=frame.index,
        )

    def expected(
        self,
        frame: pd.DataFrame,
        *,
        asset_id: str,
        target: str = "load_kw",
        unit: str = "kW",
    ) -> ExpectedSeries:
        model: ForecastModel | None = None
        gate_reason = ""
        if self.forecaster.has_model(asset_id, target):
            try:
                model = self.forecaster.for_asset(asset_id, target)
            except Exception as exc:  # pragma: no cover - corrupt artefact
                log.warning("could not load model for %s: %s", asset_id, exc)
                model = None

        if model is not None:
            skill = model.metrics.backtest.skill_vs_baseline_pct
            if skill > MIN_SKILL_PCT:
                predictions = self.forecaster.predict(model, frame)
                if predictions["prediction"].notna().any():
                    return ExpectedSeries(
                        frame=predictions,
                        served_by="model",
                        model=model,
                        model_id=model.model_id,
                        gate_reason=(
                            f"Model beats the {model.metrics.backtest.baseline_name} "
                            f"baseline by {skill:.1f}% on backtest."
                        ),
                        provenance=predicted(
                            model_id=model.model_id,
                            units=unit,
                            processing=(
                                "LightGBM day-ahead forecast with a conformalised "
                                "80% interval"
                            ),
                            notes=(
                                f"Trained on data before {model.cutoff}; backtest "
                                f"MAE {model.metrics.backtest.mae_kw:.2f} {unit}, "
                                f"R² {model.metrics.backtest.r2:.3f}."
                            ),
                        ),
                    )
                gate_reason = "Model produced no usable prediction over this window."
            else:
                gate_reason = (
                    f"Model skill over the {model.metrics.backtest.baseline_name} "
                    f"baseline is {skill:.1f}%, below the {MIN_SKILL_PCT:.0f}% gate."
                )
        else:
            gate_reason = "No trained model for this asset."

        return ExpectedSeries(
            frame=self._fallback(frame, target),
            served_by="seasonal_naive",
            model=model,
            model_id=f"seasonal-naive-1d-{asset_id}",
            gate_reason=gate_reason + " Serving the seasonal-naive reference instead.",
            provenance=derived(
                "residual_anomaly",
                field=target,
                units=unit,
                processing="seasonal-naive reference: the measured value 24 h earlier",
                assumptions=[
                    "Used because the trained model did not clear the quality gate.",
                    "Interval is the 80th percentile of the reference's own error.",
                ],
                notes=gate_reason,
            ),
        )
