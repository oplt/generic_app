"""Export FastAPI OpenAPI schema for frontend TypeScript client generation.

Usage (from repo root):

    UV_CACHE_DIR=/tmp/generic-app-uv PYTHONPATH=. \\
      uv run --project backend python -m backend.scripts.export_openapi

Writes ``frontend/openapi/openapi.json`` by default.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def export_openapi(output: Path) -> dict:
    # Install deterministic env BEFORE importing Settings / the app so schema
    # generation never depends on a local .env or live infrastructure.
    from backend.core.openapi_export import install_openapi_export_env

    install_openapi_export_env(force=True)

    from backend.api.main import create_app

    application = create_app(include_lifespan=False)
    schema = application.openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return schema


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "frontend" / "openapi" / "openapi.json",
        help="Destination OpenAPI JSON path",
    )
    args = parser.parse_args(argv)
    schema = export_openapi(args.output.resolve())
    paths = len(schema.get("paths") or {})
    print(f"Wrote OpenAPI schema ({paths} paths) → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
