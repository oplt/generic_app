from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User

router = APIRouter()


@router.get("/health")
async def inventory_module_health(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authenticated readiness probe for the scaffolded module."""

    _ = (current_user, db)
    return {"module": "inventory", "status": "ok"}
