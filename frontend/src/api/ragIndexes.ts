/**
 * Compatibility wrapper around generated RAG index-administration OpenAPI clients.
 */
import {
    activateIndexVersionApiV1RagAdminIndexVersionsVersionIdActivatePost,
    createIndexVersionApiV1RagAdminIndexVersionsPost,
    getIndexStatusApiV1RagAdminIndexStatusGet,
    reindexStaleDocumentsApiV1RagAdminReindexStalePost,
    rollbackIndexVersionApiV1RagAdminIndexVersionsVersionIdRollbackPost,
    validateIndexVersionApiV1RagAdminIndexVersionsVersionIdValidatePost,
} from "../generated/endpoints/rag/rag";
import type {
    RagIndexReindexStaleResponse,
    RagIndexStatusResponse,
    RagIndexVersionResponse,
} from "../generated/models";

export type RagIndexVersion = RagIndexVersionResponse;
export type RagIndexStatus = RagIndexStatusResponse;
export type RagReindexStaleResult = RagIndexReindexStaleResponse;

export async function getRagIndexStatus(): Promise<RagIndexStatus> {
    return getIndexStatusApiV1RagAdminIndexStatusGet();
}

export async function createRagIndexVersion(notes?: string): Promise<RagIndexVersion> {
    return createIndexVersionApiV1RagAdminIndexVersionsPost({
        notes: notes ?? null,
    });
}

export async function validateRagIndexVersion(versionId: string): Promise<RagIndexVersion> {
    return validateIndexVersionApiV1RagAdminIndexVersionsVersionIdValidatePost(versionId);
}

export async function activateRagIndexVersion(versionId: string): Promise<RagIndexVersion> {
    return activateIndexVersionApiV1RagAdminIndexVersionsVersionIdActivatePost(versionId);
}

export async function rollbackRagIndexVersion(versionId: string): Promise<RagIndexVersion> {
    return rollbackIndexVersionApiV1RagAdminIndexVersionsVersionIdRollbackPost(versionId);
}

export async function reindexStaleRagDocuments(limit = 50): Promise<RagReindexStaleResult> {
    return reindexStaleDocumentsApiV1RagAdminReindexStalePost({ limit });
}
