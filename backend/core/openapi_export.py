"""Deterministic settings payload for OpenAPI schema export.

This module must not import ``Settings`` or construct the application.
``export_openapi`` installs these values into ``os.environ`` before any
``backend.core.config`` import so schema generation never needs a local
``.env``, PostgreSQL, Redis, MinIO, or external AI providers.
"""

from __future__ import annotations

import os
from typing import Any

# String form used for env installation (CI / exporter).
OPENAPI_EXPORT_ENV: dict[str, str] = {
    "APP_ENV": "dev",
    "APP_NAME": "fullstack-app",
    "LOG_TO_FILE": "false",
    "LOG_TO_CONSOLE": "false",
    "OTEL_TRACES_EXPORTER": "none",
    "DATABASE_URL": "postgresql+asyncpg://openapi:openapi@127.0.0.1:5432/openapi",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "JWT_SECRET": "openapi-export-only-not-for-production",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "REFRESH_TOKEN_EXPIRE_DAYS": "7",
    "CELERY_BROKER_URL": "redis://127.0.0.1:6379/1",
    "CELERY_RESULT_BACKEND": "redis://127.0.0.1:6379/2",
    "CELERY_TASK_ALWAYS_EAGER": "true",
    "STORAGE_ENDPOINT_URL": "http://127.0.0.1:9000",
    "STORAGE_ACCESS_KEY": "openapi",
    "STORAGE_SECRET_KEY": "openapi",
    "STORAGE_BUCKET": "openapi",
    "STORAGE_AUTO_CREATE_BUCKET": "false",
    "REQUIRE_EMAIL_VERIFICATION": "false",
    "RAG_VECTOR_BACKEND": "pgvector",
    "RAG_EMBEDDING_PROVIDER": "local",
    "RAG_EMBEDDING_DIMENSIONS": "1536",
    "AI_DEFAULT_PROVIDER": "local",
    "AI_EMBEDDING_PROVIDER": "local",
    "PLATFORM_DEFAULT_MODULE_PACK": "full_platform",
}


def openapi_export_settings_kwargs() -> dict[str, Any]:
    """Typed kwargs for ``Settings.for_openapi_export()`` / ``Settings(_env_file=None, ...)``."""

    return {
        "APP_ENV": "dev",
        "APP_NAME": "fullstack-app",
        "LOG_TO_FILE": False,
        "LOG_TO_CONSOLE": False,
        "OTEL_TRACES_EXPORTER": "none",
        "DATABASE_URL": OPENAPI_EXPORT_ENV["DATABASE_URL"],
        "REDIS_URL": OPENAPI_EXPORT_ENV["REDIS_URL"],
        "JWT_SECRET": OPENAPI_EXPORT_ENV["JWT_SECRET"],
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
        "CELERY_BROKER_URL": OPENAPI_EXPORT_ENV["CELERY_BROKER_URL"],
        "CELERY_RESULT_BACKEND": OPENAPI_EXPORT_ENV["CELERY_RESULT_BACKEND"],
        "CELERY_TASK_ALWAYS_EAGER": True,
        "STORAGE_ENDPOINT_URL": OPENAPI_EXPORT_ENV["STORAGE_ENDPOINT_URL"],
        "STORAGE_ACCESS_KEY": "openapi",
        "STORAGE_SECRET_KEY": "openapi",
        "STORAGE_BUCKET": "openapi",
        "STORAGE_AUTO_CREATE_BUCKET": False,
        "REQUIRE_EMAIL_VERIFICATION": False,
        "RAG_VECTOR_BACKEND": "pgvector",
        "RAG_EMBEDDING_PROVIDER": "local",
        "RAG_EMBEDDING_DIMENSIONS": 1536,
        "AI_DEFAULT_PROVIDER": "local",
        "AI_EMBEDDING_PROVIDER": "local",
        "PLATFORM_DEFAULT_MODULE_PACK": "full_platform",
    }


def install_openapi_export_env(*, force: bool = True) -> None:
    """Install OpenAPI export env vars before importing application modules.

    ``force=True`` (default) overwrites so a developer ``.env`` cannot make
    schema generation non-deterministic for required keys.
    """

    for key, value in OPENAPI_EXPORT_ENV.items():
        if force:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)
