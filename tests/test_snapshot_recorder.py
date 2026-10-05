"""The recorder's own bookkeeping, tested without recording anything.

The expensive part of ``scripts/build_static_snapshot.py`` needs the whole API
and ten minutes. These are the two pieces that are cheap to get wrong and
silent when they are: which files a run keeps, and what the browser will call
them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_static_snapshot import prepare_out, slug  # noqa: E402


def _recording(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.json").write_text(json.dumps({"recorded_at": "then", "cursor_stride": 4}))
    (root / "bms_overview__site_id-227.json").write_text("{}")
    (root / "ems_portfolio.json").write_text("{}")


def test_a_fresh_run_starts_from_empty(tmp_path: Path) -> None:
    """Otherwise a removed endpoint leaves a file behind still answering."""
    root = tmp_path / "snapshot"
    _recording(root)
    assert prepare_out(root, fill=False) == {}
    assert list(root.glob("*.json")) == []


def test_a_fill_keeps_the_recording_it_was_asked_to_top_up(tmp_path: Path) -> None:
    """The failure this guards is silent: wiping it instead still exits 0.

    The two branches are one line apart, and a fill that re-records everything
    also relabels the result with the old recording's date, so the index ends
    up claiming a time none of its files were written at.
    """
    root = tmp_path / "snapshot"
    _recording(root)
    previous = prepare_out(root, fill=True)
    assert previous["recorded_at"] == "then"
    assert previous["cursor_stride"] == 4
    assert {p.name for p in root.glob("*.json")} == {
        "index.json",
        "bms_overview__site_id-227.json",
        "ems_portfolio.json",
    }


def test_a_fill_into_nothing_is_a_fresh_run(tmp_path: Path) -> None:
    assert prepare_out(tmp_path / "new", fill=True) == {}


def test_the_slug_is_what_the_browser_will_ask_for() -> None:
    """Mirrored by snapshotFile() in apps/web/lib/api.ts, character for
    character. Percent-encoding the colons in a timestamp was the original
    bug: the encoding survived into the filename and the server decoded it
    back before looking it up, so the file was never found."""
    assert slug("/bms/overview", {"site_id": "227", "at": "2017-08-24T07:15:00"}) == (
        "bms_overview__at-2017-08-24T07-15-00__site_id-227"
    )
    # Sorted by key, so the two sides cannot disagree on ordering.
    assert slug("/ems/risk", {"scenario_id": "x", "facility_id": "1"}) == (
        "ems_risk__facility_id-1__scenario_id-x"
    )
    # Absent values are absent from the name, not spelled out.
    assert (
        slug("/ems/portfolio", {"at": None, "scenario_id": "x"}) == "ems_portfolio__scenario_id-x"
    )
    assert slug("/ems/portfolio", {"at": "None"}) == "ems_portfolio"
    assert slug("/status", None) == "status"
