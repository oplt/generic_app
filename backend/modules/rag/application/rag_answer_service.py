from __future__ import annotations

import asyncio
import logging
from time import perf_counter

from backend.lib.generation_port import AiServiceGenerationPort, GenerationPort
from backend.lib.project_access import ProjectAccessPort, SqlAlchemyProjectAccessPort
from backend.modules.identity_access.models import User
from backend.modules.memory.application.memory_service import MemoryService
from backend.modules.memory.domain.models import MemorySearchRequest
from backend.modules.memory.infrastructure.memory_config import MemoryConfig
from backend.modules.rag.application.citation_service import CitationService
from backend.modules.rag.application.rag_context_builder import RagContextBuilder
from backend.modules.rag.application.retrieval_service import RetrievalService
from backend.modules.rag.domain.models import RagAnswer
from backend.modules.rag.infrastructure import metrics
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

NO_CONTEXT_ANSWER = (
    "I could not find relevant document context for your question in the indexed documents."
)


class RagAnswerService:
    def __init__(self, db: AsyncSession, config: RagConfig | None = None):
        self.db = db
        self.config = config or RagConfig.from_settings()
        self.retrieval = RetrievalService(db, self.config)
        self.context_builder = RagContextBuilder(CitationService())
        self.repo = RagRepository(db)
        self.project_access: ProjectAccessPort = SqlAlchemyProjectAccessPort(db)
        self.memory = MemoryService(db)
        self.memory_config = MemoryConfig.from_settings()
        self.generation: GenerationPort = AiServiceGenerationPort(db)

    async def answer(
        self,
        query: str,
        *,
        user: User,
        project_id: str | None,
        run_id: str | None = None,
        agent_id: str | None = None,
        document_ids: list[str] | None = None,
        organization_id: str | None = None,
    ) -> RagAnswer:
        if not self.config.enabled:
            raise HTTPException(status_code=503, detail="RAG is disabled")

        user_id = user.id
        if project_id:
            await self.project_access.ensure_project_access(user_id, project_id)

        started = perf_counter()
        filters = {"document_ids": document_ids} if document_ids else None

        async def _load_memory_context() -> tuple[str, bool]:
            if not self.memory_config.enabled:
                return "", False
            try:
                return await self.memory.build_prompt_context_with_status(
                    MemorySearchRequest(
                        user_id=user_id,
                        agent_id=agent_id or "default",
                        query=query,
                        run_id=run_id,
                        project_id=project_id,
                    )
                )
            except Exception:
                logger.exception("Memory context degraded during RAG answer")
                return "", True

        retrieval_outcome, (memory_context, memory_degraded) = await asyncio.gather(
            self.retrieval.retrieve(
                query,
                user_id=user_id,
                project_id=project_id,
                filters=filters,
            ),
            _load_memory_context(),
        )
        chunks = retrieval_outcome.chunks
        retrieval_degraded = retrieval_outcome.degraded
        degradation_reason = retrieval_outcome.degradation_reason
        if memory_degraded and not degradation_reason:
            degradation_reason = "memory_recall_failed"
        bounded_chunks = self.context_builder.trim_chunks_to_token_budget(
            chunks,
            max_tokens=self.config.max_context_tokens,
        )
        citations = self.context_builder.citations.build_citations(bounded_chunks)
        document_context = self.context_builder.build_document_context_block(bounded_chunks)

        if not bounded_chunks:
            latency_ms = int((perf_counter() - started) * 1000)
            metrics.rag_answer_latency_ms.observe(latency_ms)
            await self._log_query(
                user_id=user_id,
                project_id=project_id,
                organization_id=organization_id,
                query=query,
                answer=NO_CONTEXT_ANSWER,
                chunk_ids=[],
                model_name="none",
                latency_ms=latency_ms,
            )
            return RagAnswer(
                query=query,
                answer=NO_CONTEXT_ANSWER,
                citations=[],
                retrieved_chunk_ids=[],
                model_name="none",
                latency_ms=latency_ms,
                no_context_found=True,
                ai_run_id=None,
                retrieval_degraded=retrieval_degraded,
                memory_degraded=memory_degraded,
                degradation_reason=degradation_reason,
            )

        reference_context = self.context_builder.assemble_agent_system_context(
            memory_context=memory_context or None,
            document_context=document_context,
        ) or ""
        chunk_ids = [c.chunk_id for c in bounded_chunks]

        ai_run = await self.generation.run_rag_answer(
            user,
            query=query,
            combined_context=reference_context,
            retrieved_chunk_ids=chunk_ids,
        )

        latency_ms = int((perf_counter() - started) * 1000)
        metrics.rag_answer_latency_ms.observe(latency_ms)

        await self._log_query(
            user_id=user_id,
            project_id=project_id,
            organization_id=organization_id,
            query=query,
            answer=ai_run.output_text or "",
            chunk_ids=chunk_ids,
            model_name=ai_run.model_name,
            latency_ms=latency_ms,
        )

        return RagAnswer(
            query=query,
            answer=ai_run.output_text or "",
            citations=citations,
            retrieved_chunk_ids=chunk_ids,
            model_name=ai_run.model_name,
            latency_ms=latency_ms,
            no_context_found=False,
            ai_run_id=ai_run.id,
            retrieval_degraded=retrieval_degraded,
            memory_degraded=memory_degraded,
            degradation_reason=degradation_reason,
        )

    async def _log_query(
        self,
        *,
        user_id: str,
        project_id: str | None,
        organization_id: str | None,
        query: str,
        answer: str,
        chunk_ids: list[str],
        model_name: str,
        latency_ms: int,
    ) -> None:
        await self.repo.create_query_record(
            user_id=user_id,
            project_id=project_id,
            organization_id=organization_id,
            query=query,
            answer=answer,
            retrieved_chunk_ids=chunk_ids,
            model_name=model_name,
            latency_ms=latency_ms,
        )
        await self.db.commit()
