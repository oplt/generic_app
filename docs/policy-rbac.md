# Policy / RBAC

Capability authorization lives in `backend/modules/policy/`.

Authentication (`identity_access`) answers who the actor is. Policy answers what
they may do.

## Capabilities

See `backend/modules/policy/catalog.py` for the stable permission keys
(`project.read`, `rag.manage`, `admin.manage`, …) and built-in roles
(`system_admin`, `org_admin`, `org_member`, `project_editor`).

## API

```python
from backend.modules.policy import authorize, catalog, require_permission

await authorize(
    db=db,
    actor=current_user,
    action=catalog.PROJECT_UPDATE,
    resource=project,
)

@router.get("/admin/...")
async def admin_only(_: User = Depends(require_permission(catalog.ADMIN_MANAGE))):
    ...
```

Effective grants combine:

1. `users.is_admin` bootstrap → all capabilities
2. Explicit `policy_role_assignments` (system / org / project scoped)
3. `organization_memberships.role` heuristics (`owner`/`admin` → org_admin perms,
   `member` → org_member perms) when an `organization_id` is in scope

Cross-tenant isolation: org/project scoped grants never apply to another
organization or project.

## Cache

Resolved permission sets are cached via `app_cache` (`namespaces.PERMISSIONS`)
with tags `permissions:user:{id}` and `permissions:org:{id}`. Assignment and
membership changes invalidate those tags.

## Admin UI / HTTP

- `GET /api/v1/policy/roles`
- `GET /api/v1/policy/permissions`
- `POST /api/v1/policy/role-assignments`
- `DELETE /api/v1/policy/role-assignments`
- `GET /api/v1/policy/me/permissions`
- `GET /api/v1/policy/users/{id}/role-assignments`

Admin Users page can assign/revoke the system `system_admin` role.

Migration: `h8d5f3b1c926_add_policy_rbac_tables.py`.
