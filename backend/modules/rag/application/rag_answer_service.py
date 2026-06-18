from __future__ import annotations

import logging
from time import perf_counter

from backend.core.config import settings
from backend.modules.ai.providers import AiProviderRegistry, ProviderGenerateRequest
from backend.modules.memory.application.memory_service import MemoryService
from backend.modules.memory.domain.models import MemorySearchRequest
from backend.modules.memory.infrastructure.memory_config import MemoryConfig
from backend.modules.projects.repository import ProjectsRepository
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
        self.projects_repo = ProjectsRepository(db)
        self.memory = MemoryService(db)
        self.memory_config = MemoryConfig.from_settings()
        self.providers = AiProviderRegistry()

    async def answer(
        self,
        query: str,
        *,
        user_id: str,
        project_id: str | None,
        run_id: str | None = None,
        agent_id: str | None = None,
        document_ids: list[str] | None = None,
        organization_id: str | None = None,
    ) -> RagAnswer:
        if not self.config.enabled:
            raise HTTPException(status_code=503, detail="RAG is disabled")

        if project_id:
            project = await self.projects_repo.get_by_id_for_user(project_id, user_id)
            if not project:
                metrics.rag_permission_denied_total.inc()
                raise HTTPException(status_code=403, detail="Project access denied")

        started = perf_counter()
        filters = {"document_ids": document_ids} if document_ids else None
        chunks = await self.retrieval.retrieve(
            query,
            user_id=user_id,
            project_id=project_id,
            filters=filters,
        )
        citations = self.context_builder.citations.build_citations(chunks)
        document_context = self.context_builder.build_document_context_block(chunks)

        memory_context = ""
        if self.memory_config.enabled:
            try:
                memory_context = await self.memory.build_prompt_context(
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

        if not chunks:
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
            )

        combined_context = self.context_builder.build_combined_context(
            memory_context=memory_context or None,
            document_context=document_context,
            user_question=query,
        )

        provider = self.providers.get(settings.AI_DEFAULT_PROVIDER)
        model_name = (
            settings.OPENAI_DEFAULT_MODEL
            if provider.key == "openai"
            else settings.AI_LOCAL_MODEL_NAME
        )
        result = await provider.generate(
            ProviderGenerateRequest(
                model=model_name,
                system_prompt=(
                    "You are a helpful assistant. Answer using only the provided context "
                    "when relevant. Cite sources by filename when possible."
                ),
                user_prompt=combined_context,
                response_format="text",
                temperature=0.2,
            )
        )

        latency_ms = int((perf_counter() - started) * 1000)
        metrics.rag_answer_latency_ms.observe(latency_ms)
        chunk_ids = [c.chunk_id for c in chunks]

        await self._log_query(
            user_id=user_id,
            project_id=project_id,
            organization_id=organization_id,
            query=query,
            answer=result.output_text,
            chunk_ids=chunk_ids,
            model_name=result.model,
            latency_ms=latency_ms,
        )

        return RagAnswer(
            query=query,
            answer=result.output_text,
            citations=citations,
            retrieved_chunk_ids=chunk_ids,
            model_name=result.model,
            latency_ms=latency_ms,
            no_context_found=False,
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
