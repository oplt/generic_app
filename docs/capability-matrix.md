# Capability matrix (Phase 3)

Machine-readable detail: [`capability-matrix.json`](capability-matrix.json).

Goal: separate **intentionally headless** backend capabilities from **accidental** missing UI.

## Naming reconciliation

| Backend module | Surface | Frontend |
| --- | --- | --- |
| `users` | embedded → `admin.users` | `features/admin-users` (+ Profile for self-service) |
| `policy` | embedded → `admin.users` | Admin Users **Access** tab + role dialogs |
| `memory` | embedded → `profile.settings` | Profile memory list/delete |
| `settings` | admin_facing | `features/settings-admin` (`settings.admin`) |
| `platform` | user_facing | `platform` + `platform-admin` |
| `storage` | internal | Admin Platform health chips only (no credentials) |
| `developer_diagnostics` | embedded → `app.shell` | Floating panel in `AppLayout` (not in `router.tsx`) |

## Phase 3 decisions

### Policy / RBAC

Wired under Admin Users (not a giant `/admin/access` CRUD app).

- Catalog: roles + permissions (permission **descriptions** only in tooltips)
- Assignments: system-scoped roles via `UserRolesDialog`
- `GET /me/permissions`: intentional API/self-service (no admin table)

### Memory

- End-user: list + delete on Profile when `memory` ∈ `active_modules`
- Search / write / forget / audit: intentional agent/API or diagnostic headless

### Developer diagnostics

Reachable: shell-mounted panel when `DEVELOPER_DIAGNOSTICS_ENABLED` and status reports enabled. Not a primary nav route by design.

### Storage

No user page. Compact health on `/admin/platform` via diagnostics metrics subset (`configured`, `bucket_name`, `endpoint_host`, `region`).

## Regenerating surface audit

```bash
./scripts/module-surface-audit.sh
```
