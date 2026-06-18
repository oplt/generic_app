from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from backend.modules.ai.service import AiService
from backend.modules.identity_access.models import User
from backend.modules.memory.application.memory_service import MemoryService
from backend.modules.memory.domain.models import MemorySearchRequest, WorkingMemoryContext
from backend.modules.memory.infrastructure.memory_config import MemoryConfig
from backend.modules.rag.application.rag_tool import rag_search_tool
from backend.modules.rag.infrastructure.rag_config import RagConfig
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_AGENT_ID = "default"


class AgentService:
    """
    Orchestrates authenticated AI runs with layered memory.

    User identity always comes from the authenticated User object — never from message text.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai = AiService(db)
        self.memory = MemoryService(db)
        self.config = MemoryConfig.from_settings()
        self.rag_config = RagConfig.from_settings()

    async def run_agent_prompt(
        self,
        user: User,
        *,
        prompt_template_key: str | None,
        prompt_version_id: str | None,
        variables: dict[str, Any],
        retrieval_query: str | None,
        document_ids: list[str],
        top_k: int,
        review_required: bool,
        agent_id: str = DEFAULT_AGENT_ID,
        run_id: str | None = None,
        project_id: str | None = None,
        user_message: str | None = None,
    ):
        resolved_run_id = run_id or str(uuid4())
        memory_context = ""
        rag_context = ""
        working = WorkingMemoryContext(
            user_message=user_message or str(variables.get("user_message", "")),
            run_id=resolved_run_id,
            project_id=project_id,
        )

        if self.config.enabled:
            query = retrieval_query or user_message or str(variables.get("user_message", ""))
            if query:
                try:
                    memory_context = await self.memory.build_prompt_context(
                        MemorySearchRequest(
                            user_id=user.id,
                            agent_id=agent_id,
                            query=query,
                            run_id=resolved_run_id,
                            project_id=project_id,
                        )
                    )
                    working.retrieved_memories = await self.memory.recall(
                        user_id=user.id,
                        agent_id=agent_id,
                        query=query,
                        run_id=resolved_run_id,
                        project_id=project_id,
                    )
                except Exception:
                    logger.exception(
                        "Memory recall degraded for user=%s run=%s", user.id, resolved_run_id
                    )

        if self.rag_config.enabled:
            query = retrieval_query or user_message or str(variables.get("user_message", ""))
            if query:
                try:
                    _chunks, rag_context = await rag_search_tool(
                        self.db,
                        query=query,
                        user_id=user.id,
                        project_id=project_id,
                    )
                except Exception:
                    logger.exception(
                        "RAG retrieval degraded for user=%s run=%s", user.id, resolved_run_id
                    )

        additional_context_parts = [part for part in (memory_context, rag_context) if part]
        additional_system_context = "\n\n".join(additional_context_parts) or None

        run = await self.ai.run_prompt(
            user,
            prompt_template_key=prompt_template_key,
            prompt_version_id=prompt_version_id,
            variables=variables,
            retrieval_query=retrieval_query,
            document_ids=document_ids,
            top_k=top_k,
            review_required=review_required,
            additional_system_context=additional_system_context,
        )

        if self.config.enabled and self.config.write_enabled and run.output_text:
            try:
                await self.memory.process_turn_memories(
                    user_id=user.id,
                    agent_id=agent_id,
                    run_id=resolved_run_id,
                    project_id=project_id,
                    user_message=working.user_message,
                    assistant_message=run.output_text,
                    source_message_id=run.id,
                )
            except Exception:
                logger.exception(
                    "Memory extraction degraded for user=%s run=%s", user.id, resolved_run_id
                )

        return run, resolved_run_id, working
