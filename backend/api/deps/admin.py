import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.policy import catalog
from backend.modules.policy.service import PolicyService

logger = logging.getLogger("backend.authz")


async def get_admin_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require ``admin.manage`` (``users.is_admin`` still grants it via policy)."""

    await PolicyService(db).authorize(current_user, catalog.ADMIN_MANAGE)
    return current_user
