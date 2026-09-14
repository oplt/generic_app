"""Turn-level memory extraction and write orchestration."""

from __future__ import annotations

import logging

from backend.lib.concurrency import map_concurrently
from backend.modules.memory.application.memory_extractor import EXTRACTION_POLICY_VERSION
from backend.modules.memory.domain.enums import MemoryLevel
from backend.modules.memory.domain.models import MemoryWriteResult

logger = logging.getLogger(__name__)

_MEMORY_WRITE_CONCURRENCY = 3


async def process_turn_memories(
    memory_service,
    *,
    user_id: str,
    agent_id: str,
    run_id: str | None,
    project_id: str | None,
    user_message: str,
    assistant_message: str,
    source_message_id: str | None = None,
) -> list[MemoryWriteResult]:
    if not memory_service.config.enabled or not memory_service.config.write_enabled:
        return []

    candidates = memory_service.extractor.extract_from_turn(
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

    async def _remember_candidate(candidate) -> MemoryWriteResult:
        return await memory_service.remember(
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

    results = await map_concurrently(
        candidates,
        _remember_candidate,
        limit=_MEMORY_WRITE_CONCURRENCY,
        kind="memory_write",
    )
    return [result for result in results if isinstance(result, MemoryWriteResult)]
