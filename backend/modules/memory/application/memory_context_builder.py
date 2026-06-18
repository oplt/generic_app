from __future__ import annotations

from backend.modules.memory.application.memory_consolidator import MemoryConsolidator
from backend.modules.memory.domain.enums import MemoryLevel
from backend.modules.memory.domain.models import MemoryItem, MemorySearchRequest
from backend.modules.memory.infrastructure.mem0_client import MEMORY_CONTEXT_HEADER
from backend.modules.memory.infrastructure.metrics import retrieved_memory_count

RETRIEVAL_ORDER: tuple[MemoryLevel, ...] = (
    MemoryLevel.USER,
    MemoryLevel.PROJECT,
    MemoryLevel.SESSION,
    MemoryLevel.AGENT,
    MemoryLevel.EPISODIC,
)

LEVEL_WEIGHTS: dict[MemoryLevel, float] = {
    MemoryLevel.USER: 1.0,
    MemoryLevel.PROJECT: 0.95,
    MemoryLevel.SESSION: 0.85,
    MemoryLevel.AGENT: 0.75,
    MemoryLevel.EPISODIC: 0.65,
}


class MemoryContextBuilder:
    def __init__(
        self,
        memory_service: MemoryServiceProtocol,
        consolidator: MemoryConsolidator | None = None,
    ):
        self.memory_service = memory_service
        self.consolidator = consolidator or MemoryConsolidator()

    async def build_context_block(self, request: MemorySearchRequest) -> str:
        items = await self.recall_ranked(request)
        retrieved_memory_count.inc(len(items))
        if not items:
            return ""

        lines: list[str] = [MEMORY_CONTEXT_HEADER]
        for index, item in enumerate(items, start=1):
            citation = f"[memory:{item.id}]"
            level = item.metadata.memory_level.value
            lines.append(f"{index}. {citation} ({level}) {item.content}")
        return "\n".join(lines)

    async def recall_ranked(self, request: MemorySearchRequest) -> list[MemoryItem]:
        levels = request.memory_levels or list(RETRIEVAL_ORDER)
        ordered_levels = [level for level in RETRIEVAL_ORDER if level in levels]
        collected: list[MemoryItem] = []
        for level in ordered_levels:
            level_items = await self.memory_service.recall(
                user_id=request.user_id,
                agent_id=request.agent_id,
                query=request.query,
                run_id=request.run_id,
                project_id=request.project_id,
                memory_levels=[level],
                limit=request.limit,
            )
            collected.extend(level_items)

        deduped = self.consolidator.consolidate(collected)
        deduped = self.consolidator.mark_contradictions(deduped)
        deduped.sort(key=self._rank_score, reverse=True)
        return deduped[: request.limit]


    def _rank_score(self, item: MemoryItem) -> float:
        level_weight = LEVEL_WEIGHTS.get(item.metadata.memory_level, 0.5)
        relevance = item.score or 0.5
        confidence = item.metadata.confidence or 0.5
        recency = 0.0
        seen = item.metadata.last_seen_at or item.metadata.created_at
        if seen:
            recency = min(1.0, seen.timestamp() / 1_000_000_000)
        return (level_weight * 0.4) + (relevance * 0.35) + (confidence * 0.15) + (recency * 0.1)


class MemoryServiceProtocol:
    async def recall(
        self,
        *,
        user_id: str,
        agent_id: str,
        query: str,
        run_id: str | None = None,
        project_id: str | None = None,
        memory_levels: list[MemoryLevel] | None = None,
        limit: int = 10,
    ) -> list[MemoryItem]: ...
