from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.errors import StructuredApiError
from backend.lib.project_access import ProjectAccessPort, SqlAlchemyProjectAccessPort
from backend.modules.chat.models import ChatConversation
from backend.modules.chat.repository import ChatRepository
from backend.modules.chat.schemas import ChatConversationCreate, ChatConversationUpdate
from backend.modules.identity_access.models import User
from backend.modules.memory.infrastructure.memory_config import MemoryConfig
from backend.modules.rag.application.document_identity import document_embedding_is_current
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository


class ConversationService:
    """Own conversation lifecycle, ownership, and response serialization."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: ChatRepository | None = None,
        project_access: ProjectAccessPort | None = None,
        memory_config: MemoryConfig | None = None,
        rag_repository: RagRepository | None = None,
    ):
        self.db = db
        self.repo = repository or ChatRepository(db)
        self.project_access = project_access or SqlAlchemyProjectAccessPort(db)
        self.memory_config = memory_config or MemoryConfig.from_settings()
        self.rag_repo = rag_repository

    async def _authorize_documents(
        self,
        user: User,
        project_id: str | None,
        document_ids: list[str],
        organization_id: str | None = None,
    ) -> list[str]:
        requested = list(dict.fromkeys(document_ids))
        if not requested or not isinstance(self.rag_repo, RagRepository):
            return requested
        if organization_id is None:
            scope = await self.project_access.resolve_ownership_scope(user.id, project_id)
            organization_id = scope.organization_id
        indexed = await self.rag_repo.list_indexed_documents(
            user.id,
            project_id=project_id,
            document_ids=requested,
            organization_id=organization_id,
        )
        config = RagConfig.from_settings()
        usable = [
            document
            for document in indexed
            if not hasattr(document, "metadata_json")
            or document_embedding_is_current(json.loads(document.metadata_json or "{}"), config)
        ]
        if len(usable) != len(requested):
            raise StructuredApiError(
                status_code=403,
                code="document_not_indexed",
                message="Selected document is not available.",
            )
        return [document.id for document in usable]

    async def create(self, user: User, payload: ChatConversationCreate) -> ChatConversation:
        mode = payload.mode or settings.CHAT_DEFAULT_MODE
        if mode == "documents" and not payload.selected_document_ids:
            raise StructuredApiError(
                status_code=422,
                code="no_documents_selected",
                message="Select at least one indexed document.",
            )
        try:
            scope = await self.project_access.resolve_ownership_scope(user.id, payload.project_id)
        except HTTPException as exc:
            raise StructuredApiError(
                status_code=exc.status_code,
                code="unauthorized" if exc.status_code == 403 else "conflict",
                message="Conversation scope is not available.",
            ) from exc
        conversation = await self.repo.create_conversation(
            user_id=user.id,
            project_id=scope.project_id,
            organization_id=scope.organization_id,
            title=payload.title or "New knowledge chat",
            mode=mode,
            selected_document_ids=await self._authorize_documents(
                user,
                scope.project_id,
                payload.selected_document_ids,
                scope.organization_id,
            ),
            memory_enabled=(
                False
                if mode == "documents"
                else self.memory_config.enabled
                and (True if payload.memory_enabled is None else payload.memory_enabled)
            ),
            memory_write_enabled=(
                False
                if mode == "documents"
                else self.memory_config.enabled
                and self.memory_config.write_enabled
                and (True if payload.memory_write_enabled is None else payload.memory_write_enabled)
            ),
        )
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def list(
        self,
        user: User,
        *,
        project_id: str | None = None,
        limit: int,
        offset: int = 0,
        cursor: str | None = None,
    ) -> tuple[list[ChatConversation], int | None, str | None, bool]:
        if cursor:
            (
                conversations,
                next_cursor,
                has_more,
            ) = await self.repo.list_conversations_for_user_cursor(
                user.id,
                project_id=project_id,
                limit=limit,
                cursor=cursor,
            )
            return conversations, None, next_cursor, has_more
        conversations, total = await self.repo.list_conversations_for_user(
            user.id,
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
        return conversations, total, None, False

    async def get(self, user: User, conversation_id: str) -> ChatConversation:
        conversation = await self.repo.get_conversation_for_user(user.id, conversation_id)
        if not conversation:
            raise StructuredApiError(
                status_code=404,
                code="not_found",
                message="Conversation not found.",
            )
        return conversation

    async def update(
        self,
        user: User,
        conversation_id: str,
        payload: ChatConversationUpdate,
    ) -> ChatConversation:
        conversation = await self.get(user, conversation_id)
        next_mode = payload.mode or conversation.mode
        current_document_ids = self.repo.selected_document_ids(conversation)
        requested_document_ids = (
            current_document_ids
            if payload.selected_document_ids is None
            else payload.selected_document_ids
        )
        if next_mode == "documents" and not requested_document_ids:
            raise StructuredApiError(
                status_code=422,
                code="no_documents_selected",
                message="Select at least one indexed document.",
            )
        if payload.mode is not None:
            conversation.mode = next_mode
        if payload.title is not None:
            conversation.title = payload.title.strip()
        if payload.selected_document_ids is not None or payload.mode == "documents":
            authorized_document_ids = await self._authorize_documents(
                user,
                conversation.project_id,
                requested_document_ids,
                conversation.organization_id,
            )
            conversation.selected_document_ids_json = json.dumps(
                authorized_document_ids,
                ensure_ascii=True,
            )
        if payload.memory_enabled is not None:
            conversation.memory_enabled = payload.memory_enabled and self.memory_config.enabled
        if payload.memory_write_enabled is not None:
            conversation.memory_write_enabled = (
                payload.memory_write_enabled
                and self.memory_config.enabled
                and self.memory_config.write_enabled
            )
        if conversation.mode == "documents":
            conversation.memory_enabled = False
            conversation.memory_write_enabled = False
        await self.repo.touch_conversation(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def delete(self, user: User, conversation_id: str) -> None:
        conversation = await self.get(user, conversation_id)
        await self.repo.delete_conversation(conversation)
        await self.db.commit()

    async def clear(self, user: User, conversation_id: str) -> None:
        conversation = await self.get(user, conversation_id)
        await self.repo.clear_messages(conversation.id)
        await self.repo.touch_conversation(conversation)
        await self.db.commit()

    async def delete_expired(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=settings.CHAT_RETENTION_DAYS)
        deleted = await self.repo.delete_expired_conversations(cutoff)
        deleted += await self.repo.delete_expired_messages(cutoff)
        await self.db.commit()
        return deleted

    async def serialize_summary(self, conversation: ChatConversation) -> dict:
        return {
            "id": conversation.id,
            "title": conversation.title,
            "project_id": conversation.project_id,
            "mode": conversation.mode,
            "selected_document_ids": self.repo.selected_document_ids(conversation),
            "memory_enabled": conversation.memory_enabled,
            "memory_write_enabled": conversation.memory_write_enabled,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }

    async def serialize(
        self,
        conversation: ChatConversation,
        *,
        message_limit: int | None = None,
    ) -> dict:
        messages = (
            await self.repo.list_recent_messages(
                conversation.id,
                limit=message_limit,
            )
            if message_limit is not None
            else await self.repo.list_messages(conversation.id)
        )
        sources = await self.repo.list_sources_for_messages([message.id for message in messages])
        source_document_ids = list({source.document_id for source in sources if source.document_id})
        available_document_ids: set[str] = set()
        if source_document_ids and isinstance(self.rag_repo, RagRepository):
            available_document_ids = await self.rag_repo.list_available_document_ids_for_chat(
                conversation.user_id,
                source_document_ids,
                organization_id=getattr(conversation, "organization_id", None),
                project_id=conversation.project_id,
            )
        sources_by_message: dict[str, list] = {}
        for source in sources:
            sources_by_message.setdefault(source.message_id, []).append(source)
        response = await self.serialize_summary(conversation)
        response.update(
            {
                "messages": [
                    {
                        "id": message.id,
                        "role": message.role,
                        "content": message.content,
                        "mode": message.mode,
                        "document_ids": self.repo.message_document_ids(message),
                        "status": message.status,
                        "ai_run_id": message.ai_run_id,
                        "model_name": message.model_name,
                        "route_reason": message.route_reason,
                        "route_confidence": message.route_confidence,
                        "input_tokens": message.input_tokens,
                        "output_tokens": message.output_tokens,
                        "completed_at": message.completed_at,
                        "error_code": message.error_code,
                        "created_at": message.created_at,
                        "sources": [
                            {
                                "source_id": source.source_id,
                                "kind": source.kind,
                                "title": source.title,
                                "document_id": source.document_id,
                                "chunk_id": source.chunk_id,
                                "url": source.url,
                                "snippet": source.snippet,
                                "score": source.score,
                                "page_number": source.page_number,
                                "chunk_index": source.chunk_index,
                                "rank": source.rank,
                                "published_at": source.published_at,
                                "metadata": json.loads(source.metadata_json or "{}"),
                                "available": (
                                    not source.document_id
                                    or source.document_id in available_document_ids
                                ),
                            }
                            for source in sources_by_message.get(message.id, [])
                        ],
                    }
                    for message in messages
                ],
            }
        )
        return response
