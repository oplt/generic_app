# Frontend compact UX (Phase 5)

## Shared primitives

| Component | Use |
| --- | --- |
| `InfoTooltip` | Secondary explanations (keyboard + touch); never validation/danger |
| `SectionTitleWithHelp` | Concise heading + help icon |
| `ConfirmDialog` | Destructive / consequential confirms (no `window.confirm`) |
| `IdCell` | Human label + tooltip/copy for UUIDs |

## Page hierarchy

`PageShell` → optional KPI row (`repeat(n, minmax(0, 1fr))`) → task tabs → primary work → drawer/dialog for detail.

See also: [frontend-decomposition.md](frontend-decomposition.md) for Phase 6 extraction rules.

## Refactors this phase

- **RAG evaluation** — tabs Probe / Datasets & Cases / Runs; candidate drawer; collapsible assembled context; `useRagEvaluation`
- **RAG indexes** — tabs Overview / Versions; metadata chips; activate/rollback/validate confirms; `useRagIndexes`
- **AI Studio** — keep 6 tabs; equal 4-KPI row; shorter captions
- **Jobs** — detail drawer; cancel confirm; IdCell
- **Profile memory** — delete confirm; help on title
