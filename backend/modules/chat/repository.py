from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.pagination import DEFAULT_PAGE_LIMIT, paginate_cursor_scalars, paginate_scalars
from backend.modules.chat.models import ChatConversation, ChatMessage, ChatMessageSource


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(self, **kwargs) -> ChatConversation:
        selected_document_ids = kwargs.pop("selected_document_ids", [])
        row = ChatConversation(**kwargs)
        row.selected_document_ids_json = json.dumps(selected_document_ids, ensure_ascii=True)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_conversations_for_user(
        self,
        user_id: str,
        *,
        project_id: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> tuple[list[ChatConversation], int]:
        stmt = select(ChatConversation).where(
            ChatConversation.user_id == user_id,
            ChatConversation.deleted_at.is_(None),
        )
        if project_id is not None:
            stmt = stmt.where(ChatConversation.project_id == project_id)
        stmt = stmt.order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
        return await paginate_scalars(self.db, stmt, limit=limit, offset=offset)

    async def list_conversations_for_user_cursor(
        self,
        user_id: str,
        *,
        project_id: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> tuple[list[ChatConversation], str | None, bool]:
        stmt = select(ChatConversation).where(
            ChatConversation.user_id == user_id,
            ChatConversation.deleted_at.is_(None),
        )
        if project_id is not None:
            stmt = stmt.where(ChatConversation.project_id == project_id)
        return await paginate_cursor_scalars(
            self.db,
            stmt,
            limit=limit,
            cursor=cursor,
            sort_column=ChatConversation.updated_at,
            id_column=ChatConversation.id,
        )

    async def get_conversation_for_user(
        self, user_id: str, conversation_id: str
    ) -> ChatConversation | None:
        result = await self.db.execute(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id,
                ChatConversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
        return list(result.scalars().all())

    async def list_recent_messages(self, conversation_id: str, *, limit: int) -> list[ChatMessage]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def list_sources_for_messages(self, message_ids: list[str]) -> list[ChatMessageSource]:
        if not message_ids:
            return []
        result = await self.db.execute(
            select(ChatMessageSource)
            .where(ChatMessageSource.message_id.in_(message_ids))
            .order_by(ChatMessageSource.id.asc())
        )
        return list(result.scalars().all())

    async def create_message(self, **kwargs) -> ChatMessage:
        row = ChatMessage(**kwargs)
        self.db.add(row)
        await self.db.flush()
        return row

    async def create_sources(self, message_id: str, sources: list[dict]) -> list[ChatMessageSource]:
        normalized_sources = []
        for source in sources:
            values = dict(source)
            metadata = values.pop("metadata", {})
            values.pop("available", None)
            values.setdefault("source_kind", values.get("kind", "document"))
            values["metadata_json"] = json.dumps(metadata or {}, ensure_ascii=True)
            normalized_sources.append(values)
        rows = [ChatMessageSource(message_id=message_id, **source) for source in normalized_sources]
        self.db.add_all(rows)
        await self.db.flush()
        return rows

    async def touch_conversation(self, conversation: ChatConversation) -> None:
        conversation.updated_at = datetime.now(UTC)
        await self.db.flush()

    async def delete_conversation(self, conversation: ChatConversation) -> None:
        await self.db.execute(
            delete(ChatConversation).where(ChatConversation.id == conversation.id)
        )

    async def clear_messages(self, conversation_id: str) -> None:
        await self.db.execute(
            delete(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
        )

    async def delete_sources_for_document(self, document_id: str) -> None:
        """Remove persisted citations when their document is permanently cleaned up."""
        await self.db.execute(
            delete(ChatMessageSource).where(ChatMessageSource.document_id == document_id)
        )

    async def delete_expired_conversations(self, cutoff: datetime) -> int:
        result = await self.db.execute(
            delete(ChatConversation).where(
                ChatConversation.updated_at < cutoff,
            )
        )
        return int(result.rowcount or 0)

    async def delete_expired_messages(self, cutoff: datetime) -> int:
        result = await self.db.execute(delete(ChatMessage).where(ChatMessage.created_at < cutoff))
        return int(result.rowcount or 0)

    @staticmethod
    def selected_document_ids(conversation: ChatConversation) -> list[str]:
        try:
            value = json.loads(conversation.selected_document_ids_json or "[]")
        except (TypeError, ValueError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def message_document_ids(message: ChatMessage) -> list[str]:
        try:
            value = json.loads(message.document_ids_json or "[]")
        except (TypeError, ValueError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []
