/**
 * Compatibility wrapper around generated RAG evaluation OpenAPI clients.
 */
import {
    createCaseApiV1RagAdminEvaluationDatasetsDatasetIdCasesPost,
    createDatasetApiV1RagAdminEvaluationDatasetsPost,
    getExportRunApiV1RagAdminEvaluationRunsRunIdExportGetUrl,
    getRunApiV1RagAdminEvaluationRunsRunIdGet,
    importGoldenDatasetApiV1RagAdminEvaluationDatasetsImportGoldenPost,
    listCasesApiV1RagAdminEvaluationDatasetsDatasetIdCasesGet,
    listDatasetsApiV1RagAdminEvaluationDatasetsGet,
    listRunsApiV1RagAdminEvaluationRunsGet,
    probeRetrievalApiV1RagAdminEvaluationProbePost,
    runDatasetApiV1RagAdminEvaluationDatasetsDatasetIdRunsPost,
} from "../generated/endpoints/rag/rag";
import type {
    RagEvalCandidateResponse,
    RagEvalCaseCreateRequest,
    RagEvalCaseResponse,
    RagEvalDatasetCreateRequest,
    RagEvalDatasetResponse,
    RagEvalProbeRequest,
    RagEvalProbeResponse,
    RagEvalRunRequest,
    RagEvalRunResponse,
} from "../generated/models";

export type RagEvalDataset = RagEvalDatasetResponse;
export type RagEvalCase = RagEvalCaseResponse;
export type RagEvalCandidate = RagEvalCandidateResponse;
export type RagEvalProbeResult = RagEvalProbeResponse;
export type RagEvalRun = RagEvalRunResponse;

export async function listRagEvalDatasets(organizationId?: string): Promise<RagEvalDataset[]> {
    return listDatasetsApiV1RagAdminEvaluationDatasetsGet(
        organizationId ? { organization_id: organizationId } : undefined
    );
}

export async function createRagEvalDataset(
    payload: RagEvalDatasetCreateRequest
): Promise<RagEvalDataset> {
    return createDatasetApiV1RagAdminEvaluationDatasetsPost(payload);
}

export async function importGoldenRagEvalDataset(
    organizationId?: string
): Promise<RagEvalDataset> {
    return importGoldenDatasetApiV1RagAdminEvaluationDatasetsImportGoldenPost(
        organizationId ? { organization_id: organizationId } : undefined
    );
}

export async function listRagEvalCases(
    datasetId: string,
    organizationId?: string
): Promise<RagEvalCase[]> {
    return listCasesApiV1RagAdminEvaluationDatasetsDatasetIdCasesGet(
        datasetId,
        organizationId ? { organization_id: organizationId } : undefined
    );
}

export async function createRagEvalCase(
    datasetId: string,
    payload: RagEvalCaseCreateRequest,
    organizationId?: string
): Promise<RagEvalCase> {
    return createCaseApiV1RagAdminEvaluationDatasetsDatasetIdCasesPost(
        datasetId,
        payload,
        organizationId ? { organization_id: organizationId } : undefined
    );
}

export async function probeRagEvaluation(
    payload: RagEvalProbeRequest
): Promise<RagEvalProbeResult> {
    return probeRetrievalApiV1RagAdminEvaluationProbePost(payload);
}

export async function runRagEvalDataset(
    datasetId: string,
    payload: RagEvalRunRequest
): Promise<RagEvalRun> {
    return runDatasetApiV1RagAdminEvaluationDatasetsDatasetIdRunsPost(datasetId, payload);
}

export async function listRagEvalRuns(datasetId?: string): Promise<RagEvalRun[]> {
    return listRunsApiV1RagAdminEvaluationRunsGet(
        datasetId ? { dataset_id: datasetId } : undefined
    );
}

export async function getRagEvalRun(runId: string): Promise<RagEvalRun> {
    return getRunApiV1RagAdminEvaluationRunsRunIdGet(runId);
}

export function ragEvalExportUrl(runId: string, format: "json" | "csv" = "json"): string {
    return getExportRunApiV1RagAdminEvaluationRunsRunIdExportGetUrl(runId, { format });
}
