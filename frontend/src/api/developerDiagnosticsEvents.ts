export const DEVELOPER_DIAGNOSTICS_EVENT = "generic-app:developer-diagnostics";
export const DEVELOPER_DIAGNOSTICS_HEADER = "X-Developer-Diagnostics";

export type DeveloperRequestSummary = {
    method: string;
    path: string;
    status_code: number | null;
    duration_ms: number;
    correlation_id: string | null;
    trace_id: string | null;
    sql_query_count: number;
    db_duration_ms: number;
    cache_hits: number;
    cache_misses: number;
    external_calls: Array<{ provider: string; operation: string; latency_ms?: number }>;
    celery_tasks: string[];
    rag_stages: string[];
    rag_retrieved_chunk_count: number | null;
};

export function publishDeveloperDiagnostics(summary: DeveloperRequestSummary) {
    if (typeof window === "undefined") return;
    window.dispatchEvent(new CustomEvent(DEVELOPER_DIAGNOSTICS_EVENT, { detail: summary }));
}

export function parseDeveloperDiagnosticsHeader(
    value: string | null
): DeveloperRequestSummary | null {
    if (!value) return null;
    try {
        return JSON.parse(value) as DeveloperRequestSummary;
    } catch {
        return null;
    }
}
