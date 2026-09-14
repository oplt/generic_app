"""Export FastAPI OpenAPI schema for frontend TypeScript client generation.

Usage (from repo root):

    UV_CACHE_DIR=/tmp/generic-app-uv PYTHONPATH=. \\
      uv run --project backend python -m backend.scripts.export_openapi

Writes ``frontend/openapi/openapi.json`` by default.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _ensure_minimal_settings_env() -> None:
    """Allow importing the app without a fully provisioned runtime."""

    defaults = {
        "DATABASE_URL": "postgresql+asyncpg://openapi:openapi@127.0.0.1:5432/openapi",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "JWT_SECRET": "openapi-export-only-not-for-production",
        "CELERY_BROKER_URL": "redis://127.0.0.1:6379/1",
        "CELERY_RESULT_BACKEND": "redis://127.0.0.1:6379/2",
        "STORAGE_ENDPOINT": "http://127.0.0.1:9000",
        "STORAGE_ACCESS_KEY": "openapi",
        "STORAGE_SECRET_KEY": "openapi",
        "STORAGE_BUCKET": "openapi",
        "APP_ENV": "dev",
        "LOG_TO_FILE": "false",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def export_openapi(output: Path) -> dict:
    _ensure_minimal_settings_env()
    # Import after env defaults so Settings() can construct.
    from backend.api.main import app

    schema = app.openapi()
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
