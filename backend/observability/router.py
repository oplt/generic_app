from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.modules.identity_access.models import User
from backend.modules.policy import catalog
from backend.modules.policy.service import PolicyService
from backend.observability.schemas import ObservabilityLinks, ObservabilityStatus
from backend.observability.service import ObservabilityService

router = APIRouter()


@router.get("/links", response_model=ObservabilityLinks)
async def get_observability_links(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ObservabilityLinks:
    allowed = await PolicyService(db).has_permission(
        current_user, catalog.DIAGNOSTICS_READ
    )
    return ObservabilityService(settings).get_links(is_admin=allowed)


@router.get("/status", response_model=ObservabilityStatus)
async def get_observability_status(
    _=Depends(get_current_user),
) -> ObservabilityStatus:
    return await ObservabilityService(settings).get_status()
