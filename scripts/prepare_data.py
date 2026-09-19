"""Turn the raw public dataset into the processed parquet EcoTwin serves.

What this script decides, and why each decision is defensible:

1. **Which series are usable.** The source splits every site into short
   "forecast windows" (``ForecastId``) at 15 / 60 / 1440-minute granularity.
   Only the 15-minute windows are kept, resampled onto a strict 15-minute grid.

2. **What the unit is.** The publisher does *not* state a unit for ``Value``.
   We test the hypothesis "Value is Wh consumed during the preceding sampling
   interval" by converting to power density and checking it against the band a
   real commercial building can physically occupy (``PLAUSIBLE_W_PER_M2``).
   Sites failing the test are excluded rather than rescaled by a fudge factor.
   The resulting kW series is tagged **DERIVED**, never MEASURED, and the
   assumption travels with it in provenance.

3. **Which window to demo.** The source blocks are ~10-day chunks scattered
   over several years, so a date dense for one site is often empty for another.
   We search for the window that maximises the *quality* of the simultaneously
   complete sites, not merely their count -- a portfolio of flat-profile sites
   is a worse demo than a smaller portfolio with real daily structure.

4. **Which building leads BMS.** The site in that window with the strongest
   occupied/unoccupied contrast, a real base load and a sane peak-to-median
   ratio. A mostly-dark shell scores high on naive contrast and makes a poor
   HVAC story, so it is filtered out explicitly.

Usage:
    python scripts/prepare_data.py
    python scripts/prepare_data.py --use-cache      # skip the raw CSV scan
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]

GRID = "15min"
GRID_MINUTES = 15
#: A commercial building's whole-site electrical power density, in W/m2.
#: Below ~3 the "site" is a sub-meter or the unit hypothesis is wrong; above
#: ~120 it is industrial process load, not a building we can reason about.
PLAUSIBLE_W_PER_M2 = (3.0, 120.0)
MIN_SAMPLES = 40_000
MAX_GAP_FILL = 4  # interpolate gaps up to 1 hour; longer gaps stay NaN

DENSE_DAY_COVERAGE = 0.98
MIN_DEMO_SITES = 6
MAX_PORTFOLIO = 8
DEMO_WINDOW_CANDIDATES = (10, 9, 8, 7, 6, 5)
WINDOW_LENGTH_PREFERENCE = 0.45

#: A BMS story needs a building with a real base load, not a mostly-dark shell.
MIN_BMS_MEDIAN_KW = 25.0
MIN_LOAD_FACTOR = 0.20
MIN_BMS_W_PER_M2 = 6.0

CACHE_LOAD = "_candidates_load.parquet"
CACHE_WX = "_candidates_weather.parquet"
CACHE_PROFILES = "_candidate_profiles.json"


def _log(msg: str) -> None:
    print(f"[prepare] {msg}", flush=True)


# --------------------------------------------------------------------------
# extract
# --------------------------------------------------------------------------
def _window_intervals(raw: Path) -> pd.DataFrame:
    """Median sampling interval of every (SiteId, ForecastId) source window."""
    frames = []
    for chunk in pd.read_csv(
        raw / "train.csv",
        usecols=["SiteId", "Timestamp", "ForecastId", "Value"],
        parse_dates=["Timestamp"],
        chunksize=1_500_000,
    ):
        frames.append(
            chunk.groupby(["SiteId", "ForecastId"]).agg(
                n=("Value", "size"), t0=("Timestamp", "min"), t1=("Timestamp", "max")
            )
        )
    agg = (
        pd.concat(frames)
        .groupby(level=[0, 1])
        .agg(n=("n", "sum"), t0=("t0", "min"), t1=("t1", "max"))
    )
    span = (agg["t1"] - agg["t0"]).dt.total_seconds() / 60.0
    agg["interval_min"] = (span / (agg["n"] - 1).clip(lower=1)).round(2)
    return agg


def _load_consumption(raw: Path, keep_windows: set[int], sites: set[int]) -> pd.DataFrame:
    frames = []
    for chunk in pd.read_csv(
        raw / "train.csv",
        usecols=["SiteId", "Timestamp", "ForecastId", "Value"],
        parse_dates=["Timestamp"],
        chunksize=1_500_000,
    ):
        frames.append(
            chunk[chunk["ForecastId"].isin(keep_windows) & chunk["SiteId"].isin(sites)]
        )
    return pd.concat(frames, ignore_index=True)


def _load_weather(raw: Path, sites: set[int]) -> pd.DataFrame:
    """Nearest-station outdoor air temperature per site."""
    frames = []
    for chunk in pd.read_csv(
        raw / "weather.csv",
        usecols=["Timestamp", "Temperature", "Distance", "SiteId"],
        parse_dates=["Timestamp"],
        chunksize=2_000_000,
    ):
        frames.append(chunk[chunk["SiteId"].isin(sites)])
    weather = pd.concat(frames, ignore_index=True)
    if weather.empty:
        return weather
    # Keep only the closest station per site: mixing stations at different
    # distances injects a step change the model would learn as signal.
    nearest = weather.groupby("SiteId")["Distance"].min().rename("min_distance")
    weather = weather.join(nearest, on="SiteId")
    weather = weather[np.isclose(weather["Distance"], weather["min_distance"], atol=1e-6)]
    return weather.drop(columns=["min_distance"])


# --------------------------------------------------------------------------
# reshape
# --------------------------------------------------------------------------
def _to_grid(frame: pd.DataFrame, value_col: str, limit: int = MAX_GAP_FILL) -> pd.DataFrame:
    """Resample one site onto the strict 15-minute grid, flagging quality."""
    series = (
        frame.drop_duplicates(subset="Timestamp")
        .set_index("Timestamp")[value_col]
        .sort_index()
        .resample(GRID)
        .mean()
    )
    observed = series.notna()
    filled = series.interpolate(method="time", limit=limit, limit_area="inside")
    quality = np.where(observed, "GOOD", np.where(filled.notna(), "INTERPOLATED", "MISSING"))
    return pd.DataFrame({value_col: filled, "quality": quality}, index=series.index)


def _profile_score(kw: pd.Series, day_off: dict[int, bool]) -> dict[str, float]:
    """How cleanly does the site separate occupied from unoccupied operation?"""
    valid = kw.dropna()
    if valid.empty:
        return {"occupancy_contrast": 0.0, "diurnal_swing": 0.0}
    frame = valid.to_frame("kw")
    frame["dow"] = frame.index.dayofweek
    frame["hour"] = frame.index.hour
    frame["is_off"] = frame["dow"].map(lambda d: bool(day_off.get(int(d), False)))
    occupied = frame[(~frame["is_off"]) & frame["hour"].between(9, 17)]["kw"]
    unoccupied = frame[frame["is_off"] | (~frame["hour"].between(6, 20))]["kw"]
    if occupied.empty or unoccupied.empty or occupied.median() <= 0:
        return {"occupancy_contrast": 0.0, "diurnal_swing": 0.0}
    contrast = float(1.0 - unoccupied.median() / occupied.median())
    by_hour = frame.groupby("hour")["kw"].median()
    swing = float((by_hour.max() - by_hour.min()) / by_hour.max()) if by_hour.max() > 0 else 0.0
    return {"occupancy_contrast": round(contrast, 4), "diurnal_swing": round(swing, 4)}


# --------------------------------------------------------------------------
# demo-window search
# --------------------------------------------------------------------------
def _day_quality(load: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Per (site, day): completeness, magnitude and within-day load swing.

    ``day_swing`` is what makes a demo legible -- a site that draws the same
    power at 03:00 and 13:00 has no operational story to tell.

    Coverage is the *joint* completeness of load and outdoor temperature.
    The weather station series and the meter series come from different
    files with different date ranges, so a day dense in one can be empty in
    the other -- and a forecast window without weather loses the feature
    that carries most of the HVAC signal.
    """
    frame = load.assign(day=load["timestamp"].dt.floor("D"))
    grouped = frame.groupby(["site_id", "day"])["load_kw"]
    out = grouped.agg(
        n="size",
        n_valid="count",
        mean_kw="mean",
        p10=lambda x: float(np.nanpercentile(x, 10)) if x.notna().any() else np.nan,
        p90=lambda x: float(np.nanpercentile(x, 90)) if x.notna().any() else np.nan,
    ).reset_index()
    out["load_coverage"] = out["n_valid"] / out["n"].clip(lower=1)
    out["day_swing"] = np.where(out["p90"] > 0, 1.0 - out["p10"] / out["p90"], 0.0)

    wx = weather.assign(day=weather["timestamp"].dt.floor("D"))
    wx_cov = (
        wx.groupby(["site_id", "day"])["outdoor_temp_c"]
        .agg(wx_n="size", wx_valid="count")
        .reset_index()
    )
    wx_cov["weather_coverage"] = wx_cov["wx_valid"] / wx_cov["wx_n"].clip(lower=1)
    out = out.merge(
        wx_cov[["site_id", "day", "weather_coverage"]], on=["site_id", "day"], how="left"
    )
    out["weather_coverage"] = out["weather_coverage"].fillna(0.0)
    out["coverage"] = out[["load_coverage", "weather_coverage"]].min(axis=1)
    return out


def _select_demo_window(day_quality: pd.DataFrame) -> dict[str, Any]:
    """Pick the window maximising the *quality* of simultaneously complete sites."""
    dense = day_quality[day_quality["coverage"] >= DENSE_DAY_COVERAGE]
    if dense.empty:
        raise SystemExit("no site-day reached the density threshold")

    days = pd.date_range(dense["day"].min(), dense["day"].max(), freq="D")
    present = (
        dense.assign(ok=1.0)
        .pivot_table(index="day", columns="site_id", values="ok", fill_value=0.0)
        .reindex(days, fill_value=0.0)
    )
    swing = (
        dense.pivot_table(index="day", columns="site_id", values="day_swing", fill_value=0.0)
        .reindex(days, fill_value=0.0)
        .reindex(columns=present.columns, fill_value=0.0)
    )

    best: dict[str, Any] | None = None
    for n_days in DEMO_WINDOW_CANDIDATES:
        if n_days > len(present):
            continue
        complete = present.rolling(n_days, min_periods=n_days).sum() == n_days
        mean_swing = swing.rolling(n_days, min_periods=n_days).mean()
        n_sites = complete.sum(axis=1)
        # Score = quality of the sites we could show, capped at the portfolio size.
        score = (mean_swing.where(complete, 0.0)).apply(
            lambda row: float(np.sort(row.to_numpy())[::-1][:MAX_PORTFOLIO].sum()), axis=1
        )
        # A longer replay is worth something, but not at any price: the mild
        # exponent keeps a much better short window from being discarded.
        utility = score * (float(n_days) ** WINDOW_LENGTH_PREFERENCE)
        eligible = utility[n_sites >= MIN_DEMO_SITES]
        if eligible.empty:
            continue
        end = eligible.idxmax()
        sites = set(int(s) for s in complete.columns[complete.loc[end]].tolist())
        candidate = {
            "n_days": int(n_days),
            "end": end,
            "start": end - pd.Timedelta(days=n_days - 1),
            "sites": sites,
            "score": float(score.loc[end]),
            "utility": float(eligible.loc[end]),
        }
        if best is None or candidate["utility"] > best["utility"]:
            best = candidate

    if best is None:
        raise SystemExit(
            f"no window kept {MIN_DEMO_SITES} sites complete; lower MIN_DEMO_SITES "
            "or DENSE_DAY_COVERAGE"
        )
    return best


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def _extract(raw: Path, out: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = pd.read_csv(raw / "metadata.csv")
    day_off_cols = {
        0: "MondayIsDayOff",
        1: "TuesdayIsDayOff",
        2: "WednesdayIsDayOff",
        3: "ThursdayIsDayOff",
        4: "FridayIsDayOff",
        5: "SaturdayIsDayOff",
        6: "SundayIsDayOff",
    }

    _log("scanning forecast-window granularity ...")
    windows = _window_intervals(raw)
    fine = windows[windows["interval_min"] == float(GRID_MINUTES)]
    keep_windows = set(fine.index.get_level_values("ForecastId"))
    per_site_rows = fine.groupby(level="SiteId")["n"].sum()
    shortlist = set(int(s) for s in per_site_rows[per_site_rows >= MIN_SAMPLES].index)
    _log(
        f"{len(windows)} windows, {len(fine)} at {GRID_MINUTES} min, "
        f"{len(shortlist)} sites with >= {MIN_SAMPLES:,} fine samples"
    )

    _log("loading consumption ...")
    cons = _load_consumption(raw, keep_windows, shortlist)
    _log("loading weather ...")
    weather = _load_weather(raw, shortlist)
    weather_sites = set(int(s) for s in weather["SiteId"].unique()) if not weather.empty else set()
    _log(f"weather available for {len(weather_sites)} shortlisted sites")

    load_frames: list[pd.DataFrame] = []
    weather_frames: list[pd.DataFrame] = []
    profiles: list[dict[str, Any]] = []

    for site_id, group in cons.groupby("SiteId"):
        site_meta = meta[meta["SiteId"] == site_id]
        if site_meta.empty:
            continue
        row = site_meta.iloc[0]
        surface = float(row["Surface"])
        day_off = {d: bool(row[c]) for d, c in day_off_cols.items()}

        gridded = _to_grid(group[["Timestamp", "Value"]], "Value")
        # Unit hypothesis: Value is Wh over the preceding 15-minute interval.
        kw = gridded["Value"] * (60.0 / GRID_MINUTES) / 1000.0
        w_per_m2 = float(np.nanmedian(kw)) * 1000.0 / surface if surface > 0 else float("nan")
        plausible = PLAUSIBLE_W_PER_M2[0] <= w_per_m2 <= PLAUSIBLE_W_PER_M2[1]

        profiles.append(
            {
                "site_id": int(site_id),
                "surface_m2": surface,
                "meter_sampling_min": float(row["Sampling"]),
                "base_temperature_c": float(row["BaseTemperature"]),
                "day_off": day_off,
                "n_samples": int(gridded["Value"].notna().sum()),
                "coverage": round(float(gridded["Value"].notna().mean()), 4),
                "span_days": round(
                    float((gridded.index.max() - gridded.index.min()).total_seconds() / 86400), 1
                ),
                "first_timestamp": gridded.index.min().isoformat(),
                "last_timestamp": gridded.index.max().isoformat(),
                "median_kw": round(float(np.nanmedian(kw)), 3),
                "p99_kw": round(float(np.nanpercentile(kw.dropna(), 99)), 3),
                "peak_kw": round(float(np.nanmax(kw)), 3),
                "w_per_m2_median": round(w_per_m2, 2),
                "unit_hypothesis_plausible": bool(plausible),
                "has_weather": bool(int(site_id) in weather_sites),
                "interpolated_pct": round(
                    100.0 * float((gridded["quality"] == "INTERPOLATED").mean()), 3
                ),
                **_profile_score(kw, day_off),
            }
        )

        if not plausible or int(site_id) not in weather_sites:
            continue

        load_frames.append(
            pd.DataFrame(
                {
                    "site_id": int(site_id),
                    "timestamp": gridded.index,
                    "energy_wh_interval": gridded["Value"].to_numpy(),
                    "load_kw": kw.to_numpy(),
                    "quality": gridded["quality"].to_numpy(),
                }
            )
        )
        w = weather[weather["SiteId"] == site_id][["Timestamp", "Temperature"]]
        wg = _to_grid(w.rename(columns={"Temperature": "temp"}), "temp", limit=8)
        weather_frames.append(
            pd.DataFrame(
                {
                    "site_id": int(site_id),
                    "timestamp": wg.index,
                    "outdoor_temp_c": wg["temp"].to_numpy(),
                    "quality": wg["quality"].to_numpy(),
                }
            )
        )

    all_load = pd.concat(load_frames, ignore_index=True)
    all_wx = pd.concat(weather_frames, ignore_index=True)
    profile_frame = pd.DataFrame(profiles).sort_values("site_id")

    all_load.to_parquet(out / CACHE_LOAD, index=False)
    all_wx.to_parquet(out / CACHE_WX, index=False)
    profile_frame.to_json(out / CACHE_PROFILES, orient="records", indent=2)
    holidays = pd.read_csv(raw / "holidays.csv", usecols=["Date", "Holiday", "SiteId"])
    holidays["Date"] = pd.to_datetime(holidays["Date"])
    return all_load, all_wx, profile_frame, holidays


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default="data/raw/power_laws_forecasting")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--use-cache", action="store_true", help="reuse the extracted candidates")
    args = parser.parse_args()

    raw = REPO_ROOT / args.raw_dir
    out = REPO_ROOT / args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    required = ["train.csv", "metadata.csv", "weather.csv", "holidays.csv"]
    missing = [f for f in required if not (raw / f).exists()]
    if missing:
        _log(f"raw files missing: {missing}")
        _log("Nothing to prepare. EcoTwin will serve SAMPLE FIXTURE data.")
        (out / "selection.json").write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "status": "NO_RAW_DATA",
                    "missing_files": missing,
                    "mode": "SAMPLE_FIXTURE",
                },
                indent=2,
            )
        )
        return 0

    if args.use_cache and (out / CACHE_LOAD).exists():
        _log("reusing extracted candidate cache")
        all_load = pd.read_parquet(out / CACHE_LOAD)
        all_wx = pd.read_parquet(out / CACHE_WX)
        profile_frame = pd.read_json(out / CACHE_PROFILES)
        holidays = pd.read_csv(raw / "holidays.csv", usecols=["Date", "Holiday", "SiteId"])
        holidays["Date"] = pd.to_datetime(holidays["Date"])
    else:
        all_load, all_wx, profile_frame, holidays = _extract(raw, out)

    usable = profile_frame[
        profile_frame["unit_hypothesis_plausible"] & profile_frame["has_weather"]
    ].copy()
    _log(f"{len(profile_frame)} sites profiled, {len(usable)} usable after unit + weather checks")

    quality = _day_quality(all_load, all_wx)
    window = _select_demo_window(quality)
    _log(
        f"demo window {window['start'].date()} .. {window['end'].date()} "
        f"({window['n_days']} days) keeps {len(window['sites'])} sites complete "
        f"(quality score {window['score']:.2f})"
    )

    usable = usable[usable["site_id"].isin(window["sites"])].copy()
    if usable.empty:
        raise SystemExit("demo window selection left no usable sites")

    # In-window statistics decide the ranking: global averages can hide the fact
    # that a site is idle exactly during the days we are going to show.
    w0 = window["start"]
    w1 = window["end"] + pd.Timedelta(days=1)
    win = all_load[
        (all_load["timestamp"] >= w0)
        & (all_load["timestamp"] < w1)
        & (all_load["site_id"].isin(usable["site_id"]))
    ]
    day_off_map = {int(r["site_id"]): r["day_off"] for _, r in usable.iterrows()}
    in_window: list[dict[str, Any]] = []
    for site_id, group in win.groupby("site_id"):
        kw = group.set_index("timestamp")["load_kw"]
        raw_off = day_off_map.get(int(site_id), {})
        off = {int(k): bool(v) for k, v in raw_off.items()}
        stats = _profile_score(kw, off)
        in_window.append(
            {
                "site_id": int(site_id),
                "window_median_kw": round(float(np.nanmedian(kw)), 3),
                "window_peak_kw": round(float(np.nanmax(kw)), 3),
                "window_occupancy_contrast": stats["occupancy_contrast"],
                "window_diurnal_swing": stats["diurnal_swing"],
            }
        )
    usable = usable.merge(pd.DataFrame(in_window), on="site_id", how="inner")
    usable["load_factor"] = (usable["median_kw"] / usable["p99_kw"].clip(lower=1e-9)).round(4)
    usable["window_load_factor"] = (
        usable["window_median_kw"] / usable["window_peak_kw"].clip(lower=1e-9)
    ).round(4)

    usable["building_like"] = (
        (usable["window_median_kw"] >= MIN_BMS_MEDIAN_KW)
        & (usable["load_factor"] >= MIN_LOAD_FACTOR)
        & (usable["w_per_m2_median"] >= MIN_BMS_W_PER_M2)
        & (usable["window_diurnal_swing"] >= 0.25)
    )
    usable["score"] = (
        usable["coverage"]
        + usable["window_diurnal_swing"].clip(0, 1) * 1.6
        + usable["window_occupancy_contrast"].clip(0, 1) * 1.2
        + usable["load_factor"].clip(0, 0.6) * 1.0
    )
    usable = usable.sort_values("score", ascending=False).head(MAX_PORTFOLIO)

    bms_pool = usable[usable["building_like"]]
    if bms_pool.empty:
        _log("WARNING: no site met the building-like criteria; using best overall score")
        bms_pool = usable
    bms_site = int(
        bms_pool.sort_values(
            ["window_diurnal_swing", "window_occupancy_contrast"], ascending=False
        ).iloc[0]["site_id"]
    )
    ems_sites = [int(s) for s in usable["site_id"]]

    chosen = set(ems_sites)
    load = all_load[all_load["site_id"].isin(chosen)].reset_index(drop=True)
    wx = all_wx[all_wx["site_id"].isin(chosen)].reset_index(drop=True)
    hol = holidays[holidays["SiteId"].isin(chosen)].rename(
        columns={"Date": "date", "Holiday": "holiday", "SiteId": "site_id"}
    )

    load.to_parquet(out / "load_15min.parquet", index=False)
    wx.to_parquet(out / "weather_15min.parquet", index=False)
    hol.to_parquet(out / "holidays.parquet", index=False)
    profile_frame.to_json(out / "site_profiles.json", orient="records", indent=2)

    selection = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "OK",
        "mode": "REAL_DATA",
        "source_key": "power_laws_forecasting",
        "grid": GRID,
        "unit_hypothesis": {
            "statement": (
                "Value is energy in Wh consumed during the preceding 15-minute "
                "interval; load_kw = Value * 4 / 1000."
            ),
            "validated_by": (
                f"median power density inside {PLAUSIBLE_W_PER_M2[0]}-"
                f"{PLAUSIBLE_W_PER_M2[1]} W/m2 using the published Surface"
            ),
            "publisher_states_unit": False,
            "consequence": "All kW series are tagged DERIVED, never MEASURED.",
        },
        "selection_rule": (
            f"15-minute windows only; >= {MIN_SAMPLES:,} samples; nearest weather "
            "station present; unit hypothesis plausible; site complete across the "
            "demo window; ranked on in-window diurnal swing, occupancy contrast "
            "and load factor."
        ),
        "demo_window": {
            "start": w0.isoformat(),
            "end": w1.isoformat(),
            "days": int(window["n_days"]),
            "rule": (
                f"longest window of {DEMO_WINDOW_CANDIDATES[0]}.."
                f"{DEMO_WINDOW_CANDIDATES[-1]} days keeping >= {MIN_DEMO_SITES} sites "
                f"at >= {DENSE_DAY_COVERAGE:.0%} daily completeness, maximising the "
                "summed daily load swing of the portfolio"
            ),
        },
        "bms_site": bms_site,
        "ems_sites": ems_sites,
        "sites": json.loads(usable.drop(columns=["score"]).to_json(orient="records")),
        "row_counts": {"load": int(len(load)), "weather": int(len(wx)), "holidays": int(len(hol))},
    }
    (out / "selection.json").write_text(json.dumps(selection, indent=2, default=str))

    _log(f"BMS site -> {bms_site}; EMS portfolio -> {ems_sites}")
    _log(f"wrote {len(load):,} load rows and {len(wx):,} weather rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
