from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from backend.core.schemas import RequestModel
from pydantic import BaseModel, ConfigDict, Field


class RagDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    project_id: str | None
    organization_id: str | None
    filename: str
    original_filename: str
    content_type: str
    fingerprint: str | None = None
    storage_path: str | None
    status: str
    source_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    needs_reindex: bool = False


class RagDocumentUploadResponse(BaseModel):
    document: RagDocumentResponse
    ingestion_job: RagIngestionJobResponse
    duplicate: bool = False


class RagChunkResponse(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    content: str
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagIngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    user_id: str
    project_id: str | None
    status: str
    error_message: str | None
    attempts: int
    deadline_at: datetime | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class RagRetrieveRequest(RequestModel):
    query: str = Field(min_length=1, max_length=4000)
    project_id: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    top_k: int | None = Field(default=None, ge=1, le=20)
    source_type: str | None = Field(default=None, max_length=32)
    strategy: Literal["vector", "lexical", "hybrid_rrf"] | None = None


class RagRetrievedChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float
    filename: str
    chunk_index: int
    page_number: int | None = None


class RagRetrieveResponse(BaseModel):
    chunks: list[RagRetrievedChunkResponse]
    degraded: bool = False
    degradation_reason: str | None = None
    no_matches: bool = False
    injection_chunks_filtered: int = 0


class RagAskRequest(RequestModel):
    query: str = Field(min_length=1, max_length=4000)
    project_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    mode: Literal["documents", "general", "web", "auto"] = "documents"
    use_memory: bool | None = None


class RagCitationResponse(BaseModel):
    document_id: str
    chunk_id: str
    filename: str
    score: float
    snippet: str
    page_number: int | None = None
    chunk_index: int | None = None


class RagWebSourceResponse(BaseModel):
    source_id: str
    title: str
    url: str
    snippet: str
    rank: int
    published_at: str | None = None


class RagAskResponse(BaseModel):
    query: str
    answer: str
    citations: list[RagCitationResponse]
    retrieved_chunk_ids: list[str]
    model_name: str
    latency_ms: int
    no_context_found: bool
    ai_run_id: str | None = None
    retrieval_degraded: bool = False
    memory_degraded: bool = False
    degradation_reason: str | None = None
    injection_chunks_filtered: int = 0
    citation_validated: bool = True
    needs_review: bool = False
    mode: Literal["documents", "general", "web", "auto"] = "documents"
    web_sources: list[RagWebSourceResponse] = Field(default_factory=list)


class RagQueryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    query: str
    answer: str
    project_id: str | None
    model_name: str
    latency_ms: int
    created_at: datetime


class RagIndexVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    status: str
    parser_version: str
    chunker_version: str
    embedding_schema_version: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    notes: str | None = None
    created_at: datetime
    activated_at: datetime | None = None
    retired_at: datetime | None = None
    validated_at: datetime | None = None


class RagIndexVersionCreateRequest(RequestModel):
    notes: str | None = Field(default=None, max_length=2000)


class RagIndexStatusResponse(BaseModel):
    active_version: RagIndexVersionResponse
    pipeline: dict[str, object]
    schema_embedding_dimensions: int
    documents_total: int
    documents_indexed: int
    documents_current: int
    documents_stale: int
    jobs_active: int
    jobs_failed: int
    dimension_migration_required: bool = False
    versions: list[RagIndexVersionResponse] = Field(default_factory=list)


class RagIndexReindexStaleRequest(RequestModel):
    limit: int = Field(default=50, ge=1, le=500)


class RagIndexReindexStaleResponse(BaseModel):
    requested: int
    enqueued: int
    skipped: int
    job_ids: list[str]
    active_index_version: str


class RagEvalDatasetCreateRequest(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    organization_id: str | None = None


class RagEvalDatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    organization_id: str | None
    name: str
    description: str | None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RagEvalCaseCreateRequest(RequestModel):
    question: str = Field(min_length=1, max_length=8000)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    judgments: dict[str, int] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class RagEvalCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    question: str
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    judgments: dict[str, int] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: datetime


class RagEvalProbeRequest(RequestModel):
    query: str = Field(min_length=1, max_length=4000)
    project_id: str | None = None
    organization_id: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    strategy: Literal["vector", "lexical", "hybrid_rrf"] | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    include_generation_judges: bool = False


class RagEvalRunRequest(RequestModel):
    name: str = Field(default="run", max_length=255)
    project_id: str | None = None
    organization_id: str | None = None
    strategy: Literal["vector", "lexical", "hybrid_rrf"] | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    baseline_run_id: str | None = None
    include_generation_judges: bool = False


class RagEvalRunItemResponse(BaseModel):
    id: str
    case_id: str
    ranked_chunk_ids: list[str] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    latency: dict[str, Any] = Field(default_factory=dict)
    included_in_context: bool = True
    score: float = 0.0
    notes: str | None = None


class RagEvalRunResponse(BaseModel):
    id: str
    dataset_id: str
    user_id: str
    organization_id: str | None
    name: str
    status: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    latency: dict[str, Any] = Field(default_factory=dict)
    baseline_run_id: str | None = None
    comparison: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    items: list[RagEvalRunItemResponse] = Field(default_factory=list)
