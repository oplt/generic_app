"""Admin APIs for roles and capability assignments."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.policy import catalog
from backend.modules.policy.deps import require_permission
from backend.modules.policy.repository import PolicyRepository
from backend.modules.policy.schemas import (
    EffectivePermissionsResponse,
    PermissionResponse,
    RoleAssignmentCreate,
    RoleAssignmentResponse,
    RoleResponse,
)
from backend.modules.policy.service import PolicyService

router = APIRouter()


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    _: User = Depends(require_permission(catalog.ADMIN_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    rows = await PolicyRepository(db).list_permissions()
    if rows:
        return [PermissionResponse(key=row.key, description=row.description) for row in rows]
    return [
        PermissionResponse(key=key, description=catalog.PERMISSION_DESCRIPTIONS[key])
        for key in catalog.ALL_PERMISSIONS
    ]


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    _: User = Depends(require_permission(catalog.ADMIN_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    repo = PolicyRepository(db)
    roles = await repo.list_roles()
    responses: list[RoleResponse] = []
    for role in roles:
        permissions = sorted(
            await repo.list_permission_keys_for_role_ids([role.id])
        )
        responses.append(
            RoleResponse(
                id=role.id,
                key=role.key,
                name=role.name,
                description=role.description,
                scope_type=role.scope_type,
                is_system=role.is_system,
                permissions=permissions,
            )
        )
    if responses:
        return responses
    return [
        RoleResponse(
            id=defn.key,
            key=defn.key,
            name=defn.name,
            description=defn.description,
            scope_type=defn.scope_type,
            is_system=True,
            permissions=list(defn.permissions),
        )
        for defn in catalog.ROLE_DEFINITIONS
    ]


@router.get("/users/{user_id}/role-assignments", response_model=list[RoleAssignmentResponse])
async def list_user_role_assignments(
    user_id: str,
    _: User = Depends(require_permission(catalog.ADMIN_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    rows = await PolicyRepository(db).list_assignments_for_user_detailed(user_id)
    return [
        RoleAssignmentResponse(
            id=assignment.id,
            user_id=assignment.user_id,
            role_key=role.key,
            role_name=role.name,
            scope_type=role.scope_type,
            organization_id=assignment.organization_id,
            project_id=assignment.project_id,
            created_at=assignment.created_at,
        )
        for assignment, role in rows
    ]


@router.post("/role-assignments", response_model=RoleAssignmentResponse, status_code=201)
async def assign_role(
    payload: RoleAssignmentCreate,
    admin: User = Depends(require_permission(catalog.ADMIN_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = PolicyService(db)
    assignment = await service.assign_role(
        actor=admin,
        user_id=payload.user_id,
        role_key=payload.role_key,
        organization_id=payload.organization_id,
        project_id=payload.project_id,
    )
    role = await PolicyRepository(db).get_role_by_id(assignment.role_id)
    assert role is not None
    return RoleAssignmentResponse(
        id=assignment.id,
        user_id=assignment.user_id,
        role_key=role.key,
        role_name=role.name,
        scope_type=role.scope_type,
        organization_id=assignment.organization_id,
        project_id=assignment.project_id,
        created_at=assignment.created_at,
    )


@router.delete("/role-assignments", status_code=204)
async def revoke_role(
    user_id: str = Query(...),
    role_key: str = Query(...),
    organization_id: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    admin: User = Depends(require_permission(catalog.ADMIN_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    await PolicyService(db).revoke_role(
        actor=admin,
        user_id=user_id,
        role_key=role_key,
        organization_id=organization_id,
        project_id=project_id,
    )


@router.get("/me/permissions", response_model=EffectivePermissionsResponse)
async def my_permissions(
    organization_id: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    granted = await PolicyService(db).resolve_permissions(
        current_user,
        organization_id=organization_id,
        project_id=project_id,
    )
    return EffectivePermissionsResponse(
        permissions=sorted(granted),
        organization_id=organization_id,
        project_id=project_id,
    )
