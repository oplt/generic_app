from __future__ import annotations

import logging

from backend.modules.rag.application.rag_tool import rag_search_tool
from backend.modules.rag.infrastructure.rag_config import RagConfig
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def rag_handles_prompt_retrieval() -> bool:
    return RagConfig.from_settings().enabled


async def build_agent_document_context(
    db: AsyncSession,
    *,
    query: str,
    user_id: str,
    project_id: str | None,
    top_k: int,
    document_ids: list[str] | None,
) -> str:
    config = RagConfig.from_settings()
    if not config.enabled or not query:
        return ""
    try:
        _chunks, context = await rag_search_tool(
            db,
            query=query,
            user_id=user_id,
            project_id=project_id,
            top_k=top_k,
            document_ids=document_ids,
        )
        return context
    except Exception:
        logger.exception("Agent RAG context build failed for user=%s", user_id)
        return ""
