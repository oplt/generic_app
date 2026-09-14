import { apiFetch, apiFetchItems, apiFetchPage, apiFetchStream, apiUpload, type UploadProgress } from "../../api/client";
import type { ChatConversation, ChatConversationSummary, ChatMessageRequest, ChatMode, RagDocument, RagIngestionJob, RagUploadResponse } from "./types";

export function listChatConversations(): Promise<ChatConversationSummary[]> {
    return apiFetchPage<ChatConversationSummary>("/chat/conversations").then((page) => page.items);
}

export function getChatConversation(conversationId: string): Promise<ChatConversation> {
    return apiFetch(`/chat/conversations/${conversationId}`);
}

export function createChatConversation(
    mode: ChatMode = "auto",
    selectedDocumentIds: string[] = [],
    projectId?: string | null,
    memoryEnabled = true,
    memoryWriteEnabled = true,
): Promise<ChatConversationSummary> {
    return apiFetch("/chat/conversations", {
        method: "POST",
        body: JSON.stringify({
            contract_version: "v1",
            mode,
            project_id: projectId ?? null,
            selected_document_ids: selectedDocumentIds,
            memory_enabled: mode === "documents" ? false : memoryEnabled,
            memory_write_enabled: mode === "documents" ? false : memoryWriteEnabled,
        }),
    });
}

export function updateChatConversation(
    conversationId: string,
    payload: {
        title?: string;
        mode?: ChatMode;
        selected_document_ids?: string[];
        memory_enabled?: boolean;
        memory_write_enabled?: boolean;
    },
): Promise<ChatConversationSummary> {
    return apiFetch(`/chat/conversations/${conversationId}`, {
        method: "PATCH",
        body: JSON.stringify({ contract_version: "v1", ...payload }),
    });
}

export function clearChatConversation(conversationId: string): Promise<void> {
    return apiFetch(`/chat/conversations/${conversationId}/clear`, { method: "POST" });
}

export function renameChatConversation(
    conversationId: string,
    title: string,
): Promise<ChatConversationSummary> {
    return apiFetch(`/chat/conversations/${conversationId}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
    });
}

export function deleteChatConversation(conversationId: string): Promise<void> {
    return apiFetch(`/chat/conversations/${conversationId}`, { method: "DELETE" });
}

export function listRagDocuments(projectId?: string | null): Promise<RagDocument[]> {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return apiFetchItems<RagDocument>(`/rag/documents${query}`);
}

export function uploadRagDocument(
    file: File,
    projectId?: string | null,
    onProgress?: (progress: UploadProgress) => void,
): Promise<RagUploadResponse> {
    const body = new FormData();
    body.append("file", file);
    if (projectId) body.append("project_id", projectId);
    return apiUpload<RagUploadResponse>("/rag/documents/upload", body, { onProgress });
}

export function listRagIngestionJobs(): Promise<RagIngestionJob[]> {
    return apiFetchItems<RagIngestionJob>("/rag/jobs");
}

export function deleteRagDocument(documentId: string): Promise<void> {
    return apiFetch(`/rag/documents/${documentId}`, { method: "DELETE" });
}

export function getRagIngestionJob(jobId: string): Promise<RagIngestionJob> {
    return apiFetch(`/rag/jobs/${jobId}`);
}

export function retryRagIngestionJob(jobId: string): Promise<RagIngestionJob> {
    return apiFetch(`/rag/jobs/${jobId}/retry`, { method: "POST" });
}

export function reindexRagDocument(documentId: string): Promise<RagIngestionJob> {
    return apiFetch(`/rag/documents/${documentId}/reindex`, { method: "POST" });
}

export async function streamChatMessage(
    conversationId: string,
    payload: ChatMessageRequest,
    signal: AbortSignal,
): Promise<Response> {
    return apiFetchStream(`/chat/conversations/${conversationId}/messages/stream`, {
        method: "POST",
        body: JSON.stringify(payload),
        signal,
    });
}
