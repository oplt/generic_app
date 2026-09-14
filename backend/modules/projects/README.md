# Project permissions

Projects belong to exactly one organization (`organization_id`). That organization is the
tenant boundary for assignment, RAG corpus invalidation, and collaborator visibility.
See [ADR 0004](../../../docs/adr/0004-tenant-organization-source-of-truth.md).

| Action | Owner | Assigned user | Unassigned user |
|---|---:|---:|---:|
| List or view the project | Yes | Yes | No |
| List project tasks | Yes | Yes | No |
| Create, update, delete, or reorder tasks | Yes | No | No |

An assignment grants read access only when the assignee is active and belongs to the
project's organization. Assignment never grants project mutation authority. Requests that
cannot access or mutate a project return `404` to avoid disclosing its existence.

Creating a project stamps `organization_id` from an explicit membership selector or the
owner's default (earliest) membership. If the owner has no membership, a personal
organization is created.

Access-changing assignment mutations (`create_task` with an assignee, reassignment, unassignment,
and `delete_task`) invalidate the affected users' project-list caches after commit and bump the
project organization's RAG corpus generation so shared retrieval caches cannot outlive access.
