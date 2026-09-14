import json
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )
    APP_NAME: str = "fullstack-app"
    APP_ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    LOG_TO_CONSOLE: bool = True
    LOG_TO_FILE: bool = True
    LOG_FILE_PATH: str = "logs/logs.txt"
    LOG_RETENTION_DAYS: int = 1
    LOG_FORMAT: str = "json"
    SLOW_REQUEST_MS: int = 1000
    SLOW_JOB_MS: int = 5000
    SLOW_EXTERNAL_CALL_MS: int = 3000
    CORE_DOMAIN_SINGULAR: str = "Project"
    CORE_DOMAIN_PLURAL: str = "Projects"
    PLATFORM_DEFAULT_MODULE_PACK: str = "full_platform"

    DATABASE_URL: str
    REDIS_URL: str
    CACHE_ENABLED: bool = True
    CACHE_EMBEDDING_TTL_SECONDS: int = 600
    CACHE_EMBEDDING_MAX_TEXT_CHARS: int = 4000
    CACHE_EMBEDDING_BATCH_SIZE: int = 64
    CACHE_RETRIEVAL_TTL_SECONDS: int = 180
    CACHE_PLATFORM_TTL_SECONDS: int = 300
    CACHE_SETTINGS_TTL_SECONDS: int = 60
    CACHE_OBSERVABILITY_STATUS_TTL_SECONDS: int = 30
    CACHE_MEMORY_SEARCH_TTL_SECONDS: int = 60
    CACHE_QUERY_EMBEDDING_TTL_SECONDS: int = 3600
    CACHE_USER_PROFILE_TTL_SECONDS: int = 90
    CACHE_PROJECT_LIST_TTL_SECONDS: int = 30
    CACHE_CALENDAR_TTL_SECONDS: int = 60
    CACHE_USER_DIRECTORY_TTL_SECONDS: int = 60
    CACHE_PROMPT_RESOLUTION_TTL_SECONDS: int = 60
    CACHE_AI_OVERVIEW_TTL_SECONDS: int = 30
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_TASK_DEFAULT_QUEUE: str = "default"
    CELERY_EMAIL_QUEUE: str = "email"
    CELERY_INGESTION_QUEUE: str = "ingestion"
    CELERY_CLEANUP_QUEUE: str = "cleanup"
    CELERY_MEMORY_QUEUE: str = "memory"
    CELERY_EVALUATION_QUEUE: str = "evaluation"
    CELERY_AI_QUEUE: str = "ai"
    CELERY_TASK_TIME_LIMIT_SECONDS: int = 1800
    CELERY_TASK_SOFT_TIME_LIMIT_SECONDS: int = 1650
    CELERY_RESULT_EXPIRES_SECONDS: int = 3600

    JWT_SECRET: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

    FRONTEND_URL: str = "http://localhost:5173"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str | None = None
    ADMIN_SIGNUP_INVITE_CODE: str = ""
    ACCESS_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    CSRF_COOKIE_NAME: str = "csrf_token"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"
    PUBLIC_RATE_LIMIT_REQUESTS: int = 120
    PUBLIC_RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_FAILURE_LIMIT: int = 8
    AUTH_FAILURE_WINDOW_SECONDS: int = 900
    HEALTH_READY_PUBLIC: bool = False
    HEALTH_VERSION_PUBLIC: bool = False
    REQUIRE_EMAIL_VERIFICATION: bool = True

    # Email verification / password reset token TTLs (seconds)
    VERIFICATION_TOKEN_TTL: int = 86400  # 24 h
    PASSWORD_RESET_TOKEN_TTL: int = 3600  # 1 h

    # SMTP — leave empty to skip sending (useful in dev)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@example.com"
    SMTP_TLS: bool = True

    # Observability
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.2
    OTLP_ENDPOINT: str = ""  # e.g. http://localhost:4317
    OTLP_INSECURE: bool = True
    OTEL_SERVICE_NAME: str = "fastapi-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_EXPORTER_OTLP_PROTOCOL: str = "http/protobuf"
    OTEL_TRACES_EXPORTER: str = "none"
    GRAFANA_PUBLIC_URL: str = "http://localhost:3001"
    PROMETHEUS_PUBLIC_URL: str = "http://localhost:9090"
    TEMPO_PUBLIC_URL: str = "http://localhost:3200"
    GRAFANA_APP_OVERVIEW_DASHBOARD_PATH: str = "/d/fastapi-overview/fastapi-overview"
    GRAFANA_API_DASHBOARD_PATH: str = "/d/fastapi-overview/fastapi-overview"
    GRAFANA_FRONTEND_DASHBOARD_PATH: str = ""
    GRAFANA_DATABASE_DASHBOARD_PATH: str = ""
    GRAFANA_CACHE_DASHBOARD_PATH: str = ""
    GRAFANA_WORKERS_DASHBOARD_PATH: str = "/d/background-workers/background-workers"
    GRAFANA_SCHEDULED_TASKS_DASHBOARD_PATH: str = ""
    GRAFANA_ERRORS_DASHBOARD_PATH: str = "/d/fastapi-overview/fastapi-overview"
    GRAFANA_TEMPO_EXPLORE_PATH: str = "/explore"

    # Object storage (S3-compatible, e.g. AWS S3 or MinIO)
    STORAGE_BUCKET: str = ""
    STORAGE_REGION: str = "us-east-1"
    STORAGE_ENDPOINT_URL: str = ""
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_USE_SSL: bool = False
    STORAGE_FORCE_PATH_STYLE: bool = True
    STORAGE_PUBLIC_BASE_URL: str = ""
    STORAGE_AUTO_CREATE_BUCKET: bool = True
    STORAGE_PUBLIC_READ: bool = False
    STORAGE_SIGNED_URL_EXPIRES_SECONDS: int = 3600
    STORAGE_AVATAR_MAX_BYTES: int = 5 * 1024 * 1024

    AI_DEFAULT_PROVIDER: str = "local"
    AI_EMBEDDING_PROVIDER: str = "local"
    AI_LOCAL_MODEL_NAME: str = "local-heuristic"
    AI_MAX_OUTPUT_TOKENS: int = 1024
    AI_MAX_PROMPT_BYTES: int = 128 * 1024
    AI_MAX_CONTEXT_BYTES: int = 256 * 1024
    AI_MAX_CONCURRENT_PROVIDER_CALLS: int = 4
    AI_EVALUATION_CONCURRENCY: int = 3
    AI_EVALUATION_MAX_CASES: int = 1000
    AI_EVALUATION_WRITE_BATCH_SIZE: int = 50
    AI_RATE_LIMIT_REQUESTS: int = 30
    AI_RATE_LIMIT_WINDOW_SECONDS: int = 60
    AI_REQUEST_TIMEOUT_SECONDS: float = 60.0
    AI_PROVIDER_MAX_RETRIES: int = 3
    AI_PROVIDER_BACKOFF_MAX_SECONDS: float = 8.0
    AI_PROVIDER_BACKOFF_JITTER_SECONDS: float = 1.0
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_DEFAULT_MODEL: str = "gpt-4.1-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
    ANTHROPIC_DEFAULT_MODEL: str = "claude-3-5-sonnet-latest"

    # Chat and web-search rollout controls. External search remains disabled
    # until its provider and secret are explicitly configured.
    CHAT_ENABLED: bool = False
    CHAT_DEFAULT_MODE: str = "auto"
    CHAT_MAX_MESSAGE_BYTES: int = 32 * 1024
    CHAT_MAX_HISTORY_MESSAGES: int = 20
    CHAT_RETENTION_DAYS: int = 90
    CHAT_STREAM_HEARTBEAT_SECONDS: int = 15
    CHAT_PROVIDER_CONCURRENCY: int = 4
    CHAT_REQUEST_TIMEOUT_SECONDS: float = 90.0
    WEB_SEARCH_ENABLED: bool = False
    WEB_SEARCH_PROVIDER: str = ""
    WEB_SEARCH_API_KEY: str = ""
    WEB_SEARCH_BASE_URL: str = ""
    WEB_SEARCH_TIMEOUT_SECONDS: float = 8.0
    WEB_SEARCH_MAX_RESULTS: int = 5
    WEB_SEARCH_MAX_CONTENT_BYTES: int = 50 * 1024
    WEB_SEARCH_RATE_LIMIT_REQUESTS: int = 10
    WEB_SEARCH_RATE_LIMIT_WINDOW_SECONDS: int = 60
    WEB_SEARCH_DAILY_REQUESTS: int = 0
    WEB_SEARCH_CONCURRENCY: int = 4

    # Mem0 / agent memory
    MEM0_MODE: str = "hosted"
    MEM0_API_KEY: str = ""
    MEM0_ORG_ID: str = ""
    MEM0_PROJECT_ID: str = ""
    MEM0_BASE_URL: str = ""
    MEMORY_ENABLED: bool = True
    MEMORY_WRITE_ENABLED: bool = True
    MEMORY_AUDIT_ENABLED: bool = True
    MEMORY_DEFAULT_LIMIT: int = 10
    MEMORY_MIN_CONFIDENCE: float = 0.65
    MEMORY_SESSION_TTL_DAYS: int = 30
    MEMORY_RECALL_TIMEOUT_SECONDS: float = 2.0

    # RAG
    RAG_ENABLED: bool = True
    RAG_VECTOR_BACKEND: str = "pgvector"
    RAG_EMBEDDING_PROVIDER: str = ""
    RAG_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_EMBEDDING_DIMENSIONS: int = 1536
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 150
    RAG_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.3
    RAG_RERANK_ENABLED: bool = True
    RAG_RERANK_CANDIDATE_MULTIPLIER: int = 3
    RAG_MAX_CONTEXT_TOKENS: int = 6000
    RAG_ALLOWED_FILE_TYPES: str = "pdf,txt,md,docx,csv"
    RAG_MAX_FILE_BYTES: int = 10 * 1024 * 1024
    RAG_MAX_DOCUMENT_CHUNKS: int = 5000
    RAG_INGESTION_JOB_TIMEOUT_SECONDS: int = 1800
    RAG_INGESTION_MAX_ATTEMPTS: int = 3
    RAG_PARSER_TIMEOUT_SECONDS: float = 60.0
    RAG_MALWARE_SCAN_ENABLED: bool = False
    RAG_MALWARE_SCAN_PROVIDER: str = ""
    RAG_MALWARE_SCAN_API_KEY: str = ""
    RAG_MALWARE_SCAN_BASE_URL: str = ""
    RAG_MALWARE_SCAN_TIMEOUT_SECONDS: float = 10.0
    RAG_ASK_PROMPT_TEMPLATE_KEY: str = "rag-answer"
    RAG_ASK_TIMEOUT_SECONDS: float = 45.0
    CACHE_MAX_PAYLOAD_BYTES: int = 1024 * 1024

    CORS_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def allowed_origins(self) -> list[str]:
        return self.CORS_ALLOWED_ORIGINS or [self.FRONTEND_URL]

    @property
    def content_security_policy(self) -> str:
        connect_src = " ".join(dict.fromkeys(["'self'", *self.allowed_origins]))
        return (
            "default-src 'self'; "
            f"connect-src {connect_src}; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )

    @field_validator("COOKIE_SAMESITE")
    @classmethod
    def validate_cookie_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be one of: lax, strict, none")
        return normalized

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            return "INFO"
        return normalized

    @field_validator("LOG_RETENTION_DAYS")
    @classmethod
    def validate_log_retention_days(cls, value: int) -> int:
        if value < 1 or value > 365:
            return 1
        return value

    @field_validator("SLOW_REQUEST_MS")
    @classmethod
    def validate_slow_request_ms(cls, value: int) -> int:
        return value if value >= 1 else 1000

    @field_validator("SLOW_JOB_MS")
    @classmethod
    def validate_slow_job_ms(cls, value: int) -> int:
        return value if value >= 1 else 5000

    @field_validator("SLOW_EXTERNAL_CALL_MS")
    @classmethod
    def validate_slow_external_call_ms(cls, value: int) -> int:
        return value if value >= 1 else 3000

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 32 or stripped.lower() in {"replace-me", "changeme", "secret"}:
            raise ValueError("JWT_SECRET must be a high-entropy secret with at least 32 characters")
        return stripped

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_access_ttl(cls, value: int) -> int:
        if value <= 0 or value > 30:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 30")
        return value

    @field_validator("REFRESH_TOKEN_EXPIRE_DAYS")
    @classmethod
    def validate_refresh_ttl(cls, value: int) -> int:
        if value <= 0 or value > 30:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be between 1 and 30")
        return value

    @field_validator("CHAT_DEFAULT_MODE")
    @classmethod
    def validate_chat_default_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "documents", "general", "web"}:
            raise ValueError("CHAT_DEFAULT_MODE must be auto, documents, general, or web")
        return normalized

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.startswith(("'", '"')) and normalized.endswith(("'", '"')):
                normalized = normalized[1:-1].strip()
            if normalized.startswith("["):
                parsed = json.loads(normalized)
                if not isinstance(parsed, list):
                    raise ValueError(
                        "CORS_ALLOWED_ORIGINS must be a list or comma-separated string"
                    )
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in normalized.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_security_posture(self):
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is 'none'")
        if self.is_production and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be enabled in production")
        if self.is_production and any(
            origin.startswith("http://") for origin in self.allowed_origins
        ):
            raise ValueError("CORS_ALLOWED_ORIGINS/FRONTEND_URL must use https in production")
        if self.is_production and self.CELERY_TASK_ALWAYS_EAGER:
            raise ValueError("CELERY_TASK_ALWAYS_EAGER must be disabled in production")
        if (
            self.RAG_ENABLED
            and self.RAG_VECTOR_BACKEND.lower() == "pgvector"
            and self.RAG_EMBEDDING_DIMENSIONS != 1536
        ):
            raise ValueError("RAG_EMBEDDING_DIMENSIONS must match the pgvector schema (1536)")
        bounded_positive = {
            "CHAT_MAX_MESSAGE_BYTES": (self.CHAT_MAX_MESSAGE_BYTES, 1, 1024 * 1024),
            "CHAT_MAX_HISTORY_MESSAGES": (self.CHAT_MAX_HISTORY_MESSAGES, 1, 100),
            "CHAT_RETENTION_DAYS": (self.CHAT_RETENTION_DAYS, 1, 3650),
            "CHAT_STREAM_HEARTBEAT_SECONDS": (self.CHAT_STREAM_HEARTBEAT_SECONDS, 1, 300),
            "CHAT_PROVIDER_CONCURRENCY": (self.CHAT_PROVIDER_CONCURRENCY, 1, 64),
            "WEB_SEARCH_MAX_RESULTS": (self.WEB_SEARCH_MAX_RESULTS, 1, 20),
            "WEB_SEARCH_MAX_CONTENT_BYTES": (self.WEB_SEARCH_MAX_CONTENT_BYTES, 1, 1024 * 1024),
            "WEB_SEARCH_RATE_LIMIT_REQUESTS": (self.WEB_SEARCH_RATE_LIMIT_REQUESTS, 1, 1000),
            "WEB_SEARCH_RATE_LIMIT_WINDOW_SECONDS": (
                self.WEB_SEARCH_RATE_LIMIT_WINDOW_SECONDS,
                1,
                86400,
            ),
            "WEB_SEARCH_CONCURRENCY": (self.WEB_SEARCH_CONCURRENCY, 1, 64),
        }
        for name, (value, minimum, maximum) in bounded_positive.items():
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
        if not 0.1 <= self.WEB_SEARCH_TIMEOUT_SECONDS <= 60:
            raise ValueError("WEB_SEARCH_TIMEOUT_SECONDS must be between 0.1 and 60")
        if not 1 <= self.CHAT_REQUEST_TIMEOUT_SECONDS <= 3600:
            raise ValueError("CHAT_REQUEST_TIMEOUT_SECONDS must be between 1 and 3600")
        if not 0 <= self.WEB_SEARCH_DAILY_REQUESTS <= 100_000:
            raise ValueError("WEB_SEARCH_DAILY_REQUESTS must be between 0 and 100000")
        if not 0.1 <= self.RAG_PARSER_TIMEOUT_SECONDS <= 600:
            raise ValueError("RAG_PARSER_TIMEOUT_SECONDS must be between 0.1 and 600")
        if self.WEB_SEARCH_ENABLED:
            if self.WEB_SEARCH_PROVIDER.strip() != "generic_json":
                raise ValueError("WEB_SEARCH_PROVIDER must be generic_json")
            if not self.WEB_SEARCH_PROVIDER.strip():
                raise ValueError("WEB_SEARCH_PROVIDER is required when web search is enabled")
            if not self.WEB_SEARCH_API_KEY.strip():
                raise ValueError("WEB_SEARCH_API_KEY is required when web search is enabled")
            parsed_url = urlparse(self.WEB_SEARCH_BASE_URL.strip())
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValueError(
                    "WEB_SEARCH_BASE_URL must be an absolute http(s) URL when web search is enabled"
                )
            if self.is_production and parsed_url.scheme != "https":
                raise ValueError("WEB_SEARCH_BASE_URL must use https in production")
        if not 0.1 <= self.RAG_MALWARE_SCAN_TIMEOUT_SECONDS <= 60:
            raise ValueError("RAG_MALWARE_SCAN_TIMEOUT_SECONDS must be between 0.1 and 60")
        if self.RAG_MALWARE_SCAN_ENABLED:
            if self.RAG_MALWARE_SCAN_PROVIDER.strip() != "generic_json":
                raise ValueError("RAG_MALWARE_SCAN_PROVIDER must be generic_json")
            if not self.RAG_MALWARE_SCAN_API_KEY.strip():
                raise ValueError(
                    "RAG_MALWARE_SCAN_API_KEY is required when malware scanning is enabled"
                )
            parsed_url = urlparse(self.RAG_MALWARE_SCAN_BASE_URL.strip())
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                raise ValueError(
                    "RAG_MALWARE_SCAN_BASE_URL must be an absolute http(s) URL "
                    "when malware scanning is enabled"
                )
            if self.is_production and parsed_url.scheme != "https":
                raise ValueError("RAG_MALWARE_SCAN_BASE_URL must use https in production")
        if self.CHAT_DEFAULT_MODE == "web" and not self.WEB_SEARCH_ENABLED:
            raise ValueError("CHAT_DEFAULT_MODE=web requires WEB_SEARCH_ENABLED=true")
        return self


settings = Settings()
