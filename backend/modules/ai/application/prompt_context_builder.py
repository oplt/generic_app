from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.memory.application.memory_service import MemoryService
from backend.modules.memory.domain.models import MemoryItem, MemorySearchRequest
from backend.modules.memory.infrastructure.memory_config import MemoryConfig
from backend.modules.rag.application.agent_context_service import (
    build_agent_document_context,
    rag_handles_prompt_retrieval,
)
from backend.modules.rag.application.rag_context_builder import RagContextBuilder

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentPromptContext:
    additional_system_context: str | None
    effective_retrieval_query: str | None
    retrieved_memories: list[MemoryItem]


class AgentPromptContextBuilder:
    """
    Single orchestration path for agent prompt context.

    Performs one memory recall and one document retrieval, then assembles
    system context with injection rules for both sources.
    """

    def __init__(self, db: AsyncSession, memory: MemoryService):
        self.db = db
        self.memory = memory
        self.memory_config = MemoryConfig.from_settings()
        self.rag_context_builder = RagContextBuilder()

    async def build(
        self,
        *,
        user_id: str,
        agent_id: str,
        query: str,
        run_id: str | None,
        project_id: str | None,
        retrieval_query: str | None,
        document_ids: list[str],
        top_k: int,
    ) -> AgentPromptContext:
        memory_request = MemorySearchRequest(
            user_id=user_id,
            agent_id=agent_id,
            query=query,
            run_id=run_id,
            project_id=project_id,
        )

        memory_task = self._load_memory_context(memory_request, query=query)
        document_task = self._load_document_context(
            query=query,
            user_id=user_id,
            project_id=project_id,
            top_k=top_k,
            document_ids=document_ids,
        )
        memory_result, document_result = await asyncio.gather(
            memory_task,
            document_task,
            return_exceptions=True,
        )

        memory_context = ""
        retrieved_memories: list[MemoryItem] = []
        if isinstance(memory_result, BaseException):
            logger.error(
                "Memory context degraded for user=%s run=%s: %s",
                user_id,
                run_id,
                memory_result,
            )
        else:
            memory_context, retrieved_memories = memory_result

        document_context = ""
        if isinstance(document_result, BaseException):
            logger.error(
                "Document context degraded for user=%s run=%s: %s",
                user_id,
                run_id,
                document_result,
            )
        elif isinstance(document_result, str):
            document_context = document_result

        additional_system_context = self.rag_context_builder.assemble_agent_system_context(
            memory_context=memory_context or None,
            document_context=document_context or None,
        )
        effective_retrieval_query = (
            None if rag_handles_prompt_retrieval() else retrieval_query
        )

        return AgentPromptContext(
            additional_system_context=additional_system_context,
            effective_retrieval_query=effective_retrieval_query,
            retrieved_memories=retrieved_memories,
        )

    async def _load_memory_context(
        self,
        request: MemorySearchRequest,
        *,
        query: str,
    ) -> tuple[str, list[MemoryItem]]:
        if not self.memory_config.enabled or not query:
            return "", []
        context, items, degraded = await self.memory.recall_for_prompt(request)
        if degraded:
            return "", []
        return context, items

    async def _load_document_context(
        self,
        *,
        query: str,
        user_id: str,
        project_id: str | None,
        top_k: int,
        document_ids: list[str],
    ) -> str:
        if not query:
            return ""
        return await build_agent_document_context(
            self.db,
            query=query,
            user_id=user_id,
            project_id=project_id,
            top_k=top_k,
            document_ids=document_ids or None,
        )
