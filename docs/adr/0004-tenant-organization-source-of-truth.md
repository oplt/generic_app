# ADR 0004: Organization as the tenant source of truth

## Status

Accepted

## Context

Personal organizations and memberships were introduced while `projects` remained
user-owned (`owner_id` only). RAG and chat rows store both `organization_id` and
`project_id`, but nothing proved those identifiers belonged together.
`SqlAlchemyProjectAccessPort.resolve_ownership_scope` combined a user's earliest
membership with a project authorized only by owner/task assignment. A multi-org
user could therefore attach documents or chat history for project A to
organization B.

Carrying two partial tenancy models is unsafe. Removing organizations would
discard sharing; leaving the split would keep authorization and cache keys
ambiguous.

## Decision

1. **Organization is the tenant boundary.** Every project belongs to exactly one
   organization (`projects.organization_id`, NOT NULL, FK to `organizations`).
2. **Project is an optional work-space selector inside a tenant.** When a
   workflow supplies `project_id`, the project's organization is authoritative.
   Clients never invent organization scope from an unrelated membership.
3. **Explicit organization selection** is allowed only for non-project workflows
   (`project_id is None`). The caller may pass `organization_id`; the server
   accepts it only when the user is an active member. Otherwise the user's
   default (earliest) membership is used.
4. **Scoped aggregates inherit the pair.** RAG documents/chunks/queries and chat
   conversations that reference a project must use that project's
   `organization_id`. Database triggers reject mismatched pairs.
5. **Access and caches follow the project tenant.** Assignee eligibility and
   corpus/list invalidation use `project.organization_id`, not the owner's
   default membership alone.

IDs are preserved. Rollout is expand → backfill → validate → contract (nullable
column, backfill, NOT NULL + FKs/triggers, then application enforcement).

## Consequences

Positive:

- One auditable tenant for projects, documents, chat, and retrieval caches
- Multi-org users cannot mix unrelated organization and project scopes
- Assignment and collaborator visibility align with the project's organization

Trade-offs:

- Creating a project requires an organization membership (auto-created personal
  org on signup covers the common case)
- Existing rows with mismatched project/org pairs are repaired during migration
- Organization deletion remains restricted while projects or scoped rows reference it

## Validation

- Unit tests for ownership-scope resolution across two organizations
- Integration matrix: multi-org user, project membership, assignment, RAG/chat
  scope, and cache invalidation keyed by project organization
