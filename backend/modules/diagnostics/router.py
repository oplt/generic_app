"""Admin infrastructure diagnostics routes."""

from __future__ import annotations

from backend.api.deps.db import get_db
from backend.modules.diagnostics.schemas import DiagnosticsResponse
from backend.modules.diagnostics.service import DiagnosticsService
from backend.modules.identity_access.models import User
from backend.modules.policy.deps import require_permission
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("", response_model=DiagnosticsResponse)
async def get_diagnostics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("diagnostics.read")),
) -> DiagnosticsResponse:
    _ = current_user
    return await DiagnosticsService(db).collect()
