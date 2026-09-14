from __future__ import annotations

import asyncio
from time import monotonic

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.core.errors import StructuredApiError
from backend.core.pagination import (
    PaginatedResponse,
    PaginationParams,
    paginated_response,
    pagination_params,
)
from backend.modules.ai.dependencies import enforce_ai_generation_rate_limit
from backend.modules.chat.application.chat_service import ChatService
from backend.modules.chat.infrastructure.streaming import encode_sse_event
from backend.modules.chat.schemas import (
    ChatConversationCreate,
    ChatConversationResponse,
    ChatConversationSummary,
    ChatConversationUpdate,
    ChatErrorEvent,
    ChatMessageRequest,
)
from backend.modules.identity_access.models import User

router = APIRouter()


def _require_chat_enabled() -> None:
    if not settings.CHAT_ENABLED:
        raise StructuredApiError(
            status_code=503,
            code="feature_disabled",
            message="Knowledge chat is disabled.",
        )


@router.post("/conversations", response_model=ChatConversationSummary, status_code=201)
async def create_conversation(
    payload: ChatConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_chat_enabled()
    service = ChatService(db)
    conversation = await service.create_conversation(current_user, payload)
    return await service.serialize_conversation_summary(conversation)


@router.get("/conversations", response_model=PaginatedResponse[ChatConversationSummary])
async def list_conversations(
    project_id: str | None = Query(default=None),
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_chat_enabled()
    service = ChatService(db)
    conversations, total, next_cursor, has_more = await service.list_conversations(
        current_user,
        project_id=project_id,
        limit=pagination.limit,
        offset=pagination.offset,
        cursor=pagination.cursor,
    )
    return paginated_response(
        [await service.serialize_conversation_summary(item) for item in conversations],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/conversations/{conversation_id}", response_model=ChatConversationResponse)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_chat_enabled()
    service = ChatService(db)
    conversation = await service.get_conversation(current_user, conversation_id)
    return await service.serialize_conversation(
        conversation,
        message_limit=settings.CHAT_MAX_HISTORY_MESSAGES,
    )


@router.patch("/conversations/{conversation_id}", response_model=ChatConversationSummary)
async def update_conversation(
    conversation_id: str,
    payload: ChatConversationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_chat_enabled()
    service = ChatService(db)
    conversation = await service.update_conversation(current_user, conversation_id, payload)
    return await service.serialize_conversation_summary(conversation)


@router.post("/conversations/{conversation_id}/clear", status_code=204)
async def clear_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_chat_enabled()
    await ChatService(db).clear_conversation(current_user, conversation_id)
    return Response(status_code=204)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_chat_enabled()
    await ChatService(db).delete_conversation(current_user, conversation_id)
    return Response(status_code=204)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatConversationResponse,
)
async def send_message(
    conversation_id: str,
    payload: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(enforce_ai_generation_rate_limit),
):
    _require_chat_enabled()
    service = ChatService(db)
    conversation = await service.get_conversation(current_user, conversation_id)
    try:
        completed = await asyncio.wait_for(
            service.collect_chat_answer(current_user, conversation, payload),
            timeout=settings.CHAT_REQUEST_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise StructuredApiError(
            status_code=504,
            code="request_timeout",
            message="The chat request timed out.",
            retryable=True,
        ) from exc
    return await service.serialize_conversation(
        completed,
        message_limit=settings.CHAT_MAX_HISTORY_MESSAGES,
    )


@router.post(
    "/conversations/{conversation_id}/messages/stream",
    response_class=StreamingResponse,
)
async def stream_message(
    conversation_id: str,
    payload: ChatMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(enforce_ai_generation_rate_limit),
):
    _require_chat_enabled()
    service = ChatService(db)
    conversation = await service.get_conversation(current_user, conversation_id)

    async def event_stream():
        sequence = 0
        deadline = monotonic() + settings.CHAT_REQUEST_TIMEOUT_SECONDS
        events = service.stream_chat_answer(
            current_user,
            conversation,
            payload,
            is_disconnected=request.is_disconnected,
        )
        pending = asyncio.create_task(events.__anext__())
        try:
            while True:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    if not pending.done():
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
                    sequence += 1
                    yield encode_sse_event(
                        sequence,
                        ChatErrorEvent(
                            event="error",
                            code="request_timeout",
                            message="The chat request timed out.",
                            retryable=True,
                        ),
                    )
                    break
                try:
                    event = await asyncio.wait_for(
                        asyncio.shield(pending),
                        timeout=min(settings.CHAT_STREAM_HEARTBEAT_SECONDS, remaining),
                    )
                except TimeoutError:
                    if monotonic() < deadline:
                        yield ": keep-alive\n\n"
                        continue
                    if not pending.done():
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
                    sequence += 1
                    yield encode_sse_event(
                        sequence,
                        ChatErrorEvent(
                            event="error",
                            code="request_timeout",
                            message="The chat request timed out.",
                            retryable=True,
                        ),
                    )
                    break
                except StopAsyncIteration:
                    break
                sequence += 1
                yield encode_sse_event(sequence, event)
                pending = asyncio.create_task(events.__anext__())
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            await events.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
