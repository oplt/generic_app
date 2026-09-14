"""FastAPI helpers for capability checks."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.policy.service import PolicyService


async def authorize(
    *,
    db: AsyncSession,
    actor: User,
    action: str,
    organization_id: str | None = None,
    project_id: str | None = None,
    resource: object | None = None,
) -> None:
    """Module-level authorize matching the Phase 4 conceptual API."""

    await PolicyService(db).authorize(
        actor,
        action,
        organization_id=organization_id,
        project_id=project_id,
        resource=resource,
    )


def require_permission(
    action: str,
    *,
    organization_id_getter: Callable[..., str | None] | None = None,
    project_id_getter: Callable[..., str | None] | None = None,
):
    """Dependency factory: ``Depends(require_permission("admin.manage"))``."""

    async def _dependency(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        org_id = organization_id_getter() if organization_id_getter else None
        project_id = project_id_getter() if project_id_getter else None
        await authorize(
            db=db,
            actor=current_user,
            action=action,
            organization_id=org_id,
            project_id=project_id,
        )
        return current_user

    return _dependency
