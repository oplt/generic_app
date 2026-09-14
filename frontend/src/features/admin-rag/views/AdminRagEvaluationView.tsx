import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Collapse,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Skeleton,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";
import { Fragment, useMemo, useState } from "react";

import {
    createRagEvalCase,
    createRagEvalDataset,
    importGoldenRagEvalDataset,
    listRagEvalCases,
    listRagEvalDatasets,
    listRagEvalRuns,
    probeRagEvaluation,
    ragEvalExportUrl,
    runRagEvalDataset,
    type RagEvalCandidate,
    type RagEvalProbeResult,
} from "../../../api/ragEvaluation";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { SectionCard } from "../../../components/ui/SectionCard";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";

type Strategy = "vector" | "lexical" | "hybrid_rrf";

function CandidateRows({ candidates }: { candidates: RagEvalCandidate[] }) {
    const [openId, setOpenId] = useState<string | null>(null);
    return (
        <Table size="small">
            <TableHead>
                <TableRow>
                    <TableCell>Rank</TableCell>
                    <TableCell>Document</TableCell>
                    <TableCell>Chunk</TableCell>
                    <TableCell>V/L rank</TableCell>
                    <TableCell>Scores</TableCell>
                    <TableCell>Included</TableCell>
                </TableRow>
            </TableHead>
            <TableBody>
                {candidates.map((candidate) => (
                    <Fragment key={candidate.chunk_id}>
                        <TableRow
                            hover
                            sx={{ cursor: "pointer" }}
                            onClick={() =>
                                setOpenId((current) =>
                                    current === candidate.chunk_id ? null : candidate.chunk_id
                                )
                            }
                        >
                            <TableCell>{candidate.rank}</TableCell>
                            <TableCell>{candidate.filename || candidate.document_id}</TableCell>
                            <TableCell>{candidate.chunk_id}</TableCell>
                            <TableCell>
                                {candidate.vector_rank ?? "—"} / {candidate.lexical_rank ?? "—"}
                            </TableCell>
                            <TableCell>
                                v={candidate.vector_score?.toFixed?.(3) ?? "—"} · l=
                                {candidate.lexical_score?.toFixed?.(3) ?? "—"} · f=
                                {candidate.fused_score?.toFixed?.(3) ?? "—"} · r=
                                {candidate.reranker_score?.toFixed?.(3) ?? "—"}
                            </TableCell>
                            <TableCell>{candidate.included ? "yes" : "no"}</TableCell>
                        </TableRow>
                        <TableRow>
                            <TableCell colSpan={6} sx={{ py: 0, border: 0 }}>
                                <Collapse in={openId === candidate.chunk_id}>
                                    <Box sx={{ py: 1.5, whiteSpace: "pre-wrap" }}>
                                        <Typography variant="body2">{candidate.content}</Typography>
                                    </Box>
                                </Collapse>
                            </TableCell>
                        </TableRow>
                    </Fragment>
                ))}
            </TableBody>
        </Table>
    );
}

export default function AdminRagEvaluationView() {
    const client = useQueryClient();
    const toastError = useMutationErrorToast();
    const [datasetId, setDatasetId] = useState<string>("");
    const [query, setQuery] = useState("What does error ZX-204 mean?");
    const [strategy, setStrategy] = useState<Strategy>("hybrid_rrf");
    const [topK, setTopK] = useState(5);
    const [projectId, setProjectId] = useState("");
    const [caseQuestion, setCaseQuestion] = useState("");
    const [caseChunks, setCaseChunks] = useState("");
    const [baselineRunId, setBaselineRunId] = useState("");
    const [probe, setProbe] = useState<RagEvalProbeResult | null>(null);

    const datasetsQuery = useQuery({
        queryKey: ["admin", "rag-eval-datasets"],
        queryFn: () => listRagEvalDatasets(),
    });
    const casesQuery = useQuery({
        queryKey: ["admin", "rag-eval-cases", datasetId],
        queryFn: () => listRagEvalCases(datasetId),
        enabled: Boolean(datasetId),
    });
    const runsQuery = useQuery({
        queryKey: ["admin", "rag-eval-runs", datasetId],
        queryFn: () => listRagEvalRuns(datasetId || undefined),
        enabled: Boolean(datasetId),
    });

    const selectedDataset = useMemo(
        () => datasetsQuery.data?.find((item) => item.id === datasetId) ?? null,
        [datasetId, datasetsQuery.data]
    );

    const refreshDatasets = () =>
        void client.invalidateQueries({ queryKey: ["admin", "rag-eval-datasets"] });
    const refreshCases = () =>
        void client.invalidateQueries({ queryKey: ["admin", "rag-eval-cases", datasetId] });
    const refreshRuns = () =>
        void client.invalidateQueries({ queryKey: ["admin", "rag-eval-runs", datasetId] });

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

    return (
        <PageShell title="RAG evaluation" maxWidth="xl">
            <SettingsTabs />
            <QueryBoundary
                isLoading={datasetsQuery.isLoading}
                isError={datasetsQuery.isError}
                error={datasetsQuery.error}
                errorFallback="Failed to load evaluation datasets."
                onRetry={() => void datasetsQuery.refetch()}
                loadingFallback={<Skeleton variant="rounded" height={320} />}
            >
                <Stack spacing={2.5}>
                    <Alert severity="info">
                        Admin/developer workbench for comparing retrieval strategies. Datasets and
                        runs are tenant-scoped. Generation LLM judges are optional and off by
                        default.
                    </Alert>

                    <SectionCard title="Datasets">
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mb: 2 }}>
                            <Button
                                variant="contained"
                                onClick={() => createDatasetMutation.mutate()}
                                disabled={createDatasetMutation.isPending}
                            >
                                New dataset
                            </Button>
                            <Button
                                variant="outlined"
                                onClick={() => importGoldenMutation.mutate()}
                                disabled={importGoldenMutation.isPending}
                            >
                                Import golden_v1
                            </Button>
                            <FormControl sx={{ minWidth: 260 }}>
                                <InputLabel id="dataset-label">Dataset</InputLabel>
                                <Select
                                    labelId="dataset-label"
                                    label="Dataset"
                                    value={datasetId}
                                    onChange={(event) => setDatasetId(event.target.value)}
                                >
                                    {(datasetsQuery.data ?? []).map((dataset) => (
                                        <MenuItem key={dataset.id} value={dataset.id}>
                                            {dataset.name}
                                        </MenuItem>
                                    ))}
                                </Select>
                            </FormControl>
                        </Stack>
                        {selectedDataset && (
                            <Typography variant="body2" color="text.secondary">
                                {selectedDataset.description || "No description"} · tags:{" "}
                                {selectedDataset.tags?.join(", ") || "none"}
                            </Typography>
                        )}
                    </SectionCard>

                    <SectionCard title="Interactive probe">
                        <Stack spacing={1.5}>
                            <TextField
                                label="Query"
                                value={query}
                                onChange={(event) => setQuery(event.target.value)}
                                fullWidth
                            />
                            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                                <FormControl sx={{ minWidth: 180 }}>
                                    <InputLabel id="strategy-label">Strategy</InputLabel>
                                    <Select
                                        labelId="strategy-label"
                                        label="Strategy"
                                        value={strategy}
                                        onChange={(event) =>
                                            setStrategy(event.target.value as Strategy)
                                        }
                                    >
                                        <MenuItem value="hybrid_rrf">hybrid_rrf</MenuItem>
                                        <MenuItem value="vector">vector</MenuItem>
                                        <MenuItem value="lexical">lexical</MenuItem>
                                    </Select>
                                </FormControl>
                                <TextField
                                    label="top_k"
                                    type="number"
                                    value={topK}
                                    onChange={(event) => setTopK(Number(event.target.value) || 5)}
                                    sx={{ width: 120 }}
                                />
                                <TextField
                                    label="Project ID (optional)"
                                    value={projectId}
                                    onChange={(event) => setProjectId(event.target.value)}
                                    fullWidth
                                />
                                <Button
                                    variant="contained"
                                    onClick={() => probeMutation.mutate()}
                                    disabled={probeMutation.isPending || !query.trim()}
                                >
                                    Probe
                                </Button>
                            </Stack>
                            {probe && (
                                <Stack spacing={1.5}>
                                    <Typography variant="body2">
                                        strategy={probe.strategy} · latencies(ms):{" "}
                                        {Object.entries(probe.latencies_ms ?? {})
                                            .map(([key, value]) => `${key}=${value}`)
                                            .join(" · ")}
                                    </Typography>
                                    <CandidateRows candidates={probe.candidates ?? []} />
                                    <Box>
                                        <Typography variant="subtitle2" gutterBottom>
                                            Assembled context
                                        </Typography>
                                        <Typography
                                            component="pre"
                                            variant="body2"
                                            sx={{
                                                whiteSpace: "pre-wrap",
                                                p: 1.5,
                                                bgcolor: "action.hover",
                                                borderRadius: 1,
                                            }}
                                        >
                                            {probe.assembled_context || "(empty)"}
                                        </Typography>
                                    </Box>
                                </Stack>
                            )}
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Cases">
                        {!datasetId ? (
                            <Typography color="text.secondary">Select a dataset first.</Typography>
                        ) : (
                            <Stack spacing={1.5}>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                                    <TextField
                                        label="Question"
                                        value={caseQuestion}
                                        onChange={(event) => setCaseQuestion(event.target.value)}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Expected chunk IDs (comma-separated)"
                                        value={caseChunks}
                                        onChange={(event) => setCaseChunks(event.target.value)}
                                        fullWidth
                                    />
                                    <Button
                                        variant="outlined"
                                        onClick={() => createCaseMutation.mutate()}
                                        disabled={
                                            createCaseMutation.isPending || !caseQuestion.trim()
                                        }
                                    >
                                        Add case
                                    </Button>
                                </Stack>
                                <Table size="small">
                                    <TableHead>
                                        <TableRow>
                                            <TableCell>Question</TableCell>
                                            <TableCell>Expected chunks</TableCell>
                                            <TableCell>Tags</TableCell>
                                        </TableRow>
                                    </TableHead>
                                    <TableBody>
                                        {(casesQuery.data ?? []).map((item) => (
                                            <TableRow key={item.id}>
                                                <TableCell>{item.question}</TableCell>
                                                <TableCell>
                                                    {item.expected_chunk_ids?.join(", ") || "—"}
                                                </TableCell>
                                                <TableCell>{item.tags?.join(", ") || "—"}</TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </Stack>
                        )}
                    </SectionCard>

                    <SectionCard title="Runs">
                        {!datasetId ? (
                            <Typography color="text.secondary">Select a dataset first.</Typography>
                        ) : (
                            <Stack spacing={1.5}>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
                                    <TextField
                                        label="Baseline run ID (optional)"
                                        value={baselineRunId}
                                        onChange={(event) => setBaselineRunId(event.target.value)}
                                        fullWidth
                                    />
                                    <Button
                                        variant="contained"
                                        onClick={() => runMutation.mutate()}
                                        disabled={runMutation.isPending}
                                    >
                                        Run evaluation
                                    </Button>
                                </Stack>
                                <Table size="small">
                                    <TableHead>
                                        <TableRow>
                                            <TableCell>Name</TableCell>
                                            <TableCell>Status</TableCell>
                                            <TableCell>Metrics</TableCell>
                                            <TableCell>Δ vs baseline</TableCell>
                                            <TableCell>Export</TableCell>
                                        </TableRow>
                                    </TableHead>
                                    <TableBody>
                                        {(runsQuery.data ?? []).map((run) => (
                                            <TableRow key={run.id}>
                                                <TableCell>
                                                    {run.name}
                                                    <Typography variant="caption" display="block">
                                                        {run.id}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell>{run.status}</TableCell>
                                                <TableCell>
                                                    R@K={String(run.metrics?.recall_at_k ?? "—")} · MRR=
                                                    {String(run.metrics?.mrr ?? "—")} · nDCG=
                                                    {String(run.metrics?.ndcg_at_k ?? "—")}
                                                </TableCell>
                                                <TableCell>
                                                    {run.comparison?.deltas
                                                        ? Object.entries(run.comparison.deltas)
                                                              .map(
                                                                  ([key, value]) =>
                                                                      `${key}:${value > 0 ? "+" : ""}${value}`
                                                              )
                                                              .join(" · ")
                                                        : "—"}
                                                </TableCell>
                                                <TableCell>
                                                    <Button
                                                        size="small"
                                                        href={ragEvalExportUrl(run.id, "json")}
                                                    >
                                                        JSON
                                                    </Button>
                                                    <Button
                                                        size="small"
                                                        href={ragEvalExportUrl(run.id, "csv")}
                                                    >
                                                        CSV
                                                    </Button>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </Stack>
                        )}
                    </SectionCard>
                </Stack>
            </QueryBoundary>
        </PageShell>
    );
}
