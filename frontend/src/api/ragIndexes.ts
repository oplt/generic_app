import { apiFetch } from "./client";

export type RagIndexVersion = {
    id: string;
    key: string;
    status: string;
    parser_version: string;
    chunker_version: string;
    embedding_schema_version: string;
    embedding_provider: string;
    embedding_model: string;
    embedding_dimensions: number;
    notes: string | null;
    created_at: string;
    activated_at: string | null;
    retired_at: string | null;
    validated_at: string | null;
};

export type RagIndexStatus = {
    active_version: RagIndexVersion;
    pipeline: Record<string, string | number>;
    schema_embedding_dimensions: number;
    documents_total: number;
    documents_indexed: number;
    documents_current: number;
    documents_stale: number;
    jobs_active: number;
    jobs_failed: number;
    dimension_migration_required: boolean;
    versions: RagIndexVersion[];
};

export type RagReindexStaleResult = {
    requested: number;
    enqueued: number;
    skipped: number;
    job_ids: string[];
    active_index_version: string;
};

export async function getRagIndexStatus(): Promise<RagIndexStatus> {
    return apiFetch("/rag/admin/index-status");
}

export async function createRagIndexVersion(notes?: string): Promise<RagIndexVersion> {
    return apiFetch("/rag/admin/index-versions", {
        method: "POST",
        body: JSON.stringify({ notes: notes ?? null }),
    });
}

export async function validateRagIndexVersion(versionId: string): Promise<RagIndexVersion> {
    return apiFetch(`/rag/admin/index-versions/${versionId}/validate`, { method: "POST" });
}

export async function activateRagIndexVersion(versionId: string): Promise<RagIndexVersion> {
    return apiFetch(`/rag/admin/index-versions/${versionId}/activate`, { method: "POST" });
}

export async function reindexStaleRagDocuments(limit = 50): Promise<RagReindexStaleResult> {
    return apiFetch("/rag/admin/reindex-stale", {
        method: "POST",
        body: JSON.stringify({ limit }),
    });
}
