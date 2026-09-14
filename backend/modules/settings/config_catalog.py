"""Static catalog for .env-backed config settings."""

from __future__ import annotations

from typing import Any

CONFIG_NOTICE = (
    "Config values are saved to backend/.env. Values read directly from"
    " `settings` update immediately, "
    "but infrastructure-bound changes may still require a backend restart."
)

DEPLOYMENT_MANAGED_CONFIG_KEYS = frozenset(
    {
        "DATABASE_URL",
        "REDIS_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "JWT_SECRET",
        "SMTP_PASSWORD",
        "STORAGE_ACCESS_KEY",
        "STORAGE_SECRET_KEY",
    }
)

DEPRECATED_CONFIG_KEY_REPLACEMENTS = {
    "AI_DOCUMENT_MAX_BYTES": "RAG_MAX_FILE_BYTES",
    "AI_DOCUMENT_CHUNK_SIZE": "RAG_CHUNK_SIZE",
    "AI_DOCUMENT_CHUNK_OVERLAP": "RAG_CHUNK_OVERLAP",
}

CONFIG_FIELD_METADATA: dict[str, dict[str, Any]] = {
    "APP_NAME": {
        "description": "Application name used by FastAPI metadata.",
        "requires_restart": True,
    },
    "APP_ENV": {"description": "Application environment name.", "requires_restart": True},
    "APP_HOST": {"description": "Backend bind host.", "requires_restart": True},
    "APP_PORT": {"description": "Backend bind port.", "requires_restart": True},
    "LOG_LEVEL": {"description": "Application log level.", "requires_restart": True},
    "CORE_DOMAIN_SINGULAR": {
        "description": "Default singular label for the core domain.",
        "requires_restart": True,
    },
    "CORE_DOMAIN_PLURAL": {
        "description": "Default plural label for the core domain.",
        "requires_restart": True,
    },
    "PLATFORM_DEFAULT_MODULE_PACK": {
        "description": (
            "Default capability profile (module pack) applied to cloned apps "
            "(core, lean_saas, rag, agent, automation_suite, client_portal, full_platform)."
        ),
        "requires_restart": True,
    },
    "DATABASE_URL": {
        "description": "Primary PostgreSQL connection string.",
        "requires_restart": True,
    },
    "DB_POOL_SIZE": {
        "description": "Base PostgreSQL connections per backend process.",
        "requires_restart": True,
    },
    "DB_MAX_OVERFLOW": {
        "description": "Temporary PostgreSQL connections above the base pool size.",
        "requires_restart": True,
    },
    "DB_POOL_TIMEOUT_SECONDS": {
        "description": "Maximum seconds to wait for a PostgreSQL pool checkout.",
        "requires_restart": True,
    },
    "DB_POOL_RECYCLE_SECONDS": {
        "description": "Maximum lifetime of a pooled PostgreSQL connection in seconds.",
        "requires_restart": True,
    },
    "DB_CONNECT_TIMEOUT_SECONDS": {
        "description": "PostgreSQL connection establishment timeout in seconds.",
        "requires_restart": True,
    },
    "DB_COMMAND_TIMEOUT_SECONDS": {
        "description": "asyncpg command timeout in seconds.",
        "requires_restart": True,
    },
    "DB_STATEMENT_TIMEOUT_MS": {
        "description": "PostgreSQL statement timeout in milliseconds.",
        "requires_restart": True,
    },
    "DB_LOCK_TIMEOUT_MS": {
        "description": "PostgreSQL lock wait timeout in milliseconds.",
        "requires_restart": True,
    },
    "DB_IDLE_IN_TRANSACTION_TIMEOUT_MS": {
        "description": "PostgreSQL idle-in-transaction timeout in milliseconds.",
        "requires_restart": True,
    },
    "OUTBOX_DISPATCH_LEASE_SECONDS": {
        "description": "Seconds before an unacknowledged outbox claim can be recovered.",
        "requires_restart": True,
    },
    "EXTERNAL_EFFECT_LEASE_SECONDS": {
        "description": "Seconds before an in-flight external effect can be reclaimed.",
        "requires_restart": True,
    },
    "REDIS_URL": {"description": "Primary Redis connection string.", "requires_restart": True},
    "CELERY_BROKER_URL": {
        "description": "Optional Celery broker URL override.",
        "requires_restart": True,
    },
    "CELERY_RESULT_BACKEND": {
        "description": "Optional Celery result backend override.",
        "requires_restart": True,
    },
    "CELERY_TASK_ALWAYS_EAGER": {
        "description": "Execute Celery tasks inline instead of queueing them.",
        "requires_restart": True,
    },
    "CELERY_TASK_DEFAULT_QUEUE": {
        "description": "Default queue name for asynchronous jobs.",
        "requires_restart": True,
    },
    "CELERY_EMAIL_QUEUE": {
        "description": "Queue name used for outbound email jobs.",
        "requires_restart": True,
    },
    "CELERY_RESULT_EXPIRES_SECONDS": {
        "description": "How long Celery task results are retained in seconds.",
        "requires_restart": True,
    },
    "JWT_SECRET": {"description": "JWT signing secret.", "requires_restart": False},
    "JWT_ALGORITHM": {"description": "JWT signing algorithm.", "requires_restart": False},
    "ACCESS_TOKEN_EXPIRE_MINUTES": {
        "description": "Access token TTL in minutes.",
        "requires_restart": False,
    },
    "REFRESH_TOKEN_EXPIRE_DAYS": {
        "description": "Refresh token TTL in days.",
        "requires_restart": False,
    },
    "FRONTEND_URL": {"description": "Frontend base URL.", "requires_restart": True},
    "COOKIE_SECURE": {
        "description": "Whether auth cookies require HTTPS.",
        "requires_restart": True,
    },
    "ADMIN_SIGNUP_INVITE_CODE": {
        "description": "Invite code required for admin registration during sign-up.",
        "requires_restart": False,
    },
    "VERIFICATION_TOKEN_TTL": {
        "description": "Email verification token TTL in seconds.",
        "requires_restart": False,
    },
    "PASSWORD_RESET_TOKEN_TTL": {
        "description": "Password reset token TTL in seconds.",
        "requires_restart": False,
    },
    "SMTP_HOST": {"description": "SMTP hostname.", "requires_restart": False},
    "SMTP_PORT": {"description": "SMTP port.", "requires_restart": False},
    "SMTP_USER": {"description": "SMTP username.", "requires_restart": False},
    "SMTP_PASSWORD": {"description": "SMTP password.", "requires_restart": False},
    "SMTP_FROM": {"description": "Email sender address.", "requires_restart": False},
    "SMTP_TLS": {"description": "Use TLS for outbound SMTP.", "requires_restart": False},
    "SENTRY_DSN": {"description": "Sentry DSN.", "requires_restart": True},
    "SENTRY_TRACES_SAMPLE_RATE": {
        "description": "Fraction of requests to trace in Sentry.",
        "requires_restart": True,
    },
    "OTLP_ENDPOINT": {
        "description": "OpenTelemetry collector endpoint.",
        "requires_restart": True,
    },
    "OTLP_INSECURE": {
        "description": "Allow insecure gRPC OTLP transport.",
        "requires_restart": True,
    },
    "STORAGE_BUCKET": {
        "description": "Object storage bucket for uploaded assets.",
        "requires_restart": True,
    },
    "STORAGE_REGION": {"description": "Object storage region.", "requires_restart": True},
    "STORAGE_ENDPOINT_URL": {
        "description": "Custom S3-compatible endpoint URL, e.g. MinIO.",
        "requires_restart": True,
    },
    "STORAGE_ACCESS_KEY": {
        "description": "Object storage access key.",
        "requires_restart": True,
    },
    "STORAGE_SECRET_KEY": {
        "description": "Object storage secret key.",
        "requires_restart": True,
    },
    "STORAGE_USE_SSL": {
        "description": "Use HTTPS for object storage traffic.",
        "requires_restart": True,
    },
    "STORAGE_FORCE_PATH_STYLE": {
        "description": "Force path-style S3 URLs; useful for MinIO.",
        "requires_restart": True,
    },
    "STORAGE_PUBLIC_BASE_URL": {
        "description": "Optional public base URL used to build asset URLs.",
        "requires_restart": True,
    },
    "STORAGE_AUTO_CREATE_BUCKET": {
        "description": "Create the storage bucket automatically on startup.",
        "requires_restart": True,
    },
    "STORAGE_PUBLIC_READ": {
        "description": "Apply a public-read policy to the storage bucket.",
        "requires_restart": True,
    },
    "STORAGE_AVATAR_MAX_BYTES": {
        "description": "Maximum avatar upload size in bytes.",
        "requires_restart": False,
    },
    "AI_DEFAULT_PROVIDER": {
        "description": "Default provider key used for AI generation.",
        "requires_restart": False,
    },
    "AI_EMBEDDING_PROVIDER": {
        "description": "Provider used for document embeddings.",
        "requires_restart": False,
    },
    "AI_LOCAL_MODEL_NAME": {
        "description": "Label used for the built-in local heuristic model.",
        "requires_restart": False,
    },
    "RAG_MAX_FILE_BYTES": {
        "description": "Maximum source document size for RAG ingestion.",
        "requires_restart": False,
    },
    "RAG_CHUNK_SIZE": {
        "description": "Chunk size in characters for RAG document ingestion.",
        "requires_restart": False,
    },
    "RAG_CHUNK_OVERLAP": {
        "description": "Chunk overlap in characters for RAG document ingestion.",
        "requires_restart": False,
    },
    "AI_MAX_OUTPUT_TOKENS": {
        "description": "Maximum output tokens requested from AI providers.",
        "requires_restart": False,
    },
    "AI_EVALUATION_CONCURRENCY": {
        "description": "Maximum number of evaluation cases to run in parallel.",
        "requires_restart": False,
    },
    "OPENAI_API_KEY": {
        "description": "OpenAI API key used by the AI provider adapter.",
        "requires_restart": False,
    },
    "OPENAI_BASE_URL": {
        "description": "Override for OpenAI-compatible API base URL.",
        "requires_restart": False,
    },
    "OPENAI_DEFAULT_MODEL": {
        "description": "Default OpenAI chat model for prompt versions.",
        "requires_restart": False,
    },
    "OPENAI_EMBEDDING_MODEL": {
        "description": "Default OpenAI embedding model.",
        "requires_restart": False,
    },
    "ANTHROPIC_API_KEY": {
        "description": "Anthropic API key used by the AI provider adapter.",
        "requires_restart": False,
    },
    "ANTHROPIC_BASE_URL": {
        "description": "Override for Anthropic API base URL.",
        "requires_restart": False,
    },
    "ANTHROPIC_DEFAULT_MODEL": {
        "description": "Default Anthropic model for prompt versions.",
        "requires_restart": False,
    },
}

TYPE_LABELS = {
    str: "string",
    int: "integer",
    bool: "boolean",
}

REDACTED_SECRET = "********"
SENSITIVE_KEY_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "KEY",
    "DSN",
    "DATABASE_URL",
    "REDIS_URL",
)
