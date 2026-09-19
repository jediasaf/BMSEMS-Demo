"""The common internal representation.

Source adapters normalise everything into these types, so the AI, optimisation
and simulation layers never see a source-specific field name. Replacing the
DrivenData adapter with an EcoStruxure Building Operation adapter is therefore a
change in ``core/adapters`` only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.enums import AnomalyKind, Quality, Severity, SourceType
from core.provenance.model import Provenance, ProvenancedSeries


class BuildingPoint(BaseModel):
    """One building-side observation at one instant."""

    model_config = ConfigDict(frozen=True)

    point_id: str
    asset_id: str
    zone_id: str | None = None
    metric: str
    value: float | None
    unit: str
    timestamp: datetime
    source_type: SourceType
    source_name: str
    quality: Quality = Quality.GOOD
    provenance: Provenance | None = None


class PowerPoint(BaseModel):
    """One electrical observation at one instant."""

    model_config = ConfigDict(frozen=True)

    meter_id: str
    asset_id: str
    metric: str
    value: float | None
    unit: str
    timestamp: datetime
    source_type: SourceType
    source_name: str
    quality: Quality = Quality.GOOD
    provenance: Provenance | None = None


class Prediction(BaseModel):
    """A single-step forecast with an empirical interval."""

    target: str
    asset_id: str
    timestamp: datetime
    prediction: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    model_id: str
    unit: str


class FeatureContribution(BaseModel):
    feature: str
    label: str
    contribution: float
    direction: Literal["up", "down", "flat"]
    detail: str | None = None


class Insight(BaseModel):
    """An explainable operational finding. Never asserts a cause."""

    insight_id: str
    timestamp: datetime
    asset_id: str
    zone_id: str | None = None
    module: Literal["BMS", "EMS"]
    kind: AnomalyKind
    severity: Severity
    metric: str
    unit: str
    observed: float | None
    expected: float | None
    deviation: float | None
    deviation_pct: float | None = None
    robust_z: float | None = None
    threshold: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    title: str
    description: str
    possible_causes: list[str] = Field(default_factory=list)
    recommended_next_step: str
    provenance: Provenance
    evidence: list[FeatureContribution] = Field(default_factory=list)
    linked_recommendation_id: str | None = None


class ExpectedImpact(BaseModel):
    """Estimated effect of a proposed action. Always carries its own provenance."""

    energy_kwh: float | None = None
    energy_pct: float | None = None
    peak_kw: float | None = None
    peak_pct: float | None = None
    comfort_note: str | None = None
    comfort_violation_kh: float | None = None
    provenance: Provenance
    basis: str = Field(description="How the estimate was produced, in one sentence")


class Recommendation(BaseModel):
    """A constrained, advisory control proposal."""

    recommendation_id: str
    timestamp: datetime
    asset_id: str
    zone_id: str | None = None
    module: Literal["BMS", "EMS"]
    action: str
    point: str
    current_value: float
    proposed_value: float
    unit: str
    rationale: str
    factors: list[FeatureContribution] = Field(default_factory=list)
    expected_impact: ExpectedImpact | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    mode: Literal["ADVISORY", "SIMULATION"] = "ADVISORY"
    constraints_checked: list[str] = Field(default_factory=list)
    provenance: Provenance
    simulatable: bool = True
    source_insight_id: str | None = None


class ControlAction(BaseModel):
    """A validated control request. Only ever executed against a simulator."""

    action_id: str
    asset_id: str
    zone_id: str | None = None
    point: str
    value: float
    unit: str
    mode: Literal["SIMULATION"] = "SIMULATION"
    validated: bool = False
    validation_messages: list[str] = Field(default_factory=list)


class AssetNode(BaseModel):
    """A node of the Building → Floor → Zone → Equipment → Point hierarchy."""

    node_id: str
    parent_id: str | None = None
    name: str
    kind: Literal["site", "building", "floor", "zone", "equipment", "point", "feeder"]
    metrics: dict[str, float] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    status: Severity = Severity.INFO
    #: Where this node's metrics come from. A full provenance record rather
    #: than a bare category, so the tree answers the same questions as every
    #: other value on screen -- and so a node cannot claim MEASURED while
    #: displaying a figure that was derived.
    provenance: Provenance
    has_anomaly: bool = False
    detail: str | None = None
    children: list[AssetNode] = Field(default_factory=list)


class KpiValue(BaseModel):
    """A headline number for a KPI card."""

    key: str
    label: str
    value: float | None
    unit: str | None = None
    display: str | None = None
    delta: float | None = None
    delta_label: str | None = None
    status: Severity = Severity.INFO
    provenance: Provenance
    hint: str | None = None


class SeriesPoint(BaseModel):
    timestamp: datetime
    value: float | None


TimeSeries = ProvenancedSeries


class DataQualityReport(BaseModel):
    """Contents of the data-quality drawer."""

    asset_id: str
    window_start: datetime
    window_end: datetime
    expected_samples: int
    actual_samples: int
    missing_pct: float
    duplicate_timestamps: int
    sampling_minutes: float
    timezone: str
    units: dict[str, str]
    last_timestamp: datetime | None
    outlier_count: int
    outlier_rule: str
    flatline_runs: int
    notes: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


AssetNode.model_rebuild()
