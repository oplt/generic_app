import { apiFetch } from "./client";

export type ConsoleJob = {
    id: string;
    source: "application" | "rag_ingestion" | string;
    task_id: string;
    job_type: string;
    queue: string;
    state: string;
    raw_status: string;
    created_at: string | null;
    started_at: string | null;
    completed_at: string | null;
    duration_seconds: number | null;
    attempts: number;
    max_attempts: number;
    retries: number;
    related_user_id: string | null;
    related_project_id: string | null;
    related_document_id: string | null;
    correlation_id: string | null;
    operation_id: string | null;
    error_classification: string | null;
    safe_error_summary: string | null;
    stale: boolean;
    can_retry: boolean;
    can_cancel: boolean;
    retry_blocked_reason?: string | null;
    cancel_blocked_reason?: string | null;
    payload_summary: {
        field_names: string[];
        field_count: number;
        redacted_field_count: number;
        source?: string | null;
    };
    trace_hints?: Record<string, string | null>;
};

export type ConsoleJobList = {
    items: ConsoleJob[];
    total: number;
    limit: number;
    offset: number;
};

export async function listConsoleJobs(params?: {
    status?: string;
    job_type?: string;
    queue?: string;
    project_id?: string;
    failed_only?: boolean;
    limit?: number;
    offset?: number;
}): Promise<ConsoleJobList> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.job_type) qs.set("job_type", params.job_type);
    if (params?.queue) qs.set("queue", params.queue);
    if (params?.project_id) qs.set("project_id", params.project_id);
    if (params?.failed_only) qs.set("failed_only", "true");
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return apiFetch(`/admin/jobs${query ? `?${query}` : ""}`);
}

export async function getConsoleJob(jobId: string, source?: string): Promise<ConsoleJob> {
    const qs = source ? `?source=${encodeURIComponent(source)}` : "";
    return apiFetch(`/admin/jobs/${jobId}${qs}`);
}

export async function retryConsoleJob(jobId: string, source?: string): Promise<ConsoleJob> {
    const qs = source ? `?source=${encodeURIComponent(source)}` : "";
    return apiFetch(`/admin/jobs/${jobId}/retry${qs}`, { method: "POST" });
}

export async function cancelConsoleJob(jobId: string, source?: string): Promise<ConsoleJob> {
    const qs = source ? `?source=${encodeURIComponent(source)}` : "";
    return apiFetch(`/admin/jobs/${jobId}/cancel${qs}`, { method: "POST" });
}
