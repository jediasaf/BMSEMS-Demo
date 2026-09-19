"""Serve a recorded result when the live computation cannot answer.

The two expensive paths in the product -- the zone simulation behind the
Control Lab and the flexible-load optimisation behind the Scenario Lab -- are
the ones most likely to fail in a hosted deployment, and the two an audience
is most likely to be looking at when they do. This reads the recording
``scripts/build_demo_cache.py`` produced so a failure degrades to a slightly
stale answer instead of an empty panel.

Two rules make that honest rather than convenient:

* **A recording is only served for the request it was recorded for.** The key
  includes the scenario, so a hot-day request never receives a normal-day
  recording. A miss is a miss; the error stands.
* **A served recording says so.** Its provenance becomes SIMULATION REPLAY
  naming the demo cache, the engine that originally produced it is kept in the
  processing note, and the payload carries ``served_from: "demo_cache"`` so
  the UI can put a banner on it. Nothing is presented as fresh that is not.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from core.common import paths
from core.enums import SimulationEngine
from core.provenance.model import simulated

log = logging.getLogger(__name__)

INDEX = paths.DEMO_DIR / "index.json"


@lru_cache(maxsize=1)
def _index() -> dict[str, Any]:
    if not INDEX.exists():
        return {}
    try:
        return json.loads(INDEX.read_text())
    except Exception as exc:  # pragma: no cover - a corrupt cache is a miss
        log.warning("demo cache index unreadable: %s", exc)
        return {}


def reset_cache() -> None:
    """Used by the demo-reset endpoint and by tests."""
    _index.cache_clear()
    _entry_files.cache_clear()


@lru_cache(maxsize=64)
def _entry_files() -> dict[str, str]:
    return {entry["key"]: entry["file"] for entry in _index().get("entries", [])}


def available() -> bool:
    return bool(_entry_files())


def generated_at() -> str | None:
    return _index().get("generated_at")


def load(key: str) -> dict[str, Any] | None:
    """The recording for `key`, or None. Never raises: a miss is not an error."""
    file = _entry_files().get(key)
    if not file:
        return None
    path = paths.REPO_ROOT / file
    if not path.exists():
        log.warning("demo cache lists %s but %s is missing", key, path)
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover
        log.warning("demo cache entry %s unreadable: %s", key, exc)
        return None


def as_replay(payload: dict[str, Any], *, key: str, original_engine: str | None) -> dict[str, Any]:
    """Relabel a recording as a replay before it is served.

    The values were produced by the real engine, so they are not fiction --
    but they were produced earlier, and a number on screen that claims to be
    this request's answer when it is not is the whole thing this project is
    trying not to do.
    """
    replayed = dict(payload)
    replayed["served_from"] = "demo_cache"
    replayed["recorded_at"] = generated_at()
    replayed["replay_note"] = (
        "SIMULATION REPLAY: the live computation was unavailable, so this is a "
        "recorded result produced earlier by "
        f"{original_engine or 'the same code path'}. It is not this request's "
        "own solve."
    )
    replayed["provenance"] = simulated(
        SimulationEngine.REPLAY,
        units="mixed",
        processing=(
            f"recorded result for {key}, originally produced by "
            f"{original_engine or 'the same code path'} and replayed because the "
            "live computation was unavailable"
        ),
        assumptions=[
            f"Recorded at {generated_at() or 'an unrecorded time'}.",
            "Replayed verbatim; no value was recomputed or adjusted.",
        ],
    ).model_dump(mode="json")
    return replayed
