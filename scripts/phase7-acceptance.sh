#!/usr/bin/env bash
# Phase 7 acceptance harness — profile matrix, generator smoke, RAG/injection, FE gate.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/generic-app-uv}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

echo "==> 7.1 Profile matrix + cross-feature"
uv run --project backend pytest -q \
  backend/modules/platform/tests/test_capability_profiles.py \
  backend/tests/test_cross_feature_integration.py \
  backend/tests/test_phase7_acceptance.py

echo "==> 7.2 Generator smoke (orders golden + wiring)"
uv run --project backend pytest -q backend/tools/generic_app/tests

echo "==> 7.3/7.4 RAG lifecycle + failure injection"
uv run --project backend pytest -q \
  backend/modules/rag/tests/test_index_versions.py \
  backend/modules/rag/tests/test_hybrid_search.py \
  backend/modules/rag/tests/test_retrieval.py \
  backend/modules/rag/tests/test_evaluation_workbench.py \
  backend/tests/test_failure_injection_resilience.py \
  backend/tests/test_idempotency.py

echo "==> Frontend gate + API contract"
cd frontend
npm run test -- src/components/guards/ModuleRouteGate.test.tsx src/api/rawApiPathGuard.test.ts
cd "${ROOT}"

echo "Phase 7 acceptance suite passed."
echo "Recorded baselines: docs/acceptance-baselines.md"
echo "Load/pool commands (do not invent numbers): see docs/database-pool-capacity.md"
