import { apiFetch } from "./client";

export type OperationalState =
    | "healthy"
    | "degraded"
    | "unavailable"
    | "not_required"
    | "unknown";

export type DiagnosticsSection = {
    state: OperationalState;
    detail: string | null;
    metrics: Record<string, unknown>;
};

export type AiProviderDiagnostics = {
    key: string;
    label: string;
    configured: boolean;
    state: OperationalState;
    detail: string;
    supports_generation: boolean;
    supports_embeddings: boolean;
    latency_summary_ms: number | null;
};

export type DiagnosticsReport = {
    generated_at: string;
    overall_state: OperationalState;
    application: DiagnosticsSection;
    postgresql: DiagnosticsSection;
    redis: DiagnosticsSection;
    celery: DiagnosticsSection;
    storage: DiagnosticsSection;
    ai_providers: AiProviderDiagnostics[];
    rag: DiagnosticsSection;
    observability_hints: Record<string, unknown>;
};

export async function getDiagnostics(): Promise<DiagnosticsReport> {
    return apiFetch("/admin/diagnostics");
}
