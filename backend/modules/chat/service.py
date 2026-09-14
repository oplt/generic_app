from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.errors import StructuredApiError
from backend.lib.generation_port import (
    AiServiceGenerationPort,
    GenerationPort,
    RagGenerationChunk,
)
from backend.lib.project_access import ProjectAccessPort, SqlAlchemyProjectAccessPort
from backend.lib.vectors import estimate_tokens
from backend.modules.chat import metrics
from backend.modules.chat.application.chat_context import (
    bounded_token_batches,
    build_history_context,
    build_web_context,
    chat_error_code,
    requested_memory_enabled,
    requested_memory_write_enabled,
    safe_chat_error_message,
    source_from_chunk,
    source_from_memory_item,
    source_from_search_result,
)
from backend.modules.chat.application.conversation_service import ConversationService
from backend.modules.chat.application.provider_concurrency import chat_provider_slot
from backend.modules.chat.application.query_router import QueryRouter
from backend.modules.chat.application.search import (
    SearchOptions,
    SearchProviderError,
    SearchResult,
)
from backend.modules.chat.application.search_limits import (
    enforce_web_search_limits,
    web_search_slot,
)
from backend.modules.chat.infrastructure.search_provider import build_search_provider
from backend.modules.chat.models import ChatConversation, ChatMessage
from backend.modules.chat.repository import ChatRepository
from backend.modules.chat.schemas import (
    ChatConversationCreate,
    ChatConversationUpdate,
    ChatErrorEvent,
    ChatFinalEvent,
    ChatMessageRequest,
    ChatRouteDecision,
    ChatSource,
    ChatSourceEvent,
    ChatStatusEvent,
    ChatStreamEvent,
    ChatTokenEvent,
)
from backend.modules.identity_access.models import User
from backend.modules.memory.application.memory_service import MemoryService
from backend.modules.memory.domain.models import MemoryItem, MemorySearchRequest
from backend.modules.memory.infrastructure.memory_config import MemoryConfig
from backend.modules.memory.workers import queue_turn_memory_extraction
from backend.modules.rag.application.citation_service import CitationService
from backend.modules.rag.application.document_identity import document_embedding_is_current
from backend.modules.rag.application.rag_context_builder import RagContextBuilder
from backend.modules.rag.application.retrieval_service import RetrievalService
from backend.modules.rag.domain.models import RetrievedChunk
from backend.modules.rag.infrastructure.rag_config import RagConfig
from backend.modules.rag.infrastructure.repositories import RagRepository

logger = logging.getLogger(__name__)

NO_DOCUMENT_CONTEXT_ANSWER = (
    "I could not find relevant context in the selected indexed documents. "
    "Try selecting another document or asking about information contained in the selection."
)


class DocumentChatService:
    """Conversation persistence and strict, evidence-only document chat."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        generation: GenerationPort | None = None,
        retrieval: RetrievalService | None = None,
    ):
        self.db = db
        self.repo = ChatRepository(db)
        self.rag_repo = RagRepository(db)
        self.project_access: ProjectAccessPort = SqlAlchemyProjectAccessPort(db)
        self.retrieval = retrieval or RetrievalService(db)
        self.generation = generation or AiServiceGenerationPort(db)
        self.citations = CitationService()
        self.context_builder = RagContextBuilder(self.citations)
        self.memory = MemoryService(db)
        self.memory_config = MemoryConfig.from_settings()
        self.router = QueryRouter()
        self.conversations = ConversationService(
            db,
            repository=self.repo,
            project_access=self.project_access,
            memory_config=self.memory_config,
            rag_repository=self.rag_repo,
        )

    def _conversation_service(self) -> ConversationService:
        """Keep compatibility with lightweight service instances in unit tests."""

        service = getattr(self, "conversations", None)
        if service is None:
            service = ConversationService(
                self.db,
                repository=self.repo,
                project_access=getattr(self, "project_access", None),
                memory_config=getattr(self, "memory_config", None),
                rag_repository=getattr(self, "rag_repo", None),
            )
            self.conversations = service
        return service

    async def create_conversation(
        self, user: User, payload: ChatConversationCreate
    ) -> ChatConversation:
        return await self._conversation_service().create(user, payload)

    async def list_conversations(
        self,
        user: User,
        *,
        project_id: str | None = None,
        limit: int,
        offset: int = 0,
        cursor: str | None = None,
    ) -> tuple[list[ChatConversation], int | None, str | None, bool]:
        return await self._conversation_service().list(
            user,
            project_id=project_id,
            limit=limit,
            offset=offset,
            cursor=cursor,
        )

    async def get_conversation(self, user: User, conversation_id: str) -> ChatConversation:
        return await self._conversation_service().get(user, conversation_id)

    async def update_conversation(
        self,
        user: User,
        conversation_id: str,
        payload: ChatConversationUpdate,
    ) -> ChatConversation:
        return await self._conversation_service().update(user, conversation_id, payload)

    async def delete_conversation(self, user: User, conversation_id: str) -> None:
        await self._conversation_service().delete(user, conversation_id)

    async def clear_conversation(self, user: User, conversation_id: str) -> None:
        await self._conversation_service().clear(user, conversation_id)

    async def delete_expired_conversations(self) -> int:
        return await self._conversation_service().delete_expired()

    async def stream_chat_answer(
        self,
        user: User,
        conversation: ChatConversation,
        payload: ChatMessageRequest,
        *,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        memory_enabled = self._requested_memory_enabled(conversation, payload)
        decision = self.router.decide(
            mode=payload.mode,
            query=payload.content,
            selected_document_ids=payload.document_ids,
            memory_enabled=memory_enabled,
            web_enabled=settings.WEB_SEARCH_ENABLED,
        )
        metrics.chat_route_total.labels(
            requested_mode=payload.mode,
            route=decision.mode,
            reason=decision.reason,
        ).inc()
        if decision.use_documents:
            async for event in self.stream_document_answer(
                user,
                conversation,
                payload,
                is_disconnected=is_disconnected,
                route=decision,
            ):
                yield event
            return
        async for event in self._stream_context_answer(
            user,
            conversation,
            payload,
            decision,
            is_disconnected=is_disconnected,
        ):
            yield event

    async def _stream_context_answer(
        self,
        user: User,
        conversation: ChatConversation,
        payload: ChatMessageRequest,
        route: ChatRouteDecision,
        *,
        is_disconnected: Callable[[], Awaitable[bool]] | None,
    ) -> AsyncIterator[ChatStreamEvent]:
        self._validate_message(conversation, payload, strict=False)
        memory_enabled = self._requested_memory_enabled(conversation, payload)
        history = (
            await self.repo.list_recent_messages(
                conversation.id,
                limit=settings.CHAT_MAX_HISTORY_MESSAGES,
            )
            if isinstance(self.repo, ChatRepository)
            else []
        )
        assistant_message = await self._create_pending_messages(
            user, conversation, payload, mode=route.mode
        )
        started = perf_counter()
        sources: list[ChatSource] = []
        context_parts: list[str] = []
        memory_degraded = False
        history_context = self._build_history_context(history)
        if history_context:
            context_parts.append(history_context)
        write_memory = self._requested_memory_write_enabled(conversation, payload)

        try:
            yield ChatStatusEvent(event="status", status="queued")
            if await self._disconnected(is_disconnected):
                raise asyncio.CancelledError
            yield ChatStatusEvent(event="status", status="retrieving")

            if route.use_web:
                try:
                    await enforce_web_search_limits(user.id)
                    async with web_search_slot():
                        provider = build_search_provider()
                        results = await provider.search(
                            route.search_query or payload.content,
                            SearchOptions(
                                max_results=settings.WEB_SEARCH_MAX_RESULTS,
                                timeout_seconds=settings.WEB_SEARCH_TIMEOUT_SECONDS,
                            ),
                        )
                except SearchProviderError as exc:
                    if payload.mode == "auto":
                        route = ChatRouteDecision(
                            mode="general",
                            reason="fallback",
                            confidence="low",
                            use_memory=memory_enabled,
                        )
                        results = []
                    else:
                        raise StructuredApiError(
                            status_code=503,
                            code="web_search_unavailable",
                            message="Web search is temporarily unavailable.",
                            retryable=True,
                        ) from exc
                if route.use_web and not results:
                    if payload.mode == "auto":
                        route = ChatRouteDecision(
                            mode="general",
                            reason="fallback",
                            confidence="low",
                            use_memory=memory_enabled,
                        )
                    else:
                        no_web_answer = "I could not find usable web results for that question."
                        await self._complete_message(
                            conversation,
                            assistant_message,
                            answer=no_web_answer,
                            model_name="none",
                            latency_ms=int((perf_counter() - started) * 1000),
                            route=route,
                        )
                        yield ChatFinalEvent(
                            event="final",
                            message_id=assistant_message.id,
                            answer=no_web_answer,
                            sources=[],
                            route=route,
                        )
                        return
                if route.use_web:
                    sources = [self._source_from_search_result(result) for result in results]
                    context_parts.append(self._build_web_context(results))
                    for source in sources:
                        yield ChatSourceEvent(event="source", source=source)

            if route.use_memory:
                memory_context, memory_items, memory_degraded = await self.memory.recall_for_prompt(
                    MemorySearchRequest(
                        user_id=user.id,
                        agent_id="default",
                        query=payload.content,
                        run_id=conversation.id,
                        project_id=conversation.project_id,
                        limit=settings.MEMORY_DEFAULT_LIMIT,
                    )
                )
                metrics.chat_memory_recall_total.labels(
                    outcome="degraded" if memory_degraded else "success"
                ).inc()
                if memory_context:
                    context_parts.append(memory_context)
                memory_sources = [self._source_from_memory_item(item) for item in memory_items]
                sources.extend(memory_sources)
                for source in memory_sources:
                    yield ChatSourceEvent(event="source", source=source)

            yield ChatStatusEvent(event="status", status="generating")
            if await self._disconnected(is_disconnected):
                raise asyncio.CancelledError
            generation = None
            answer_parts: list[str] = []
            async for generation_event in self._iter_generation_events(
                user,
                is_disconnected=is_disconnected,
                query=payload.content,
                combined_context="\n\n".join(context_parts),
                retrieved_chunk_ids=[],
                memory_degraded=memory_degraded,
            ):
                if generation_event.result is not None:
                    generation = generation_event.result
                if generation_event.text:
                    answer_parts.append(generation_event.text)
                    for token in self._bounded_token_batches(generation_event.text):
                        yield ChatTokenEvent(event="token", token=token)
            answer = "".join(answer_parts).strip()
            if not answer:
                raise StructuredApiError(
                    status_code=502,
                    code="provider_unavailable",
                    message="The AI provider returned no answer.",
                    retryable=True,
                )
            if generation is None:
                raise StructuredApiError(
                    status_code=502,
                    code="provider_unavailable",
                    message="The AI provider returned no run metadata.",
                    retryable=True,
                )
            await self._complete_message(
                conversation,
                assistant_message,
                answer=answer,
                model_name=generation.model_name,
                ai_run_id=generation.id,
                input_tokens=getattr(generation, "input_tokens", None),
                output_tokens=getattr(generation, "output_tokens", None),
                latency_ms=int((perf_counter() - started) * 1000),
                sources=sources,
                route=route,
            )
            if route.mode in {"general", "auto"} and route.use_memory and write_memory:
                try:
                    queue_turn_memory_extraction(
                        user_id=user.id,
                        agent_id="default",
                        run_id=conversation.id,
                        project_id=conversation.project_id,
                        user_message=payload.content,
                        assistant_message=answer,
                        source_message_id=assistant_message.id,
                    )
                except Exception:
                    # Memory extraction is optional and must not fail the answer.
                    logger.exception(
                        "Chat memory extraction queue degraded user=%s conversation=%s",
                        user.id,
                        conversation.id,
                    )
            yield ChatStatusEvent(event="status", status="completed")
            yield ChatFinalEvent(
                event="final",
                message_id=assistant_message.id,
                answer=answer,
                sources=sources,
                route=route,
            )
        except asyncio.CancelledError:
            await self._mark_message(
                assistant_message,
                status="cancelled",
                content="",
                error_code="cancelled",
            )
            self._record_failure(route=route, code="cancelled", outcome="cancelled")
            raise
        except HTTPException as exc:
            error_code = getattr(exc, "code", None) or (
                "web_search_unavailable" if route.use_web else self._error_code(exc.status_code)
            )
            await self._mark_message(
                assistant_message,
                status="failed",
                content="",
                error_code=error_code,
            )
            self._record_failure(route=route, code=error_code)
            yield ChatErrorEvent(
                event="error",
                code=error_code,
                message=(
                    getattr(exc, "message", None)
                    or (
                        "Web search is temporarily unavailable."
                        if route.use_web
                        else self._safe_error_message(exc.status_code)
                    )
                ),
                retryable=True,
            )
        except Exception:
            await self._mark_message(
                assistant_message,
                status="failed",
                content="",
                error_code="internal_error",
            )
            self._record_failure(route=route, code="internal_error")
            yield ChatErrorEvent(
                event="error",
                code="internal_error",
                message="The chat answer could not be generated.",
                retryable=True,
            )

    async def stream_document_answer(
        self,
        user: User,
        conversation: ChatConversation,
        payload: ChatMessageRequest,
        *,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
        route: ChatRouteDecision | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        self._validate_message(conversation, payload, strict=True)
        selected_document_ids = await self._authorize_documents(user, conversation, payload)
        assistant_message = await self._create_pending_messages(
            user, conversation, payload, mode="documents"
        )
        started = perf_counter()

        try:
            yield ChatStatusEvent(event="status", status="queued")
            if await self._disconnected(is_disconnected):
                raise asyncio.CancelledError

            yield ChatStatusEvent(event="status", status="retrieving")
            outcome = (
                await self.retrieval.retrieve(
                    payload.content,
                    user_id=user.id,
                    project_id=conversation.project_id,
                    organization_id=getattr(conversation, "organization_id", None),
                    top_k=None,
                    filters={"document_ids": selected_document_ids},
                )
                if selected_document_ids
                else None
            )
            chunks = self.context_builder.trim_chunks_to_token_budget(
                outcome.chunks if outcome else [],
                max_tokens=settings.RAG_MAX_CONTEXT_TOKENS,
            )
            if not chunks:
                await self._complete_message(
                    conversation,
                    assistant_message,
                    answer=NO_DOCUMENT_CONTEXT_ANSWER,
                    model_name="none",
                    latency_ms=int((perf_counter() - started) * 1000),
                    route=route,
                )
                yield ChatFinalEvent(
                    event="final",
                    message_id=assistant_message.id,
                    answer=NO_DOCUMENT_CONTEXT_ANSWER,
                    sources=[],
                    route=route,
                )
                return

            sources = [self._source_from_chunk(chunk) for chunk in chunks]
            for source in sources:
                yield ChatSourceEvent(event="source", source=source)
            yield ChatStatusEvent(event="status", status="generating")
            if await self._disconnected(is_disconnected):
                raise asyncio.CancelledError

            document_context = self.context_builder.build_document_context_block(chunks)
            combined_context = self.context_builder.build_combined_context(
                memory_context=None,
                document_context=document_context,
                user_question=payload.content,
            )
            generation = None
            answer_parts: list[str] = []
            async for generation_event in self._iter_generation_events(
                user,
                is_disconnected=is_disconnected,
                query=payload.content,
                combined_context=combined_context,
                retrieved_chunk_ids=[chunk.chunk_id for chunk in chunks],
                retrieval_degraded=outcome.degraded if outcome else False,
                memory_degraded=False,
                degradation_reason=outcome.degradation_reason if outcome else None,
                injection_chunks_filtered=outcome.injection_chunks_filtered if outcome else 0,
            ):
                if generation_event.result is not None:
                    generation = generation_event.result
                if generation_event.text:
                    answer_parts.append(generation_event.text)
                    for token in self._bounded_token_batches(generation_event.text):
                        yield ChatTokenEvent(event="token", token=token)
            answer = "".join(answer_parts).strip()
            if not answer:
                raise StructuredApiError(
                    status_code=502,
                    code="provider_unavailable",
                    message="The AI provider returned no answer.",
                    retryable=True,
                )

            validation = self.citations.validate_answer(answer, chunks)
            if not validation.valid:
                raise StructuredApiError(
                    status_code=502,
                    code="citation_validation_failed",
                    message=(
                        "The AI provider returned an answer that could not be "
                        "validated against the selected documents."
                    ),
                    retryable=True,
                )
            if generation is None:
                raise StructuredApiError(
                    status_code=502,
                    code="provider_unavailable",
                    message="The AI provider returned no run metadata.",
                    retryable=True,
                )
            await self._complete_message(
                conversation,
                assistant_message,
                answer=answer,
                model_name=generation.model_name,
                ai_run_id=generation.id,
                input_tokens=getattr(generation, "input_tokens", None),
                output_tokens=getattr(generation, "output_tokens", None),
                latency_ms=int((perf_counter() - started) * 1000),
                sources=sources,
            )
            yield ChatStatusEvent(event="status", status="completed")
            yield ChatFinalEvent(
                event="final",
                message_id=assistant_message.id,
                answer=answer,
                sources=sources,
                route=route,
            )
        except asyncio.CancelledError:
            await self._mark_message(
                assistant_message,
                status="cancelled",
                content="",
                error_code="cancelled",
            )
            self._record_failure(route=route, code="cancelled", outcome="cancelled")
            raise
        except HTTPException as exc:
            error_code = getattr(exc, "code", None) or self._error_code(exc.status_code)
            await self._mark_message(
                assistant_message,
                status="failed",
                content="",
                error_code=error_code,
            )
            self._record_failure(route=route, code=error_code)
            yield ChatErrorEvent(
                event="error",
                code=error_code,
                message=getattr(exc, "message", None) or self._safe_error_message(exc.status_code),
                retryable=exc.status_code in {429, 502, 503, 504},
            )
        except Exception:
            await self._mark_message(
                assistant_message,
                status="failed",
                content="",
                error_code="internal_error",
            )
            self._record_failure(route=route, code="internal_error")
            yield ChatErrorEvent(
                event="error",
                code="internal_error",
                message="The document answer could not be generated.",
                retryable=True,
            )

    async def collect_document_answer(
        self, user: User, conversation: ChatConversation, payload: ChatMessageRequest
    ) -> ChatConversation:
        async for _ in self.stream_document_answer(user, conversation, payload):
            pass
        return await self.get_conversation(user, conversation.id)

    async def collect_chat_answer(
        self, user: User, conversation: ChatConversation, payload: ChatMessageRequest
    ) -> ChatConversation:
        async for _ in self.stream_chat_answer(user, conversation, payload):
            pass
        return await self.get_conversation(user, conversation.id)

    async def serialize_conversation(
        self,
        conversation: ChatConversation,
        *,
        message_limit: int | None = None,
    ) -> dict:
        return await self._conversation_service().serialize(
            conversation,
            message_limit=message_limit,
        )

    async def serialize_conversation_summary(self, conversation: ChatConversation) -> dict:
        return await self._conversation_service().serialize_summary(conversation)

    async def _authorize_documents(
        self,
        user: User,
        conversation: ChatConversation,
        payload: ChatMessageRequest,
    ) -> list[str]:
        requested = list(dict.fromkeys(payload.document_ids))
        if not requested:
            raise StructuredApiError(
                status_code=422,
                code="no_documents_selected",
                message="Select at least one indexed document.",
            )
        indexed = await self.rag_repo.list_indexed_documents(
            user.id,
            project_id=conversation.project_id,
            document_ids=requested,
            organization_id=getattr(conversation, "organization_id", None),
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

    async def _create_pending_messages(
        self,
        user: User,
        conversation: ChatConversation,
        payload: ChatMessageRequest,
        *,
        mode: str,
    ) -> ChatMessage:
        await self.repo.create_message(
            conversation_id=conversation.id,
            user_id=user.id,
            role="user",
            content=payload.content,
            mode=mode,
            document_ids_json=json.dumps(
                list(dict.fromkeys(payload.document_ids)) if mode == "documents" else [],
                ensure_ascii=True,
            ),
            status="completed",
            completed_at=datetime.now(UTC),
        )
        assistant_message = await self.repo.create_message(
            conversation_id=conversation.id,
            user_id=user.id,
            role="assistant",
            content="",
            mode=mode,
            status="generating",
        )
        await self.repo.touch_conversation(conversation)
        await self.db.commit()
        return assistant_message

    async def _complete_message(
        self,
        conversation: ChatConversation,
        message: ChatMessage,
        *,
        answer: str,
        model_name: str,
        latency_ms: int,
        ai_run_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        sources: list[ChatSource] | None = None,
        route: ChatRouteDecision | None = None,
    ) -> None:
        message.content = answer
        message.status = "completed"
        message.model_name = model_name
        message.ai_run_id = ai_run_id
        message.input_tokens = input_tokens
        message.output_tokens = output_tokens
        message.latency_ms = latency_ms
        message.completed_at = datetime.now(UTC)
        message.error_code = None
        if route:
            message.route_reason = route.reason
            message.route_confidence = route.confidence
        if sources:
            await self.repo.create_sources(
                message.id,
                [source.model_dump() for source in sources],
            )
        route_name = route.mode if route else getattr(message, "mode", "documents")
        metrics.chat_requests_total.labels(
            requested_mode=route_name,
            route=route_name,
            outcome="completed",
        ).inc()
        metrics.chat_response_latency_ms.labels(route=route_name).observe(max(0, latency_ms))
        metrics.chat_tokens_total.labels(route=route_name).inc(estimate_tokens(answer, model_name))
        source_counts = {kind: 0 for kind in ("document", "web", "memory")}
        for source in sources or []:
            source_counts[source.kind] += 1
            metrics.chat_sources_total.labels(kind=source.kind).inc()
        for kind, count in source_counts.items():
            metrics.chat_source_count.labels(kind=kind).observe(count)
        await self.repo.touch_conversation(conversation)
        await self.db.commit()

    @staticmethod
    def _record_failure(
        *,
        route: ChatRouteDecision | None,
        code: str,
        outcome: str = "error",
    ) -> None:
        route_name = route.mode if route else "documents"
        metrics.chat_errors_total.labels(code=code, route=route_name).inc()
        metrics.chat_requests_total.labels(
            requested_mode=route_name,
            route=route_name,
            outcome=outcome,
        ).inc()

    async def _mark_message(
        self,
        message: ChatMessage,
        *,
        status: str,
        content: str,
        error_code: str | None = None,
    ) -> None:
        message.status = status
        message.content = content
        message.error_code = error_code
        message.completed_at = datetime.now(UTC)
        await self.db.commit()

    @staticmethod
    def _validate_message(
        conversation: ChatConversation,
        payload: ChatMessageRequest,
        *,
        strict: bool,
    ) -> None:
        if strict and payload.mode not in {"documents", "auto"}:
            raise StructuredApiError(
                status_code=422,
                code="invalid_request",
                message="Documents mode is required for document-only answers.",
            )
        if strict and conversation.mode not in {"documents", "auto"}:
            raise StructuredApiError(
                status_code=409,
                code="conflict",
                message="Conversation mode does not allow documents.",
            )
        if not strict and payload.mode == "documents":
            raise StructuredApiError(
                status_code=422,
                code="invalid_request",
                message="Use documents mode for document-only answers.",
            )
        if not strict and conversation.mode == "documents":
            raise StructuredApiError(
                status_code=409,
                code="conflict",
                message="A documents conversation cannot use another mode.",
            )
        if conversation.mode not in {payload.mode, "auto"} and not strict:
            raise StructuredApiError(
                status_code=409,
                code="conflict",
                message="Conversation mode does not match request.",
            )
        if payload.project_id and payload.project_id != conversation.project_id:
            raise StructuredApiError(
                status_code=409,
                code="conflict",
                message="Conversation project does not match request.",
            )
        if payload.conversation_id and payload.conversation_id != conversation.id:
            raise StructuredApiError(
                status_code=409,
                code="conflict",
                message="Conversation ID does not match request path.",
            )
        if len(payload.content.encode("utf-8")) > settings.CHAT_MAX_MESSAGE_BYTES:
            raise StructuredApiError(
                status_code=413,
                code="message_too_large",
                message="Chat message exceeds the size limit.",
            )

    @staticmethod
    async def _disconnected(
        callback: Callable[[], Awaitable[bool]] | None,
    ) -> bool:
        return bool(await callback()) if callback else False

    @staticmethod
    def _bounded_token_batches(text: str, *, max_chars: int = 256) -> list[str]:
        return bounded_token_batches(text, max_chars=max_chars)

    async def _iter_generation_events(
        self,
        user: User,
        *,
        is_disconnected: Callable[[], Awaitable[bool]] | None,
        **kwargs,
    ) -> AsyncIterator[RagGenerationChunk]:
        stream_method = getattr(self.generation, "stream_rag_answer", None)
        provider_timeout = max(
            0.001,
            min(settings.AI_REQUEST_TIMEOUT_SECONDS, settings.CHAT_REQUEST_TIMEOUT_SECONDS),
        )
        async with chat_provider_slot():
            if callable(stream_method):
                stream = stream_method(user, **kwargs)
                iterator = stream.__aiter__()
                deadline = asyncio.get_running_loop().time() + provider_timeout
                try:
                    while True:
                        if await self._disconnected(is_disconnected):
                            raise asyncio.CancelledError
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise StructuredApiError(
                                status_code=504,
                                code="provider_timeout",
                                message="The AI provider timed out.",
                                retryable=True,
                            )
                        try:
                            event = await asyncio.wait_for(iterator.__anext__(), remaining)
                        except StopAsyncIteration:
                            break
                        except TimeoutError as exc:
                            raise StructuredApiError(
                                status_code=504,
                                code="provider_timeout",
                                message="The AI provider timed out.",
                                retryable=True,
                            ) from exc
                        if isinstance(event, RagGenerationChunk):
                            yield event
                        else:
                            yield RagGenerationChunk(
                                text=getattr(event, "text", ""),
                                result=getattr(event, "result", None),
                            )
                finally:
                    close = getattr(stream, "aclose", None)
                    if callable(close):
                        await close()
                return

            # Narrow test/legacy ports may only implement completion generation.
            try:
                generation = await asyncio.wait_for(
                    self.generation.run_rag_answer(user, **kwargs), provider_timeout
                )
            except TimeoutError as exc:
                raise StructuredApiError(
                    status_code=504,
                    code="provider_timeout",
                    message="The AI provider timed out.",
                    retryable=True,
                ) from exc
            answer = generation.output_text or ""
            if answer:
                yield RagGenerationChunk(text=answer)
            yield RagGenerationChunk(result=generation)

    @staticmethod
    def _build_history_context(messages: list[ChatMessage]) -> str:
        return build_history_context(messages)

    @staticmethod
    def _source_from_chunk(chunk: RetrievedChunk) -> ChatSource:
        return source_from_chunk(chunk)

    @staticmethod
    def _source_from_search_result(result: SearchResult) -> ChatSource:
        return source_from_search_result(result)

    @staticmethod
    def _source_from_memory_item(item: MemoryItem) -> ChatSource:
        return source_from_memory_item(item)

    @staticmethod
    def _build_web_context(results: list[SearchResult]) -> str:
        return build_web_context(results)

    @staticmethod
    def _requested_memory_enabled(
        conversation: ChatConversation, payload: ChatMessageRequest
    ) -> bool:
        return requested_memory_enabled(conversation, payload)

    @staticmethod
    def _requested_memory_write_enabled(
        conversation: ChatConversation, payload: ChatMessageRequest
    ) -> bool:
        return requested_memory_write_enabled(conversation, payload)

    @staticmethod
    def _error_code(status_code: int) -> str:
        return chat_error_code(status_code)

    @staticmethod
    def _safe_error_message(status_code: int) -> str:
        return safe_chat_error_message(status_code)
