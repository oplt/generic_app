"""Capability permission and built-in role catalog.

Permission keys are stable API contracts. Keep Prometheus / cache labels on these
fixed strings only (low cardinality).
"""

from __future__ import annotations

from dataclasses import dataclass

# Capability permissions (Phase 4 / prompt catalog).
PROJECT_READ = "project.read"
PROJECT_CREATE = "project.create"
PROJECT_UPDATE = "project.update"
PROJECT_DELETE = "project.delete"
RAG_READ = "rag.read"
RAG_MANAGE = "rag.manage"
USERS_MANAGE = "users.manage"
BILLING_READ = "billing.read"
BILLING_MANAGE = "billing.manage"
API_KEYS_MANAGE = "api_keys.manage"
WEBHOOKS_MANAGE = "webhooks.manage"
JOBS_READ = "jobs.read"
JOBS_RETRY = "jobs.retry"
JOBS_CANCEL = "jobs.cancel"
DIAGNOSTICS_READ = "diagnostics.read"
ADMIN_MANAGE = "admin.manage"
# <generic-app:permission-constants>
# </generic-app:permission-constants>

ALL_PERMISSIONS: tuple[str, ...] = (
    PROJECT_READ,
    PROJECT_CREATE,
    PROJECT_UPDATE,
    PROJECT_DELETE,
    RAG_READ,
    RAG_MANAGE,
    USERS_MANAGE,
    BILLING_READ,
    BILLING_MANAGE,
    API_KEYS_MANAGE,
    WEBHOOKS_MANAGE,
    JOBS_READ,
    JOBS_RETRY,
    JOBS_CANCEL,
    DIAGNOSTICS_READ,
    ADMIN_MANAGE,
    # <generic-app:permission-entries>
    # </generic-app:permission-entries>
)

SCOPE_SYSTEM = "system"
SCOPE_ORGANIZATION = "organization"
SCOPE_PROJECT = "project"

ROLE_SYSTEM_ADMIN = "system_admin"
ROLE_ORG_ADMIN = "org_admin"
ROLE_ORG_MEMBER = "org_member"
ROLE_PROJECT_EDITOR = "project_editor"


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    key: str
    name: str
    scope_type: str
    permissions: tuple[str, ...]
    description: str


ORG_MEMBER_PERMISSIONS: tuple[str, ...] = (
    PROJECT_READ,
    PROJECT_CREATE,
    RAG_READ,
    JOBS_READ,
)

ORG_ADMIN_PERMISSIONS: tuple[str, ...] = (
    *ORG_MEMBER_PERMISSIONS,
    PROJECT_UPDATE,
    PROJECT_DELETE,
    RAG_MANAGE,
    USERS_MANAGE,
    BILLING_READ,
    BILLING_MANAGE,
    API_KEYS_MANAGE,
    WEBHOOKS_MANAGE,
    JOBS_RETRY,
    JOBS_CANCEL,
    DIAGNOSTICS_READ,
)

PROJECT_EDITOR_PERMISSIONS: tuple[str, ...] = (
    PROJECT_READ,
    PROJECT_UPDATE,
    RAG_READ,
    RAG_MANAGE,
    JOBS_READ,
    JOBS_RETRY,
    JOBS_CANCEL,
)

ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        key=ROLE_SYSTEM_ADMIN,
        name="System admin",
        scope_type=SCOPE_SYSTEM,
        permissions=ALL_PERMISSIONS,
        description="Full platform capability; maps from users.is_admin bootstrap.",
    ),
    RoleDefinition(
        key=ROLE_ORG_ADMIN,
        name="Organization admin",
        scope_type=SCOPE_ORGANIZATION,
        permissions=ORG_ADMIN_PERMISSIONS,
        description="Manage projects, RAG, billing, and members inside an organization.",
    ),
    RoleDefinition(
        key=ROLE_ORG_MEMBER,
        name="Organization member",
        scope_type=SCOPE_ORGANIZATION,
        permissions=ORG_MEMBER_PERMISSIONS,
        description="Create/read projects and read RAG within an organization.",
    ),
    RoleDefinition(
        key=ROLE_PROJECT_EDITOR,
        name="Project editor",
        scope_type=SCOPE_PROJECT,
        permissions=PROJECT_EDITOR_PERMISSIONS,
        description="Update a project and manage its RAG corpus.",
    ),
)

PERMISSION_DESCRIPTIONS: dict[str, str] = {
    PROJECT_READ: "View projects and project tasks",
    PROJECT_CREATE: "Create projects",
    PROJECT_UPDATE: "Update projects and tasks",
    PROJECT_DELETE: "Delete projects",
    RAG_READ: "Search and read RAG documents",
    RAG_MANAGE: "Upload, delete, and manage RAG documents/jobs",
    USERS_MANAGE: "Manage organization members",
    BILLING_READ: "View billing and plans",
    BILLING_MANAGE: "Manage billing and plans",
    API_KEYS_MANAGE: "Manage API keys",
    WEBHOOKS_MANAGE: "Manage webhooks",
    JOBS_READ: "View background jobs",
    JOBS_RETRY: "Retry failed jobs",
    JOBS_CANCEL: "Cancel queued jobs",
    DIAGNOSTICS_READ: "View diagnostics and observability",
    ADMIN_MANAGE: "Administer platform roles and global settings",
}
