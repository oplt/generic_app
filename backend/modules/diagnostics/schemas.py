from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

OperationalState = Literal["healthy", "degraded", "unavailable", "not_required", "unknown"]


class DiagnosticsSection(BaseModel):
    state: OperationalState = "unknown"
    detail: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class AiProviderDiagnostics(BaseModel):
    key: str
    label: str
    configured: bool
    state: OperationalState
    detail: str
    supports_generation: bool = False
    supports_embeddings: bool = False
    latency_summary_ms: float | None = None


class DiagnosticsResponse(BaseModel):
    generated_at: str
    overall_state: OperationalState
    application: DiagnosticsSection
    postgresql: DiagnosticsSection
    redis: DiagnosticsSection
    celery: DiagnosticsSection
    storage: DiagnosticsSection
    ai_providers: list[AiProviderDiagnostics] = Field(default_factory=list)
    rag: DiagnosticsSection
    observability_hints: dict[str, Any] = Field(default_factory=dict)
