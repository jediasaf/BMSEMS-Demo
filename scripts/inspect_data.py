"""Inspect raw source files and emit a factual schema report.

This script makes **no assumptions** about the shape of the downloaded data. It
reads whatever is present under ``data/raw`` and reports files, columns, dtypes,
timestamp ranges, sampling intervals, missingness, unique assets and candidate
model targets.

The output (``docs/schema_report.md`` + ``data/processed/schema_report.json``)
is the evidence base for the adapter layer: adapters are written against the
report, never against guessed field names.

Usage:
    python scripts/inspect_data.py
    python scripts/inspect_data.py --raw-dir data/raw --max-rows 2000000
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
CHUNK = 500_000


def _human_bytes(n: int) -> str:
    step = 1024.0
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < step:
            return f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} PB"


def _detect_timestamp_columns(df: pd.DataFrame) -> list[str]:
    found: list[str] = []
    for col in df.columns:
        lowered = col.lower()
        if any(token in lowered for token in ("timestamp", "date", "time")):
            found.append(col)
    return found


def _sampling_summary(series: pd.Series) -> dict[str, Any]:
    """Median/mode sampling interval in minutes for a sorted timestamp series."""
    ordered = series.dropna().sort_values()
    if len(ordered) < 3:
        return {"median_minutes": None, "mode_minutes": None, "n_gaps": 0}
    deltas = ordered.diff().dropna().dt.total_seconds() / 60.0
    deltas = deltas[deltas > 0]
    if deltas.empty:
        return {"median_minutes": None, "mode_minutes": None, "n_gaps": 0}
    mode = deltas.round(3).mode()
    return {
        "median_minutes": float(np.median(deltas)),
        "mode_minutes": float(mode.iloc[0]) if not mode.empty else None,
        "n_gaps": int((deltas > float(np.median(deltas)) * 2.5).sum()),
    }


def _profile_csv(path: Path, max_rows: int) -> dict[str, Any]:
    size = path.stat().st_size
    report: dict[str, Any] = {
        "file": str(path.relative_to(REPO_ROOT)),
        "bytes": size,
        "size_human": _human_bytes(size),
        "format": "csv",
    }

    head = pd.read_csv(path, nrows=5_000)
    report["columns"] = list(head.columns)

    ts_cols = _detect_timestamp_columns(head)
    parse_dates = [c for c in ts_cols if c in head.columns]

    total_rows = 0
    null_counts: dict[str, int] = {c: 0 for c in head.columns}
    numeric_stats: dict[str, dict[str, float]] = {}
    unique_tracker: dict[str, set[Any]] = {}
    ts_min: dict[str, pd.Timestamp] = {}
    ts_max: dict[str, pd.Timestamp] = {}
    sample_for_interval: dict[str, list[pd.Series]] = {}
    duplicate_rows = 0

    id_like = [
        c
        for c in head.columns
        if c.lower().endswith("id") or c.lower() in ("siteid", "forecastid", "holiday")
    ]

    reader = pd.read_csv(path, chunksize=CHUNK, parse_dates=parse_dates or None)
    for chunk in reader:
        if total_rows >= max_rows:
            break
        total_rows += len(chunk)
        duplicate_rows += int(chunk.duplicated().sum())
        for col in chunk.columns:
            null_counts[col] = null_counts.get(col, 0) + int(chunk[col].isna().sum())
            if col in id_like and len(unique_tracker.get(col, ())) < 5_000:
                unique_tracker.setdefault(col, set()).update(chunk[col].dropna().unique().tolist())
            if pd.api.types.is_numeric_dtype(chunk[col]):
                col_values = chunk[col].dropna()
                if col_values.empty:
                    continue
                stats = numeric_stats.setdefault(
                    col, {"min": np.inf, "max": -np.inf, "sum": 0.0, "count": 0.0, "n_zero": 0.0}
                )
                stats["min"] = min(stats["min"], float(col_values.min()))
                stats["max"] = max(stats["max"], float(col_values.max()))
                stats["sum"] += float(col_values.sum())
                stats["count"] += float(len(col_values))
                stats["n_zero"] += float((col_values == 0).sum())
            if col in parse_dates and pd.api.types.is_datetime64_any_dtype(chunk[col]):
                col_values = chunk[col].dropna()
                if col_values.empty:
                    continue
                ts_min[col] = min(ts_min.get(col, col_values.min()), col_values.min())
                ts_max[col] = max(ts_max.get(col, col_values.max()), col_values.max())
                bucket = sample_for_interval.setdefault(col, [])
                if len(bucket) < 3:
                    bucket.append(col_values.head(20_000))

    report["rows_scanned"] = total_rows
    report["truncated"] = total_rows >= max_rows
    report["dtypes"] = {c: str(t) for c, t in head.dtypes.items()}
    report["duplicate_rows_scanned"] = duplicate_rows
    report["missingness_pct"] = {
        c: round(100.0 * null_counts.get(c, 0) / max(total_rows, 1), 4) for c in head.columns
    }
    report["numeric_stats"] = {
        c: {
            "min": s["min"],
            "max": s["max"],
            "mean": s["sum"] / s["count"] if s["count"] else None,
            "pct_zero": round(100.0 * s["n_zero"] / s["count"], 3) if s["count"] else None,
        }
        for c, s in numeric_stats.items()
    }
    report["unique_counts"] = {
        c: {"n_unique_seen": len(v), "sample": sorted(list(v))[:10]}
        for c, v in unique_tracker.items()
    }
    report["timestamps"] = {
        c: {
            "min": ts_min[c].isoformat() if c in ts_min else None,
            "max": ts_max[c].isoformat() if c in ts_max else None,
            "tz": "naive (no offset in source)",
            "sampling": _sampling_summary(pd.concat(sample_for_interval.get(c, [pd.Series([])]))),
        }
        for c in parse_dates
    }
    return report


def _candidate_targets(reports: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for rep in reports:
        for col, stats in rep.get("numeric_stats", {}).items():
            if col.lower() in ("obs_id", "siteid", "forecastid") or col == "":
                continue
            spread = (stats.get("max") or 0) - (stats.get("min") or 0)
            if spread <= 0:
                continue
            out.append(
                {
                    "file": rep["file"],
                    "column": col,
                    "reason": f"numeric, range {stats['min']:.4g}..{stats['max']:.4g}",
                }
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--max-rows", type=int, default=3_000_000)
    parser.add_argument("--out-md", default="docs/schema_report.md")
    parser.add_argument("--out-json", default="data/processed/schema_report.json")
    args = parser.parse_args()

    raw_dir = (REPO_ROOT / args.raw_dir).resolve()
    csv_files = sorted(raw_dir.rglob("*.csv"))
    parquet_files = sorted(raw_dir.rglob("*.parquet"))

    reports: list[dict[str, Any]] = []
    for path in csv_files:
        print(f"[inspect] {path.relative_to(REPO_ROOT)} ...", flush=True)
        reports.append(_profile_csv(path, args.max_rows))
    for path in parquet_files:
        df = pd.read_parquet(path)
        reports.append(
            {
                "file": str(path.relative_to(REPO_ROOT)),
                "bytes": path.stat().st_size,
                "size_human": _human_bytes(path.stat().st_size),
                "format": "parquet",
                "columns": list(df.columns),
                "rows_scanned": len(df),
                "dtypes": {c: str(t) for c, t in df.dtypes.items()},
                "missingness_pct": {
                    c: round(100.0 * df[c].isna().mean(), 4) for c in df.columns
                },
                "numeric_stats": {},
                "unique_counts": {},
                "timestamps": {},
                "truncated": False,
                "duplicate_rows_scanned": int(df.duplicated().sum()),
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "raw_dir": str(raw_dir.relative_to(REPO_ROOT)),
        "n_files": len(reports),
        "files": reports,
        "candidate_targets": _candidate_targets(reports),
    }

    out_json = REPO_ROOT / args.out_json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, default=str))

    lines: list[str] = [
        "# Raw data schema report",
        "",
        "> Generated by `scripts/inspect_data.py`. **Do not hand-edit.**",
        "> Every field used by the adapter layer must appear below; adapters are",
        "> written against this report, never against assumed field names.",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Raw directory: `{payload['raw_dir']}`",
        f"- Files inspected: **{payload['n_files']}**",
        "",
    ]
    if not reports:
        lines += [
            "## No raw files found",
            "",
            "`data/raw` is empty. EcoTwin falls back to the documented fixture adapters",
            "(`core/adapters/*/fixture.py`) and every value they emit is tagged",
            "`SAMPLE FIXTURE` in provenance. See `docs/data_provenance.md`.",
            "",
        ]
    for rep in reports:
        lines += [
            f"## `{rep['file']}`",
            "",
            f"- Size: {rep['size_human']}  ",
            f"- Rows scanned: {rep['rows_scanned']:,}"
            + (" *(truncated)*" if rep.get("truncated") else ""),
            f"- Duplicate rows in scan: {rep.get('duplicate_rows_scanned', 0):,}",
            "",
            "| column | dtype | missing % | min | max | mean |",
            "|---|---|---|---|---|---|",
        ]
        for col in rep["columns"]:
            stats = rep.get("numeric_stats", {}).get(col, {})

            def fmt(key: str) -> str:
                val = stats.get(key)
                return f"{val:.4g}" if isinstance(val, (int, float)) else "—"

            lines.append(
                f"| `{col}` | {rep['dtypes'].get(col, '—')} | "
                f"{rep['missingness_pct'].get(col, 0):.3f} | "
                f"{fmt('min')} | {fmt('max')} | {fmt('mean')} |"
            )
        lines.append("")
        if rep.get("timestamps"):
            lines += ["**Timestamps**", "", "| column | min | max | median Δ (min) | mode Δ (min) |", "|---|---|---|---|---|"]
            for col, meta in rep["timestamps"].items():
                sampling = meta.get("sampling", {})
                lines.append(
                    f"| `{col}` | {meta.get('min')} | {meta.get('max')} | "
                    f"{sampling.get('median_minutes')} | {sampling.get('mode_minutes')} |"
                )
            lines.append("")
        if rep.get("unique_counts"):
            lines += ["**Identifier-like columns**", ""]
            for col, meta in rep["unique_counts"].items():
                lines.append(
                    f"- `{col}`: {meta['n_unique_seen']} unique seen "
                    f"(sample: {meta['sample']})"
                )
            lines.append("")

    lines += ["## Candidate model targets", ""]
    for cand in payload["candidate_targets"]:
        lines.append(f"- `{cand['column']}` in `{cand['file']}` — {cand['reason']}")
    lines.append("")

    out_md = REPO_ROOT / args.out_md
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines))
    print(f"[inspect] wrote {out_md.relative_to(REPO_ROOT)} and {out_json.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
