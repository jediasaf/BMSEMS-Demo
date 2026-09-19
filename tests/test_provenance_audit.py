"""Every metric the UI shows must be able to say where it came from.

``tests/test_provenance.py`` covers the model's own validators -- that a value
cannot be *mislabelled*. This covers the other half: that a value reaching the
UI is labelled at all. The manifest lives in ``scripts/audit_provenance.py``
so the same list serves the test and the command an engineer runs by hand.
"""

from __future__ import annotations

import pytest

from scripts.audit_provenance import CLAIMS, audit, resolve


@pytest.fixture(scope="module")
def audited():
    return audit()


def test_every_audited_metric_carries_provenance(audited) -> None:
    _passes, failures = audited
    assert not failures, "\n".join(
        f"{f['metric']} at {f['where']}: {f['problem']}" for f in failures
    )


def test_the_audit_actually_looked_at_something(audited) -> None:
    """A manifest that resolves to nothing would pass silently."""
    passes, _failures = audited
    assert len(passes) >= len(CLAIMS)
    assert {entry["source_type"] for entry in passes} >= {
        "MEASURED",
        "DERIVED",
        "PREDICTED",
        "SIMULATED",
        "OPTIMISED",
        "INJECTED",
    }, "the audit should exercise the whole vocabulary"


def test_the_manifest_covers_the_metrics_the_brief_names(audited) -> None:
    passes, _failures = audited
    covered = {entry["metric"] for entry in passes}
    for metric in (
        "building load",
        "outdoor air temperature",
        "occupancy proxy",
        "expected load",
        "recommended setpoint",
        "energy and peak saving",
        "portfolio demand",
        "demand forecast",
        "transformer loading",
        "network state: loading, voltage, losses",
        "injected EV load",
        "optimisation action",
        "post-action network state",
    ):
        assert metric in covered, f"{metric} is not audited"


def test_resolver_selects_list_elements_not_the_list() -> None:
    """The bug this resolver had once: `kpis[]` returning the list itself."""
    payload = {"kpis": [{"key": "a"}, {"key": "b"}]}
    assert [node for _where, node in resolve(payload, "kpis[]")] == payload["kpis"]
    assert [node for _where, node in resolve(payload, "kpis")] == [payload["kpis"]]
    assert [node for _where, node in resolve(payload, "kpis[key=b]")] == [{"key": "b"}]
    assert resolve(payload, "missing[]") == []
