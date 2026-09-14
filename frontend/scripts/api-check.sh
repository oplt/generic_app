#!/usr/bin/env bash
# Fail when OpenAPI schema or generated client drift from committed artifacts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

./frontend/scripts/api-generate.sh

if ! git diff --quiet -- frontend/openapi/openapi.json frontend/src/generated; then
  echo "OpenAPI / generated client drift detected. Run npm run api:generate and commit."
  git --no-pager diff --stat -- frontend/openapi/openapi.json frontend/src/generated
  exit 1
fi

if [[ -n "$(git ls-files --others --exclude-standard -- frontend/openapi/openapi.json frontend/src/generated)" ]]; then
  echo "Untracked generated OpenAPI artifacts detected. Commit them after api:generate."
  git ls-files --others --exclude-standard -- frontend/openapi/openapi.json frontend/src/generated
  exit 1
fi

echo "OpenAPI client is up to date."
