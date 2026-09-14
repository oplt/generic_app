import { apiFetch } from "./client";

export type RagEvalDataset = {
    id: string;
    user_id: string;
    organization_id: string | null;
    name: string;
    description: string | null;
    tags: string[];
    created_at: string;
    updated_at: string;
};

export type RagEvalCase = {
    id: string;
    dataset_id: string;
    question: string;
    expected_document_ids: string[];
    expected_chunk_ids: string[];
    expected_sources: string[];
    expected_facts: string[];
    judgments: Record<string, number>;
    tags: string[];
    notes: string | null;
    created_at: string;
};

export type RagEvalCandidate = {
    rank: number;
    chunk_id: string;
    document_id: string;
    filename: string;
    chunk_index: number;
    page_number?: number | null;
    section?: string | null;
    content: string;
    vector_rank?: number | null;
    lexical_rank?: number | null;
    vector_score?: number | null;
    lexical_score?: number | null;
    fused_score?: number | null;
    reranker_score?: number | null;
    included?: boolean;
    metadata?: Record<string, unknown>;
};

export type RagEvalProbeResult = {
    strategy: string;
    top_k: number;
    candidates: RagEvalCandidate[];
    context_chunks: RagEvalCandidate[];
    assembled_context: string;
    latencies_ms: Record<string, number>;
    generation?: {
        answer: string | null;
        scores: Record<string, number> | null;
        provider: string | null;
    };
};

export type RagEvalRun = {
    id: string;
    dataset_id: string;
    user_id: string;
    organization_id: string | null;
    name: string;
    status: string;
    configuration: Record<string, unknown>;
    metrics: Record<string, number>;
    latency: Record<string, { mean?: number; p50?: number }>;
    baseline_run_id: string | null;
    comparison: { baseline_run_id: string; deltas: Record<string, number> } | null;
    error_message: string | null;
    created_at: string;
    completed_at: string | null;
    items?: Array<{
        id: string;
        case_id: string;
        ranked_chunk_ids: string[];
        metrics: Record<string, number>;
        score: number;
    }>;
};

const base = "/rag/admin/evaluation";

export async function listRagEvalDatasets(organizationId?: string): Promise<RagEvalDataset[]> {
    const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : "";
    return apiFetch(`${base}/datasets${query}`);
}

export async function createRagEvalDataset(payload: {
    name: string;
    description?: string;
    tags?: string[];
    organization_id?: string | null;
}): Promise<RagEvalDataset> {
    return apiFetch(`${base}/datasets`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function importGoldenRagEvalDataset(
    organizationId?: string
): Promise<RagEvalDataset> {
    const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : "";
    return apiFetch(`${base}/datasets/import-golden${query}`, { method: "POST" });
}

export async function listRagEvalCases(
    datasetId: string,
    organizationId?: string
): Promise<RagEvalCase[]> {
    const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : "";
    return apiFetch(`${base}/datasets/${datasetId}/cases${query}`);
}

export async function createRagEvalCase(
    datasetId: string,
    payload: {
        question: string;
        expected_chunk_ids?: string[];
        expected_document_ids?: string[];
        tags?: string[];
        notes?: string;
    },
    organizationId?: string
): Promise<RagEvalCase> {
    const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : "";
    return apiFetch(`${base}/datasets/${datasetId}/cases${query}`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function probeRagEvaluation(payload: {
    query: string;
    project_id?: string;
    document_ids?: string[];
    strategy?: "vector" | "lexical" | "hybrid_rrf";
    top_k?: number;
    include_generation_judges?: boolean;
}): Promise<RagEvalProbeResult> {
    return apiFetch(`${base}/probe`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function runRagEvalDataset(
    datasetId: string,
    payload: {
        name?: string;
        strategy?: "vector" | "lexical" | "hybrid_rrf";
        top_k?: number;
        baseline_run_id?: string;
        include_generation_judges?: boolean;
        project_id?: string;
    }
): Promise<RagEvalRun> {
    return apiFetch(`${base}/datasets/${datasetId}/runs`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function listRagEvalRuns(datasetId?: string): Promise<RagEvalRun[]> {
    const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : "";
    return apiFetch(`${base}/runs${query}`);
}

export async function getRagEvalRun(runId: string): Promise<RagEvalRun> {
    return apiFetch(`${base}/runs/${runId}`);
}

export function ragEvalExportUrl(runId: string, format: "json" | "csv" = "json"): string {
    return `/api/v1${base}/runs/${runId}/export?format=${format}`;
}
