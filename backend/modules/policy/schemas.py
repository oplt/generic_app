"""Policy admin API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PermissionResponse(BaseModel):
    key: str
    description: str


class RoleResponse(BaseModel):
    id: str
    key: str
    name: str
    description: str
    scope_type: str
    is_system: bool
    permissions: list[str] = Field(default_factory=list)


class RoleAssignmentResponse(BaseModel):
    id: str
    user_id: str
    role_key: str
    role_name: str
    scope_type: str
    organization_id: str | None
    project_id: str | None
    created_at: datetime


class RoleAssignmentCreate(BaseModel):
    user_id: str
    role_key: str
    organization_id: str | None = None
    project_id: str | None = None


class RoleAssignmentDelete(BaseModel):
    user_id: str
    role_key: str
    organization_id: str | None = None
    project_id: str | None = None


class EffectivePermissionsResponse(BaseModel):
    permissions: list[str]
    organization_id: str | None = None
    project_id: str | None = None
