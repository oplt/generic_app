#!/usr/bin/env bash
# Export FastAPI OpenAPI + generate typed Orval clients into src/generated/.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/generic-app-uv}"

echo "==> Exporting OpenAPI schema"
uv run --project "${ROOT}/backend" python -m backend.scripts.export_openapi \
  --output "${ROOT}/frontend/openapi/openapi.json"

echo "==> Generating TypeScript client (Orval)"
cd "${ROOT}/frontend"
npx orval --config orval.config.ts

cat > "${ROOT}/frontend/src/generated/index.ts" <<'EOF'
/**
 * Generated OpenAPI TypeScript SDK (Orval).
 *
 * DO NOT EDIT files under `endpoints/`, `models/`, or `zod/` manually.
 * Regenerate with `npm run api:generate`.
 */

export * from "./models";
EOF

echo "==> Done"
