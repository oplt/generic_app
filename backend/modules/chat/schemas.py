from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel

CHAT_CONTRACT_VERSION = "v1"
ChatMode = Literal["auto", "documents", "general", "web"]
ChatSourceKind = Literal["document", "web", "memory"]
ChatRouteReason = Literal[
    "explicit_mode",
    "current_information",
    "direct_web_request",
    "selected_documents",
    "general_question",
    "fallback",
]
ChatErrorCode = Literal[
    "invalid_request",
    "not_found",
    "conflict",
    "documents_required",
    "no_documents_selected",
    "document_selection_invalid",
    "document_not_indexed",
    "document_deleted",
    "conversation_forbidden",
    "message_too_large",
    "rate_limited",
    "feature_disabled",
    "unauthorized",
    "no_context",
    "provider_timeout",
    "provider_busy",
    "provider_unavailable",
    "request_timeout",
    "citation_validation_failed",
    "web_search_unavailable",
    "cancelled",
    "stream_cancelled",
    "context_budget_exceeded",
    "internal_error",
]


class ChatMessageRequest(RequestModel):
    """Client selectors for a chat request; ownership is never client-provided."""

    contract_version: Literal["v1"] = CHAT_CONTRACT_VERSION
    content: str = Field(min_length=1, max_length=32_000)
    mode: ChatMode = "auto"
    conversation_id: str | None = None
    project_id: str | None = None
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    memory_enabled: bool | None = None
    memory_write_enabled: bool | None = None
    # Backward-compatible names used by existing clients.
    use_memory: bool | None = None
    write_memory: bool | None = None


class ChatConversationCreate(RequestModel):
    contract_version: Literal["v1"] = CHAT_CONTRACT_VERSION
    title: str | None = Field(default=None, max_length=255)
    project_id: str | None = None
    mode: ChatMode | None = None
    selected_document_ids: list[str] = Field(default_factory=list, max_length=50)
    memory_enabled: bool | None = None
    memory_write_enabled: bool | None = None


class ChatConversationUpdate(RequestModel):
    contract_version: Literal["v1"] = CHAT_CONTRACT_VERSION
    title: str | None = Field(default=None, min_length=1, max_length=255)
    mode: ChatMode | None = None
    selected_document_ids: list[str] | None = Field(default=None, max_length=50)
    memory_enabled: bool | None = None
    memory_write_enabled: bool | None = None


class ChatSource(BaseModel):
    source_id: str
    kind: ChatSourceKind
    title: str = Field(max_length=512)
    document_id: str | None = None
    chunk_id: str | None = None
    url: str | None = Field(default=None, max_length=2048)
    snippet: str | None = Field(default=None, max_length=2_000)
    score: float | None = Field(default=None, ge=0, le=1)
    page_number: int | None = Field(default=None, ge=1)
    chunk_index: int | None = Field(default=None, ge=0)
    rank: int | None = Field(default=None, ge=1)
    published_at: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    available: bool = True


class ChatRouteDecision(BaseModel):
    mode: ChatMode
    reason: ChatRouteReason
    confidence: Literal["high", "medium", "low"] = "high"
    use_documents: bool = False
    use_memory: bool = False
    use_web: bool = False
    search_query: str | None = None


class ChatStatusEvent(BaseModel):
    event: Literal["status"]
    status: Literal["queued", "retrieving", "generating", "completed"]


class ChatSourceEvent(BaseModel):
    event: Literal["source"]
    source: ChatSource


class ChatTokenEvent(BaseModel):
    event: Literal["token"]
    token: str


class ChatFinalEvent(BaseModel):
    event: Literal["final"]
    message_id: str
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)
    route: ChatRouteDecision | None = None


class ChatErrorEvent(BaseModel):
    event: Literal["error"]
    code: ChatErrorCode
    message: str = Field(max_length=500)
    retryable: bool = False


class ChatCancelledEvent(BaseModel):
    event: Literal["cancelled"]
    message: str = Field(default="Generation cancelled", max_length=200)


ChatStreamEvent = Annotated[
    ChatStatusEvent
    | ChatSourceEvent
    | ChatTokenEvent
    | ChatFinalEvent
    | ChatErrorEvent
    | ChatCancelledEvent,
    Field(discriminator="event"),
]


class ChatEventEnvelope(BaseModel):
    contract_version: Literal["v1"] = CHAT_CONTRACT_VERSION
    sequence: int = Field(ge=0)
    payload: ChatStreamEvent


class ChatErrorResponse(BaseModel):
    code: ChatErrorCode
    message: str = Field(max_length=500)
    retryable: bool = False


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant"]
    content: str
    mode: ChatMode
    document_ids: list[str] = Field(default_factory=list)
    status: str
    ai_run_id: str | None = None
    model_name: str | None = None
    route_reason: ChatRouteReason | None = None
    route_confidence: Literal["high", "medium", "low"] | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    completed_at: datetime | None = None
    error_code: str | None = None
    created_at: datetime
    sources: list[ChatSource] = Field(default_factory=list)


class ChatConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    project_id: str | None
    mode: ChatMode
    selected_document_ids: list[str] = Field(default_factory=list)
    memory_enabled: bool
    memory_write_enabled: bool
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    project_id: str | None
    mode: ChatMode
    selected_document_ids: list[str] = Field(default_factory=list)
    memory_enabled: bool
    memory_write_enabled: bool
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ChatErrorCode",
    "CHAT_CONTRACT_VERSION",
    "ChatErrorEvent",
    "ChatErrorResponse",
    "ChatConversationCreate",
    "ChatConversationUpdate",
    "ChatConversationResponse",
    "ChatConversationSummary",
    "ChatEventEnvelope",
    "ChatFinalEvent",
    "ChatMessageRequest",
    "ChatMessageResponse",
    "ChatMode",
    "ChatRouteDecision",
    "ChatSource",
    "ChatSourceEvent",
    "ChatStreamEvent",
    "ChatTokenEvent",
]
