"""Wire schemas shared by both modules.

These mirror ``core.common`` but are the *transport* contract: the frontend's
TypeScript types are generated against these, and every value-bearing field
carries its provenance.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.common.schemas import (
    AssetNode,
    Insight,
    KpiValue,
    Recommendation,
)
from core.enums import DataMode, Severity, SourceType
from core.provenance.model import Provenance, ProvenancedSeries


class HealthResponse(BaseModel):
    """Liveness plus a per-component verdict.

    ``components`` is the flat answer a load balancer or an operator wants:
    one word per subsystem. ``checks`` keeps the individual booleans behind
    those words, so a "degraded" is always traceable to something specific.
    """

    status: Literal["ok", "degraded"]
    version: str
    data_mode: DataMode
    building_adapter: str
    power_adapter: str
    simulation_engine: str
    models_loaded: int
    demo_cache: bool
    components: dict[str, str] = Field(default_factory=dict)
    checks: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class SystemStatus(BaseModel):
    """Contents of the demo status bar."""

    data_label: str
    data_mode: DataMode
    data_ok: bool
    ai_label: str
    ai_ok: bool
    simulation_label: str
    simulation_ok: bool
    simulation_engine: str
    interview_mode: bool
    demo_mode: bool
    source_name: str
    source_url: str | None = None
    notes: list[str] = Field(default_factory=list)


class ReplayWindow(BaseModel):
    start: datetime
    end: datetime
    step_minutes: int
    n_steps: int
    rule: str | None = None


class ChartSeries(ProvenancedSeries):
    """A chart series. Inherits timestamps/values/provenance validation."""


class KpiResponse(BaseModel):
    kpis: list[KpiValue]


class InsightResponse(BaseModel):
    asset_id: str
    window: ReplayWindow
    insights: list[Insight]
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
    detector: dict[str, Any] = Field(default_factory=dict)


class RecommendationResponse(BaseModel):
    recommendations: list[Recommendation]


class AssetTreeResponse(BaseModel):
    root: AssetNode
    generated_at: datetime


class DataQualityResponse(BaseModel):
    asset_id: str
    report: dict[str, Any]
    source: dict[str, Any]


class ProvenanceEnvelope(BaseModel):
    """Generic wrapper used where a single number needs a badge."""

    value: float | None
    unit: str | None
    display: str | None = None
    status: Severity = Severity.INFO
    provenance: Provenance


class ModelCardResponse(BaseModel):
    asset_id: str
    card: dict[str, Any]
    served_by: Literal["model", "seasonal_naive"]
    gate_reason: str


__all__ = [
    "AssetTreeResponse",
    "ChartSeries",
    "DataQualityResponse",
    "HealthResponse",
    "InsightResponse",
    "KpiResponse",
    "ModelCardResponse",
    "ProvenanceEnvelope",
    "RecommendationResponse",
    "ReplayWindow",
    "SourceType",
    "SystemStatus",
]
