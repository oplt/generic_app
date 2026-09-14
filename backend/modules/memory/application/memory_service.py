from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.pagination import MAX_PAGE_LIMIT
from backend.lib.memory_search_cache import (
    get_cached_memory_search,
    invalidate_memory_search_cache,
    set_cached_memory_search,
)
from backend.lib.project_access import ProjectAccessPort, SqlAlchemyProjectAccessPort
from backend.modules.memory.application.memory_authorization import MemoryAuthorization
from backend.modules.memory.application.memory_consolidator import MemoryConsolidator
from backend.modules.memory.application.memory_context_builder import MemoryContextBuilder
from backend.modules.memory.application.memory_extractor import (
    EXTRACTION_POLICY_VERSION,
    MemoryExtractor,
)
from backend.modules.memory.application.memory_policy_service import MemoryPolicyService
from backend.modules.memory.application.memory_router import MemoryRouter
from backend.modules.memory.domain.enums import (
    MemoryLevel,
    MemoryOperation,
    MemoryPrivacy,
    MemorySource,
    MemoryType,
)
from backend.modules.memory.domain.models import (
    MemoryItem,
    MemoryMetadata,
    MemorySearchRequest,
    MemoryWriteResult,
)
from backend.modules.memory.domain.policies import session_expires_at
from backend.modules.memory.infrastructure import metrics
from backend.modules.memory.infrastructure.mem0_client import Mem0Client
from backend.modules.memory.infrastructure.memory_audit_repository import (
    MemoryAuditRepository,
    MemoryRegistryRepository,
)
from backend.modules.memory.infrastructure.memory_config import MemoryConfig

logger = logging.getLogger(__name__)


_MEMORY_WRITE_CONCURRENCY = 3


class MemoryService:
    def __init__(self, db: AsyncSession, config: MemoryConfig | None = None):
        self.db = db
        self.config = config or MemoryConfig.from_settings()
        self.mem0 = Mem0Client(self.config)
        self.audit_repo = MemoryAuditRepository(db)
        self.registry_repo = MemoryRegistryRepository(db)
        self._project_access: ProjectAccessPort = SqlAlchemyProjectAccessPort(db)
        self.authorization = MemoryAuthorization(self._project_access)
        self.policy = MemoryPolicyService(self.config.min_confidence)
        self.router = MemoryRouter()
        self.extractor = MemoryExtractor(self.router)
        self.consolidator = MemoryConsolidator()
        self.context_builder = MemoryContextBuilder(self)

    @property
    def project_access(self) -> ProjectAccessPort:
        return self._project_access

    @project_access.setter
    def project_access(self, value: ProjectAccessPort) -> None:
        self._project_access = value
        if hasattr(self, "authorization"):
            self.authorization.project_access = value

    async def remember(
        self,
        *,
        user_id: str,
        agent_id: str,
        content: str,
        memory_level: str,
        run_id: str | None = None,
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        memory_type: str | None = None,
        source: str = MemorySource.CHAT.value,
        source_ref: str | None = None,
        confidence: float = 0.8,
        privacy: str = MemoryPrivacy.NORMAL.value,
        skip_policy: bool = False,
    ) -> MemoryWriteResult:
        if not self.config.enabled:
            return MemoryWriteResult(
                memory_id="",
                memory_level=MemoryLevel(memory_level),
                memory_type=MemoryType(memory_type or MemoryType.FACT.value),
                accepted=False,
                rejection_reason="memory_disabled",
            )

        if not self.config.write_enabled:
            return MemoryWriteResult(
                memory_id="",
                memory_level=MemoryLevel(memory_level),
                memory_type=MemoryType(memory_type or MemoryType.FACT.value),
                accepted=False,
                rejection_reason="memory_write_disabled",
            )

        level = MemoryLevel(memory_level)
        mtype = MemoryType(memory_type or MemoryType.FACT.value)
        privacy_level = MemoryPrivacy(privacy)

        await self.authorization.authorize_write(
            user_id=user_id,
            memory_level=level,
            project_id=project_id,
        )

        if not skip_policy:
            decision = self.policy.evaluate(
                content=content,
                memory_level=level,
                memory_type=mtype,
                confidence=confidence,
                privacy=privacy_level,
            )
            if not decision.allowed:
                metrics.rejected_memory_count.labels(reason=decision.reason or "unknown").inc()
                return MemoryWriteResult(
                    memory_id="",
                    memory_level=level,
                    memory_type=mtype,
                    accepted=False,
                    rejection_reason=decision.reason,
                )
            confidence = decision.adjusted_confidence or confidence
            privacy_level = decision.privacy

        now = datetime.now(UTC)
        meta = MemoryMetadata(
            memory_level=level,
            memory_type=mtype,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            project_id=project_id,
            source=MemorySource(source),
            source_ref=source_ref,
            confidence=confidence,
            created_at=now,
            last_seen_at=now,
            privacy=privacy_level,
        )
        if level == MemoryLevel.SESSION:
            meta.expires_at = session_expires_at(self.config.session_ttl_days)

        merged_meta = {**meta.to_dict(), **(metadata or {})}
        external_id = ""
        try:
            result = await self.mem0.add(
                content=content,
                memory_level=level,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                project_id=project_id,
                metadata=merged_meta,
            )
            external_id = self._extract_memory_id(result)
            metrics.memory_add_success.inc()
        except Exception:
            metrics.memory_add_failure.inc()
            logger.exception("Mem0 add failed for user=%s level=%s", user_id, level.value)
            return MemoryWriteResult(
                memory_id="",
                memory_level=level,
                memory_type=mtype,
                accepted=False,
                rejection_reason="mem0_unavailable",
            )

        if external_id:
            await self.registry_repo.register(
                external_memory_id=external_id,
                user_id=user_id if level != MemoryLevel.AGENT else user_id,
                agent_id=agent_id,
                run_id=run_id,
                project_id=project_id,
                memory_level=level.value,
                memory_type=mtype.value,
            )
            await invalidate_memory_search_cache(user_id=user_id)

        if self.config.audit_enabled:
            await self.audit_repo.log_operation(
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                project_id=project_id,
                operation=MemoryOperation.ADD,
                external_memory_id=external_id or None,
                memory_level=level.value,
                memory_type=mtype.value,
                metadata=merged_meta,
                source_ref=source_ref,
            )
            await self.db.commit()

        return MemoryWriteResult(
            memory_id=external_id or str(uuid4()),
            memory_level=level,
            memory_type=mtype,
            accepted=bool(external_id),
            rejection_reason=None if external_id else "mem0_empty_response",
        )

    async def recall(
        self,
        *,
        user_id: str,
        agent_id: str,
        query: str,
        run_id: str | None = None,
        project_id: str | None = None,
        memory_levels: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MemoryItem]:
        if not self.config.enabled:
            return []

        resolved_limit = limit or self.config.default_limit
        levels = [MemoryLevel(level) for level in memory_levels] if memory_levels else None
        if project_id:
            await self.authorization.ensure_project_access(user_id, project_id)

        level_values = (
            [level.value for level in levels] if levels else [level.value for level in MemoryLevel]
        )
        cached = await get_cached_memory_search(
            user_id=user_id,
            agent_id=agent_id,
            query=query,
            run_id=run_id,
            project_id=project_id,
            memory_levels=level_values,
            limit=resolved_limit,
        )
        if cached is not None:
            return cached

        collected: list[MemoryItem] = []
        search_levels = levels or list(MemoryLevel)
        started = perf_counter()

        async def _search_level(level: MemoryLevel) -> list[MemoryItem]:
            if level == MemoryLevel.PROJECT and not project_id:
                return []
            if level == MemoryLevel.SESSION and not run_id:
                return []
            items = await self.mem0.search(
                query=query,
                memory_level=level,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                project_id=project_id,
                top_k=resolved_limit,
            )
            return items

        try:
            level_results = await asyncio.wait_for(
                asyncio.gather(*[_search_level(level) for level in search_levels]),
                timeout=getattr(self.config, "recall_timeout_seconds", 2.0),
            )
            for level_items in level_results:
                collected.extend(level_items)
            collected = await self.authorization.filter_authorized_read_items(
                user_id, collected
            )
            metrics.memory_search_success.inc()
        except TimeoutError:
            metrics.memory_search_failure.inc()
            logger.warning(
                "Memory search exceeded latency budget user=%s timeout_seconds=%.2f",
                user_id,
                getattr(self.config, "recall_timeout_seconds", 2.0),
            )
            return []
        except Exception:
            metrics.memory_search_failure.inc()
            logger.exception("Mem0 search failed for user=%s", user_id)
            return []
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            metrics.memory_search_latency_ms.observe(elapsed_ms)

        logger.debug(
            "Memory search completed user=%s results=%s duration_ms=%.2f",
            user_id,
            len(collected),
            elapsed_ms,
        )

        if self.config.audit_enabled:
            await self.audit_repo.log_operation(
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                project_id=project_id,
                operation=MemoryOperation.SEARCH,
                external_memory_id=None,
                memory_level=",".join(level.value for level in search_levels),
                memory_type=None,
                metadata={"query": query, "result_count": len(collected)},
                source_ref=None,
            )
            await self.db.commit()

        consolidated = self.consolidator.consolidate(collected)
        result = consolidated[:resolved_limit]
        await set_cached_memory_search(
            user_id=user_id,
            agent_id=agent_id,
            query=query,
            run_id=run_id,
            project_id=project_id,
            memory_levels=level_values,
            limit=resolved_limit,
            items=result,
        )
        return result

    async def forget(
        self,
        *,
        user_id: str,
        memory_id: str,
        reason: str,
        is_admin: bool = False,
    ) -> None:
        registry = await self.registry_repo.get_by_external_id(memory_id)
        if not registry or registry.status != "active":
            raise HTTPException(status_code=404, detail="Memory not found")

        if registry.memory_level == "agent" and registry.user_id is None and not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only admins can forget global agent memory",
            )

        if registry.user_id and registry.user_id != user_id and not is_admin:
            raise HTTPException(status_code=403, detail="You cannot forget another user's memory")

        if registry.project_id:
            await self.authorization.ensure_project_access(user_id, registry.project_id)

        try:
            await self.mem0.delete(memory_id)
        except Exception as exc:
            logger.exception("Mem0 delete failed for memory_id=%s", memory_id)
            raise HTTPException(status_code=503, detail="Memory service unavailable") from exc

        await self.registry_repo.mark_deleted(memory_id)
        if self.config.audit_enabled:
            await self.audit_repo.log_operation(
                user_id=user_id,
                agent_id=registry.agent_id,
                run_id=registry.run_id,
                project_id=registry.project_id,
                operation=MemoryOperation.FORGET,
                external_memory_id=memory_id,
                memory_level=registry.memory_level,
                memory_type=registry.memory_type,
                metadata={"reason": reason},
                source_ref=None,
            )
            await self.db.commit()
        cache_user_id = registry.user_id or user_id
        await invalidate_memory_search_cache(user_id=cache_user_id)

    async def list_user_memories(
        self,
        *,
        user_id: str,
        memory_level: str | None = None,
        project_id: str | None = None,
        agent_id: str = "default",
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[MemoryItem], int]:
        if not self.config.enabled:
            return [], 0

        if project_id:
            await self.authorization.ensure_project_access(user_id, project_id)

        resolved_limit = limit or self.config.default_limit
        fetch_cap = min(offset + resolved_limit, MAX_PAGE_LIMIT)
        levels = [MemoryLevel(memory_level)] if memory_level else [MemoryLevel.USER]

        async def _fetch_level(level: MemoryLevel) -> list[MemoryItem]:
            rows = await self.mem0.get_all(
                memory_level=level,
                user_id=user_id,
                agent_id=agent_id,
                run_id=None,
                project_id=project_id,
                top_k=fetch_cap,
            )
            return await self.authorization.filter_authorized_read_items(user_id, rows)

        level_results = await asyncio.gather(*[_fetch_level(level) for level in levels])
        items: list[MemoryItem] = []
        for rows in level_results:
            items.extend(rows)
        consolidated = self.consolidator.consolidate(items)
        total = len(consolidated)
        page = consolidated[offset : offset + resolved_limit]
        return page, total

    async def get_memory(self, *, user_id: str, memory_id: str) -> MemoryItem:
        registry = await self.registry_repo.get_by_external_id(memory_id)
        if registry and registry.status != "active":
            raise HTTPException(status_code=404, detail="Memory not found")
        if registry and registry.user_id and registry.user_id != user_id:
            raise HTTPException(status_code=403, detail="You cannot access another user's memory")
        if registry and registry.project_id:
            await self.authorization.ensure_project_access(user_id, registry.project_id)

        item = await self.mem0.get(memory_id)
        if not item:
            raise HTTPException(status_code=404, detail="Memory not found")
        if not await self.authorization.authorize_read_item(user_id, item):
            raise HTTPException(status_code=403, detail="You cannot access this memory")
        return item

    async def build_prompt_context(self, request: MemorySearchRequest) -> str:
        context, _degraded = await self.build_prompt_context_with_status(request)
        return context

    async def build_prompt_context_with_status(
        self, request: MemorySearchRequest
    ) -> tuple[str, bool]:
        context, _items, degraded = await self.recall_for_prompt(request)
        return context, degraded

    async def recall_for_prompt(
        self, request: MemorySearchRequest
    ) -> tuple[str, list[MemoryItem], bool]:
        if not self.config.enabled:
            return "", [], False
        try:
            items = await self.context_builder.recall_ranked(request)
            return self.context_builder.format_context_block(items), items, False
        except HTTPException:
            # Authorization failures are contract errors, not provider degradation.
            raise
        except Exception:
            logger.exception("Memory recall failed for user=%s", request.user_id)
            return "", [], True

    async def process_turn_memories(
        self,
        *,
        user_id: str,
        agent_id: str,
        run_id: str | None,
        project_id: str | None,
        user_message: str,
        assistant_message: str,
        source_message_id: str | None = None,
    ) -> list[MemoryWriteResult]:
        if not self.config.enabled or not self.config.write_enabled:
            return []

        candidates = self.extractor.extract_from_turn(
            user_message=user_message,
            assistant_message=assistant_message,
            source_message_id=source_message_id,
        )
        if not candidates:
            return []
        candidates = [
            candidate
            for candidate in candidates
            if not candidate.requires_confirmation and candidate.routed.confidence >= 0.8
        ]
        if not candidates:
            logger.info("Memory candidates require explicit user confirmation")
            return []

        semaphore = asyncio.Semaphore(_MEMORY_WRITE_CONCURRENCY)

        async def _remember_candidate(candidate) -> MemoryWriteResult:
            async with semaphore:
                return await self.remember(
                    user_id=user_id,
                    agent_id=agent_id,
                    content=candidate.content,
                    memory_level=candidate.routed.memory_level.value,
                    memory_type=candidate.routed.memory_type.value,
                    run_id=run_id if candidate.routed.memory_level == MemoryLevel.SESSION else None,
                    project_id=project_id
                    if candidate.routed.memory_level == MemoryLevel.PROJECT
                    else None,
                    confidence=candidate.routed.confidence,
                    source=candidate.routed.source.value,
                    source_ref=source_message_id,
                    metadata={"extraction_policy_version": EXTRACTION_POLICY_VERSION},
                )

        return list(
            await asyncio.gather(*[_remember_candidate(candidate) for candidate in candidates])
        )

    @staticmethod
    def _extract_memory_id(result: dict[str, Any]) -> str:
        if not result:
            return ""
        if result.get("id"):
            return str(result["id"])
        results = result.get("results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict) and first.get("id"):
                return str(first["id"])
            if isinstance(first, dict) and first.get("memory_id"):
                return str(first["memory_id"])
        return str(result.get("memory_id", ""))
