"""Developer diagnostics HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.modules.developer_diagnostics.schemas import (
    DeveloperDiagnosticsRecentResponse,
    DeveloperDiagnosticsStatus,
)
from backend.modules.identity_access.models import User
from backend.modules.policy import catalog
from backend.modules.policy.service import PolicyService
from backend.observability.request_diagnostics import is_enabled, recent_snapshots
from backend.observability.service import build_public_url

router = APIRouter(prefix="/developer/diagnostics", tags=["developer-diagnostics"])


def _links() -> tuple[str | None, str | None]:
    grafana = build_public_url(settings.GRAFANA_PUBLIC_URL)
    tempo = build_public_url(
        settings.GRAFANA_PUBLIC_URL,
        settings.GRAFANA_TEMPO_EXPLORE_PATH,
    )
    return grafana, tempo


@router.get("/status", response_model=DeveloperDiagnosticsStatus)
async def developer_diagnostics_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeveloperDiagnosticsStatus:
    grafana, tempo = _links()
    if settings.is_production:
        allowed = await PolicyService(db).has_permission(
            current_user, catalog.DIAGNOSTICS_READ
        )
        if not allowed:
            grafana, tempo = None, None
    return DeveloperDiagnosticsStatus(
        enabled=is_enabled(),
        environment=settings.APP_ENV,
        grafana_base_url=grafana,
        tempo_explore_url=tempo,
    )


@router.get("/recent", response_model=DeveloperDiagnosticsRecentResponse)
async def developer_diagnostics_recent(
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeveloperDiagnosticsRecentResponse:
    if not is_enabled():
        raise HTTPException(status_code=404, detail="Developer diagnostics disabled")
    if settings.is_production:
        await PolicyService(db).authorize(current_user, catalog.DIAGNOSTICS_READ)
    return DeveloperDiagnosticsRecentResponse(
        enabled=True,
        items=recent_snapshots(limit=limit),
    )
