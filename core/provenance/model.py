"""The provenance record itself, plus constructors per source type.

Design rule enforced here: a caller cannot build a ``MEASURED`` record for a
source whose descriptor says it is not a real measurement, and cannot build a
``SIMULATED`` record without naming the engine that produced it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.enums import ENGINE_LABELS, Quality, SimulationEngine, SourceType
from core.provenance.sources import source

T = TypeVar("T")


class Provenance(BaseModel):
    """Where a number came from, in enough detail to be checked by hand."""

    model_config = ConfigDict(frozen=True)

    source_type: SourceType
    source_key: str = Field(description="Key into core.provenance.sources.SOURCES")
    source_name: str
    publisher: str
    field: str | None = Field(default=None, description="Source column / API point name")
    dataset_id: str | None = None
    engine: SimulationEngine | None = None
    engine_label: str | None = None
    model_id: str | None = None
    processing: str | None = Field(
        default=None, description="Human-readable transformation chain applied"
    )
    units: str | None = None
    timestamp: datetime | None = None
    quality: Quality = Quality.GOOD
    is_fixture: bool = False
    assumptions: list[str] = Field(default_factory=list)
    url: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> Provenance:
        descriptor = source(self.source_key)
        if self.source_type is SourceType.MEASURED and not descriptor.is_real_measurement:
            raise ValueError(
                f"source {self.source_key!r} is not a real measurement and cannot be "
                "tagged MEASURED"
            )
        if self.source_type is SourceType.SIMULATED and self.engine is None:
            raise ValueError("SIMULATED provenance must name the simulation engine")
        return self

    @property
    def badge(self) -> str:
        return self.source_type.value


def _base(source_key: str, **kwargs: Any) -> dict[str, Any]:
    descriptor = source(source_key)
    return {
        "source_key": source_key,
        "source_name": descriptor.name,
        "publisher": descriptor.publisher,
        "url": descriptor.url,
        "is_fixture": not descriptor.is_real_measurement and source_key == "ecotwin_fixture",
        **kwargs,
    }


def measured(
    source_key: str,
    *,
    field: str,
    units: str,
    processing: str | None = None,
    timestamp: datetime | None = None,
    quality: Quality = Quality.GOOD,
    dataset_id: str | None = None,
    notes: str | None = None,
) -> Provenance:
    """A value read from a published measurement (resampling is still MEASURED)."""
    return Provenance(
        source_type=SourceType.MEASURED,
        **_base(
            source_key,
            field=field,
            units=units,
            processing=processing,
            timestamp=timestamp,
            quality=quality,
            dataset_id=dataset_id,
            notes=notes,
        ),
    )


def derived(
    source_key: str,
    *,
    field: str | None,
    units: str,
    processing: str,
    assumptions: Sequence[str] = (),
    timestamp: datetime | None = None,
    quality: Quality = Quality.GOOD,
    notes: str | None = None,
) -> Provenance:
    """Deterministic arithmetic on measured values plus published metadata."""
    return Provenance(
        source_type=SourceType.DERIVED,
        **_base(
            source_key,
            field=field,
            units=units,
            processing=processing,
            assumptions=list(assumptions),
            timestamp=timestamp,
            quality=quality,
            notes=notes,
        ),
    )


def predicted(
    *,
    model_id: str,
    units: str,
    processing: str | None = None,
    timestamp: datetime | None = None,
    source_key: str = "lightgbm_forecast",
    notes: str | None = None,
) -> Provenance:
    return Provenance(
        source_type=SourceType.PREDICTED,
        **_base(
            source_key,
            model_id=model_id,
            units=units,
            processing=processing,
            timestamp=timestamp,
            notes=notes,
        ),
    )


def simulated(
    engine: SimulationEngine,
    *,
    units: str,
    field: str | None = None,
    processing: str | None = None,
    timestamp: datetime | None = None,
    assumptions: Sequence[str] = (),
    notes: str | None = None,
) -> Provenance:
    """A solver output. ``engine`` must be the engine that actually answered."""
    key = {
        SimulationEngine.BOPTEST: "boptest",
        SimulationEngine.ECOTWIN_RC: "ecotwin_rc",
        SimulationEngine.PANDAPOWER: "pandapower",
        SimulationEngine.REPLAY: "demo_cache",
    }[engine]
    return Provenance(
        source_type=SourceType.SIMULATED,
        engine=engine,
        engine_label=ENGINE_LABELS[engine],
        **_base(
            key,
            field=field,
            units=units,
            processing=processing,
            timestamp=timestamp,
            assumptions=list(assumptions),
            notes=notes,
        ),
    )


def optimised(
    *,
    units: str,
    processing: str,
    model_id: str | None = None,
    timestamp: datetime | None = None,
    assumptions: Sequence[str] = (),
    notes: str | None = None,
) -> Provenance:
    return Provenance(
        source_type=SourceType.OPTIMISED,
        **_base(
            "cvxpy",
            units=units,
            processing=processing,
            model_id=model_id,
            timestamp=timestamp,
            assumptions=list(assumptions),
            notes=notes,
        ),
    )


def injected(
    *,
    units: str,
    processing: str,
    scenario_id: str,
    timestamp: datetime | None = None,
    notes: str | None = None,
) -> Provenance:
    return Provenance(
        source_type=SourceType.INJECTED,
        **_base(
            "scenario_engine",
            units=units,
            processing=processing,
            dataset_id=scenario_id,
            timestamp=timestamp,
            notes=notes,
        ),
    )


def as_replay(original: Provenance, *, cache_key: str) -> Provenance:
    """Re-tag a cached result as a replay while preserving the true origin."""
    return original.model_copy(
        update={
            "processing": (
                f"{original.processing or 'computed'} → cached and replayed "
                f"(cache key {cache_key})"
            ),
            "notes": (
                (original.notes + " | " if original.notes else "")
                + "SIMULATION REPLAY: served from the precomputed demo cache; produced "
                f"by {original.engine_label or original.source_name}."
            ),
        }
    )


class ProvenancedValue(BaseModel, Generic[T]):
    """A single number plus its provenance. Used for every KPI."""

    value: T
    unit: str | None = None
    provenance: Provenance


class ProvenancedSeries(BaseModel):
    """A chart series plus the provenance that applies to all of its points."""

    series_id: str
    label: str
    unit: str | None = None
    timestamps: list[datetime] = Field(default_factory=list)
    values: list[float | None] = Field(default_factory=list)
    provenance: Provenance
    lower: list[float | None] | None = None
    upper: list[float | None] | None = None

    @model_validator(mode="after")
    def _check_lengths(self) -> ProvenancedSeries:
        if len(self.timestamps) != len(self.values):
            raise ValueError(
                f"series {self.series_id}: {len(self.timestamps)} timestamps vs "
                f"{len(self.values)} values"
            )
        for name, band in (("lower", self.lower), ("upper", self.upper)):
            if band is not None and len(band) != len(self.values):
                raise ValueError(f"series {self.series_id}: {name} band length mismatch")
        return self
