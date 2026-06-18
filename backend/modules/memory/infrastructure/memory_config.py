from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import settings


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    enabled: bool
    write_enabled: bool
    audit_enabled: bool
    default_limit: int
    min_confidence: float
    session_ttl_days: int
    mem0_mode: str
    mem0_api_key: str
    mem0_org_id: str
    mem0_project_id: str
    mem0_base_url: str
    app_id: str

    @classmethod
    def from_settings(cls) -> MemoryConfig:
        return cls(
            enabled=settings.MEMORY_ENABLED,
            write_enabled=settings.MEMORY_WRITE_ENABLED,
            audit_enabled=settings.MEMORY_AUDIT_ENABLED,
            default_limit=settings.MEMORY_DEFAULT_LIMIT,
            min_confidence=settings.MEMORY_MIN_CONFIDENCE,
            session_ttl_days=settings.MEMORY_SESSION_TTL_DAYS,
            mem0_mode=settings.MEM0_MODE,
            mem0_api_key=settings.MEM0_API_KEY,
            mem0_org_id=settings.MEM0_ORG_ID,
            mem0_project_id=settings.MEM0_PROJECT_ID,
            mem0_base_url=settings.MEM0_BASE_URL,
            app_id=settings.APP_NAME,
        )

    @property
    def is_hosted(self) -> bool:
        return self.mem0_mode in {"hosted", "self_hosted"}

    @property
    def mem0_configured(self) -> bool:
        if not self.enabled:
            return False
        if self.mem0_mode == "oss":
            return True
        return bool(self.mem0_api_key or self.mem0_base_url)
