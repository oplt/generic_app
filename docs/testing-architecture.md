# Testing architecture (Phase 8)

Architectural rules are tested explicitly — not only happy-path feature tests.
Feature onboarding: [adding-a-feature.md](adding-a-feature.md).

## Backend

| Rule | Where |
| --- | --- |
| Manifest uniqueness / graph / router keys / page keys | `backend/modules/manifests/tests/test_manifests.py`, `backend/tests/test_architecture_rules.py` |
| Capability profile resolution | `backend/modules/platform/tests/test_capability_profiles.py`, architecture rules |
| OpenAPI export / config construction | `backend/tests/test_openapi_export.py`, architecture rules |
| Permission catalog alignment | `backend/tests/test_cross_feature_integration.py`, architecture rules |
| Pagination helpers | `backend/tests/test_pagination.py` |
| Scaffold anti-legacy guarantees | `backend/tools/generic_app/tests/test_generator.py` (`ArchitectureGuaranteesTest`) |

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest \
  tests/test_architecture_rules.py \
  modules/manifests/tests/test_manifests.py \
  tests/test_openapi_export.py \
  tools/generic_app/tests/test_generator.py -q
```

## Frontend unit

| Rule | Where |
| --- | --- |
| Page registry completeness / uniqueness | `pageRegistry.test.ts`, `navigationConsistency.test.ts` |
| Module route gating | `ModuleRouteGate.test.tsx`, `ModuleRouteGate.moduleActivity.test.tsx` |
| Admin / auth gating | `ProtectedRoute.test.tsx` |
| Empty / error states | `EmptyState.test.tsx`, `QueryBoundary.test.tsx` |
| Dialog / tab a11y | `ConfirmDialog.test.tsx`, `TaskTabs.a11y.test.tsx`, `InfoTooltip.test.tsx` |
| View orchestration | `viewOrchestration.test.ts` |

```bash
cd frontend && npm test -- --run \
  src/app/pageRegistry.test.ts \
  src/app/navigationConsistency.test.ts \
  src/components/guards \
  src/components/ui/ConfirmDialog.test.tsx \
  src/components/ui/TaskTabs.a11y.test.tsx \
  src/components/ui/EmptyState.test.tsx \
  src/features/viewOrchestration.test.ts
```

## E2E

| Coverage | Spec |
| --- | --- |
| Sign-in / protected redirect | `e2e/auth-smoke.spec.ts` |
| Refresh persistence, projects, admin gate, core vs rag AI gate, 404, logout | `e2e/architecture-smoke.spec.ts` (mocked) |
| Live AI/RAG + provisioned workspace | `e2e/auth-rag.spec.ts`, `e2e/provisioned-workspace.spec.ts` (`@provisioned`) |

```bash
cd frontend && npm run test:e2e          # mocked Chromium smoke (CI)
cd frontend && npm run test:e2e:provisioned  # needs E2E_* credentials
```

Multi-profile proof: mocked core profile hides `/ai`; rag profile allows it. Live stacks should also run provisioned flows against at least one non-`full_platform` pack when available.
