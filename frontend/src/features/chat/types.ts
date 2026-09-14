export type ChatMode = "auto" | "documents" | "general" | "web";
export type ChatContractVersion = "v1";
export type ChatSourceKind = "document" | "web" | "memory";
export type ChatRouteReason =
    | "explicit_mode"
    | "current_information"
    | "direct_web_request"
    | "selected_documents"
    | "general_question"
    | "fallback";
export type ChatErrorCode =
    | "invalid_request"
    | "not_found"
    | "conflict"
    | "documents_required"
    | "no_documents_selected"
    | "document_selection_invalid"
    | "document_not_indexed"
    | "document_deleted"
    | "conversation_forbidden"
    | "message_too_large"
    | "feature_disabled"
    | "unauthorized"
    | "no_context"
    | "provider_timeout"
    | "provider_unavailable"
    | "search_unavailable"
    | "web_search_unavailable"
    | "cancelled"
    | "stream_cancelled"
    | "context_budget_exceeded"
    | "internal_error";

export type ChatMessageRequest = {
    contract_version?: ChatContractVersion;
    content: string;
    mode?: ChatMode;
    conversation_id?: string | null;
    project_id?: string | null;
    document_ids?: string[];
    memory_enabled?: boolean | null;
    memory_write_enabled?: boolean | null;
    use_memory?: boolean | null;
    write_memory?: boolean | null;
};

export type ChatSource = {
    source_id: string;
    kind: ChatSourceKind;
    title: string;
    document_id?: string | null;
    chunk_id?: string | null;
    url?: string | null;
    snippet?: string | null;
    score?: number | null;
    page_number?: number | null;
    chunk_index?: number | null;
    rank?: number | null;
    published_at?: string | null;
    metadata?: Record<string, unknown>;
    available?: boolean;
};

export type ChatEvent =
    | { event: "status"; status: "queued" | "retrieving" | "generating" | "completed" }
    | { event: "source"; source: ChatSource }
    | { event: "token"; token: string }
    | { event: "final"; message_id: string; answer: string; sources: ChatSource[]; route?: ChatRouteDecision | null }
    | { event: "error"; code: ChatErrorCode; message: string; retryable: boolean }
    | { event: "cancelled"; message: string };

export type ChatEventEnvelope = {
    contract_version: ChatContractVersion;
    sequence: number;
    payload: ChatEvent;
};

export type ChatMessage = {
    id: string;
    role: "user" | "assistant";
    content: string;
    mode: ChatMode;
    document_ids: string[];
    status: string;
    ai_run_id: string | null;
    model_name: string | null;
    route_reason: ChatRouteReason | null;
    route_confidence: "high" | "medium" | "low" | null;
    input_tokens?: number | null;
    output_tokens?: number | null;
    completed_at?: string | null;
    error_code?: string | null;
    created_at: string;
    sources: ChatSource[];
};

export type ChatConversation = {
    id: string;
    title: string;
    project_id: string | null;
    mode: ChatMode;
    selected_document_ids: string[];
    memory_enabled: boolean;
    memory_write_enabled: boolean;
    created_at: string;
    updated_at: string;
    messages: ChatMessage[];
};

export type ChatConversationSummary = Omit<ChatConversation, "messages">;

export type ChatRouteDecision = {
    mode: ChatMode;
    reason: ChatRouteReason;
    confidence: "high" | "medium" | "low";
    use_documents: boolean;
    use_memory: boolean;
    use_web: boolean;
    search_query: string | null;
};

export type RagDocument = {
    id: string;
    project_id: string | null;
    filename: string;
    original_filename: string;
    content_type: string;
    fingerprint?: string | null;
    status: string;
    created_at: string;
    updated_at: string;
    needs_reindex?: boolean;
};

export type RagIngestionJob = {
    id: string;
    document_id: string;
    user_id: string;
    project_id: string | null;
    status: "pending" | "running" | "completed" | "failed" | string;
    error_message: string | null;
    attempts: number;
    deadline_at: string | null;
    heartbeat_at: string | null;
    started_at: string | null;
    finished_at: string | null;
    created_at: string;
};

export type RagUploadResponse = {
    document: RagDocument;
    ingestion_job: RagIngestionJob;
    duplicate?: boolean;
};
