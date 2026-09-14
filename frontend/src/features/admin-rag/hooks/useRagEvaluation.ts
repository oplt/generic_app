import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
    createRagEvalCase,
    createRagEvalDataset,
    importGoldenRagEvalDataset,
    listRagEvalCases,
    listRagEvalDatasets,
    listRagEvalRuns,
    probeRagEvaluation,
    runRagEvalDataset,
    type RagEvalProbeResult,
} from "../../../api/ragEvaluation";
import { queryKeys } from "../../../config/queryKeys";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";

export type RagEvalStrategy = "vector" | "lexical" | "hybrid_rrf";

export function useRagEvaluation() {
    const client = useQueryClient();
    const toastError = useMutationErrorToast();
    const [datasetId, setDatasetId] = useState("");
    const [query, setQuery] = useState("What does error ZX-204 mean?");
    const [strategy, setStrategy] = useState<RagEvalStrategy>("hybrid_rrf");
    const [topK, setTopK] = useState(5);
    const [projectId, setProjectId] = useState("");
    const [caseQuestion, setCaseQuestion] = useState("");
    const [caseChunks, setCaseChunks] = useState("");
    const [baselineRunId, setBaselineRunId] = useState("");
    const [probe, setProbe] = useState<RagEvalProbeResult | null>(null);

    const datasetsQuery = useQuery({
        queryKey: queryKeys.admin.ragEvalDatasets,
        queryFn: () => listRagEvalDatasets(),
    });
    const casesQuery = useQuery({
        queryKey: queryKeys.admin.ragEvalCases(datasetId),
        queryFn: () => listRagEvalCases(datasetId),
        enabled: Boolean(datasetId),
    });
    const runsQuery = useQuery({
        queryKey: queryKeys.admin.ragEvalRuns(datasetId),
        queryFn: () => listRagEvalRuns(datasetId || undefined),
        enabled: Boolean(datasetId),
    });

    const selectedDataset = useMemo(
        () => datasetsQuery.data?.find((item) => item.id === datasetId) ?? null,
        [datasetId, datasetsQuery.data]
    );

    const refreshDatasets = () =>
        void client.invalidateQueries({ queryKey: queryKeys.admin.ragEvalDatasets });
    const refreshCases = () =>
        void client.invalidateQueries({ queryKey: queryKeys.admin.ragEvalCases(datasetId) });
    const refreshRuns = () =>
        void client.invalidateQueries({ queryKey: queryKeys.admin.ragEvalRuns(datasetId) });

    const createDatasetMutation = useMutation({
        mutationFn: () => createRagEvalDataset({ name: `eval-${Date.now()}`, tags: ["manual"] }),
        onSuccess: (dataset) => {
            refreshDatasets();
            setDatasetId(dataset.id);
        },
        onError: (error) => toastError(error, "Failed to create dataset."),
    });
    const importGoldenMutation = useMutation({
        mutationFn: () => importGoldenRagEvalDataset(),
        onSuccess: (dataset) => {
            refreshDatasets();
            setDatasetId(dataset.id);
        },
        onError: (error) => toastError(error, "Failed to import golden dataset."),
    });
    const createCaseMutation = useMutation({
        mutationFn: () =>
            createRagEvalCase(datasetId, {
                question: caseQuestion,
                expected_chunk_ids: caseChunks
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                tags: ["manual"],
            }),
        onSuccess: () => {
            setCaseQuestion("");
            setCaseChunks("");
            refreshCases();
        },
        onError: (error) => toastError(error, "Failed to create case."),
    });
    const probeMutation = useMutation({
        mutationFn: () =>
            probeRagEvaluation({
                query,
                strategy,
                top_k: topK,
                project_id: projectId || undefined,
                include_generation_judges: false,
            }),
        onSuccess: setProbe,
        onError: (error) => toastError(error, "Probe failed."),
    });
    const runMutation = useMutation({
        mutationFn: () =>
            runRagEvalDataset(datasetId, {
                name: `${strategy}-k${topK}`,
                strategy,
                top_k: topK,
                baseline_run_id: baselineRunId || undefined,
                project_id: projectId || undefined,
            }),
        onSuccess: refreshRuns,
        onError: (error) => toastError(error, "Evaluation run failed."),
    });

    return {
        datasetId,
        setDatasetId,
        query,
        setQuery,
        strategy,
        setStrategy,
        topK,
        setTopK,
        projectId,
        setProjectId,
        caseQuestion,
        setCaseQuestion,
        caseChunks,
        setCaseChunks,
        baselineRunId,
        setBaselineRunId,
        probe,
        datasetsQuery,
        casesQuery,
        runsQuery,
        selectedDataset,
        createDatasetMutation,
        importGoldenMutation,
        createCaseMutation,
        probeMutation,
        runMutation,
    };
}

export type RagEvaluationModel = ReturnType<typeof useRagEvaluation>;
