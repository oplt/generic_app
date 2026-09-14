# Frontend feature decomposition (Phase 6)

## Targets

A **view** orchestrates workflow (tabs, shells, wiring). It should not own every
table, mutation, and detail renderer.

Extract when a view mixes several of:

- query/mutation hooks
- filter/toolbars
- tables
- detail drawers
- dialogs/forms
- KPI/summary groups

Keep extracts **inside the feature directory**. Promote to `frontend/src/components/`
only when genuinely cross-feature (`InfoTooltip`, `ConfirmDialog`, `IdCell`, …).

Avoid dozens of one-use wrappers that only re-export JSX.

## Practical complexity guide

| Kind | Prefer |
| --- | --- |
| View | ~50–150 LOC orchestration |
| Hook | data + mutations only |
| Panel/table/drawer | one responsibility |

Not a hard line-limit CI gate — use judgment when responsibilities blur.

## Applied this phase

| Feature | Structure |
| --- | --- |
| `admin-rag` | views thin; hooks + Probe/Datasets/Runs + Overview/Versions (from Phase 5) |
| `admin-users` | `useAdminUsers` + `UsersDirectoryPanel` + existing Access/Roles dialogs |
| `admin-jobs` | `useAdminJobs` + Filters / Table / DetailDrawer |
| `admin-diagnostics` | SectionBlock / AiProvidersTable / ObservabilityHintsCard |

## Architectural smoke test

`frontend/src/features/viewOrchestration.test.ts` asserts primary admin views do not
import `useMutation` directly (mutations live in hooks).
