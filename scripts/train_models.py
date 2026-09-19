"""Train the per-asset load forecasters and write model cards.

Everything runs offline; the served application only does inference. Each model
is evaluated against an honest baseline ("same time last week") on a held-out
period that comes strictly *after* the training period, and the result is
written to ``models/<model_id>.card.json`` -- including when it is bad.

Usage:
    python scripts/train_models.py
    python scripts/train_models.py --asset 63 --rounds 800
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.adapters.building import get_building_adapter  # noqa: E402
from core.adapters.power import get_power_adapter  # noqa: E402
from core.common import paths  # noqa: E402
from core.adapters.building.power_laws import demo_window  # noqa: E402
from core.models.forecast import LoadForecaster  # noqa: E402


def _log(msg: str) -> None:
    print(f"[train] {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", action="append", help="train only these asset ids")
    parser.add_argument("--rounds", type=int, default=600)
    parser.add_argument("--models-dir", default=str(paths.MODELS_DIR))
    parser.add_argument(
        "--no-cutoff",
        action="store_true",
        help="ignore the demo window and use a plain chronological split",
    )
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    forecaster = LoadForecaster(models_dir=models_dir)

    building = get_building_adapter()
    power = get_power_adapter()

    # Train strictly on history preceding the demo window, so every prediction
    # the demo replays is genuinely out-of-sample.
    window = demo_window()
    cutoff = window[0] if window else None
    if args.no_cutoff:
        cutoff = None
    _log(f"training cutoff: {cutoff if cutoff is not None else 'none (chronological split)'}")

    # One model per asset; BMS and EMS share the same forecaster family, which
    # is why the portfolio and the building page never disagree about expected
    # load for the same site.
    assets: dict[str, dict[str, object]] = {}
    for site in building.list_sites():
        assets[site.site_id] = {
            "adapter": building,
            "base_temperature_c": site.base_temperature_c,
            "name": site.name,
            "kind": "building",
        }
    for facility in power.list_facilities():
        assets.setdefault(
            facility.facility_id,
            {
                "adapter": power,
                "base_temperature_c": 18.0,
                "name": facility.name,
                "kind": "facility",
            },
        )

    if args.asset:
        wanted = set(args.asset)
        assets = {k: v for k, v in assets.items() if k in wanted}
    if not assets:
        _log("no assets to train")
        return 1

    summary = []
    for asset_id, info in sorted(assets.items(), key=lambda kv: int(kv[0])):
        adapter = info["adapter"]
        loader = getattr(adapter, "load_frame")
        frame = loader(asset_id)
        _log(f"asset {asset_id} ({info['name']}): {len(frame):,} rows")
        try:
            model = forecaster.train(
                frame,
                asset_id=asset_id,
                base_temperature_c=info["base_temperature_c"],
                params={"num_boost_round": args.rounds},
                cutoff=cutoff,
                notes=[
                    f"Source adapter: {getattr(adapter, 'key', 'unknown')}.",
                    "Outdoor temperature is used as a forecast input; on historical "
                    "replay the recorded observation stands in for the vendor "
                    "weather forecast.",
                    "Target is load_kw, itself DERIVED from the published energy "
                    "counter under the unit hypothesis in docs/data_provenance.md.",
                    (
                        f"Trained only on data before {cutoff}; the demo window and "
                        "everything after it is held out."
                        if cutoff is not None
                        else "Plain chronological 60/20/20 split."
                    ),
                ],
            )
        except ValueError as exc:
            _log(f"  skipped: {exc}")
            continue

        path = forecaster.save(model)
        b = model.metrics.backtest
        live = model.metrics.live
        _log(
            f"  backtest n={b.n:,} | MAE {b.mae_kw:.2f} kW | WAPE {b.wape_pct:.1f}% | "
            f"R2 {b.r2:.3f} | skill vs {b.baseline_name} {b.skill_vs_baseline_pct:+.1f}% | "
            f"coverage {b.interval_coverage_pct:.1f}% (raw {b.raw_interval_coverage_pct:.1f}%, "
            f"target {b.interval_target_pct:.0f}%)"
        )
        if live is not None:
            _log(
                f"  live     n={live.n:,} | MAE {live.mae_kw:.2f} kW | "
                f"WAPE {live.wape_pct:.1f}% | coverage {live.interval_coverage_pct:.1f}%"
            )
        summary.append(
            {
                "asset_id": asset_id,
                "name": info["name"],
                "model_id": model.model_id,
                "artifact": str(path.relative_to(REPO_ROOT)),
                "training_cutoff": model.cutoff,
                "backtest": {
                    "n": b.n,
                    "mae_kw": b.mae_kw,
                    "wape_pct": b.wape_pct,
                    "r2": b.r2,
                    "baseline_name": b.baseline_name,
                    "baseline_mae_kw": b.baseline_mae_kw,
                    "skill_vs_baseline_pct": b.skill_vs_baseline_pct,
                    "interval_coverage_pct": b.interval_coverage_pct,
                },
                "live": (
                    {
                        "n": live.n,
                        "mae_kw": live.mae_kw,
                        "wape_pct": live.wape_pct,
                        "interval_coverage_pct": live.interval_coverage_pct,
                    }
                    if live is not None
                    else None
                ),
                "n_train": model.metrics.n_train,
                "top_features": [label for _, label, _ in model.top_features(5)],
            }
        )

    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "training_summary.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "n_models": len(summary),
                "models": summary,
            },
            indent=2,
        )
    )
    beaten = [s for s in summary if s["backtest"]["skill_vs_baseline_pct"] > 0]
    _log(f"trained {len(summary)} models; {len(beaten)} beat the best naive baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
