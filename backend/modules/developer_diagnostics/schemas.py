from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DeveloperDiagnosticsStatus(BaseModel):
    enabled: bool
    environment: str
    grafana_base_url: str | None = None
    tempo_explore_url: str | None = None
    note: str = (
        "Per-request summaries omit bodies and credentials. Enable with "
        "DEVELOPER_DIAGNOSTICS_ENABLED=true (default false)."
    )


class DeveloperDiagnosticsRecentResponse(BaseModel):
    enabled: bool
    items: list[dict[str, Any]] = Field(default_factory=list)
