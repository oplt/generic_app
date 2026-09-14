import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Skeleton,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import {
    Storage as StorageIcon,
    Sync as SyncIcon,
    FactCheck as FactCheckIcon,
    WorkOutline as JobsIcon,
} from "@mui/icons-material";

import {
    activateRagIndexVersion,
    createRagIndexVersion,
    getRagIndexStatus,
    reindexStaleRagDocuments,
    rollbackRagIndexVersion,
    validateRagIndexVersion,
} from "../../../api/ragIndexes";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { SectionCard } from "../../../components/ui/SectionCard";
import { StatCard } from "../../../components/ui/StatCard";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";
import { getQueryErrorMessage } from "../../../utils/queryErrors";

const queryKey = ["admin", "rag-index-status"] as const;

export default function AdminRagIndexesView() {
    const client = useQueryClient();
    const toastError = useMutationErrorToast();
    const statusQuery = useQuery({
        queryKey,
        queryFn: getRagIndexStatus,
    });

    const refresh = () => void client.invalidateQueries({ queryKey });

    const createMutation = useMutation({
        mutationFn: () => createRagIndexVersion("Created from admin UI"),
        onSuccess: refresh,
        onError: (error) => toastError(error, "Failed to create index version."),
    });
    const validateMutation = useMutation({
        mutationFn: validateRagIndexVersion,
        onSuccess: refresh,
        onError: (error) => toastError(error, "Failed to validate index version."),
    });
    const activateMutation = useMutation({
        mutationFn: activateRagIndexVersion,
        onSuccess: refresh,
        onError: (error) => toastError(error, "Failed to activate index version."),
    });
    const rollbackMutation = useMutation({
        mutationFn: rollbackRagIndexVersion,
        onSuccess: refresh,
        onError: (error) => toastError(error, "Failed to roll back index version."),
    });
    const reindexMutation = useMutation({
        mutationFn: () => reindexStaleRagDocuments(50),
        onSuccess: refresh,
        onError: (error) => toastError(error, "Failed to enqueue stale reindex jobs."),
    });

    const data = statusQuery.data;
    const readiness = data?.building_readiness;

    return (
        <PageShell title="RAG indexes" maxWidth="xl">
            <SettingsTabs />
            <QueryBoundary
                isLoading={statusQuery.isLoading}
                isError={statusQuery.isError}
                error={statusQuery.error}
                errorFallback="Failed to load RAG index status."
                onRetry={() => void statusQuery.refetch()}
                loadingFallback={<Skeleton variant="rounded" height={320} />}
            >
                {data && (
                    <Stack spacing={2.5}>
                        {data.dimension_migration_required && (
                            <Alert severity="warning">
                                Active embedding dimensions differ from the pgvector column (
                                {data.schema_embedding_dimensions}). Run an Alembic vector-schema
                                migration before activating a mismatched index version.
                            </Alert>
                        )}
                        {data.desired_index_version &&
                            data.desired_index_version !== data.active_version.key && (
                                <Alert severity="info">
                                    Runtime config desires {data.desired_index_version}. Active
                                    remains {data.active_version.key}
                                    {data.building_version
                                        ? ` while candidate ${data.building_version.key} is ${data.building_version.status}.`
                                        : "."}
                                </Alert>
                            )}
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: {
                                    xs: "1fr",
                                    md: "repeat(4, minmax(0, 1fr))",
                                },
                            }}
                        >
                            <StatCard
                                label="Active version"
                                value={data.active_version.key}
                                icon={<StorageIcon fontSize="small" />}
                            />
                            <StatCard
                                label="Documents current"
                                value={String(data.documents_current)}
                                icon={<FactCheckIcon fontSize="small" />}
                            />
                            <StatCard
                                label="Documents incomplete"
                                value={String(data.documents_incomplete ?? data.documents_stale)}
                                icon={<SyncIcon fontSize="small" />}
                                color="warning"
                            />
                            <StatCard
                                label="Jobs active"
                                value={String(data.jobs_active)}
                                icon={<JobsIcon fontSize="small" />}
                            />
                        </Box>

                        <SectionCard
                            title="Active pipeline"
                            description="Serving traffic from the active index version. Candidates build side-by-side."
                            action={
                                <Stack direction="row" spacing={1}>
                                    <Button
                                        variant="outlined"
                                        onClick={() => createMutation.mutate()}
                                        disabled={createMutation.isPending}
                                    >
                                        Snapshot version
                                    </Button>
                                    <Button
                                        variant="contained"
                                        onClick={() => reindexMutation.mutate()}
                                        disabled={
                                            reindexMutation.isPending ||
                                            (data.documents_incomplete ?? data.documents_stale) === 0
                                        }
                                    >
                                        Build missing
                                    </Button>
                                </Stack>
                            }
                        >
                            <Stack spacing={0.75}>
                                <Typography variant="body2">
                                    Model: {data.active_version.embedding_provider}/
                                    {data.active_version.embedding_model} (
                                    {data.active_version.embedding_dimensions}d)
                                </Typography>
                                <Typography variant="body2">
                                    Parser {data.active_version.parser_version} · Chunker{" "}
                                    {data.active_version.chunker_version} · Schema{" "}
                                    {data.active_version.embedding_schema_version}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Indexed {data.documents_indexed} / {data.documents_total} documents ·{" "}
                                    {data.jobs_failed} failed jobs
                                </Typography>
                                {readiness && (
                                    <Typography variant="body2" color="text.secondary">
                                        Candidate coverage {(Number(readiness.coverage) * 100).toFixed(1)}%
                                        · incomplete {String(readiness.documents_incomplete)} · chunks{" "}
                                        {String(readiness.chunk_count)}
                                    </Typography>
                                )}
                                {reindexMutation.isSuccess && (
                                    <Alert severity="success">
                                        Enqueued {reindexMutation.data.enqueued} job(s) targeting{" "}
                                        {reindexMutation.data.target_index_version ??
                                            reindexMutation.data.active_index_version}.
                                    </Alert>
                                )}
                                {reindexMutation.isError && (
                                    <Alert severity="error">
                                        {getQueryErrorMessage(
                                            reindexMutation.error,
                                            "Failed to enqueue reindex jobs."
                                        )}
                                    </Alert>
                                )}
                            </Stack>
                        </SectionCard>

                        <SectionCard
                            title="Index versions"
                            description="Lifecycle: building → validated → active → retired. Activate only after validation; rollback reuses retained chunks."
                        >
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>Key</TableCell>
                                        <TableCell>Status</TableCell>
                                        <TableCell>Model</TableCell>
                                        <TableCell>Dims</TableCell>
                                        <TableCell align="right">Actions</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {(data.versions ?? []).map((version) => (
                                        <TableRow key={version.id}>
                                            <TableCell>{version.key}</TableCell>
                                            <TableCell>{version.status}</TableCell>
                                            <TableCell>
                                                {version.embedding_provider}/{version.embedding_model}
                                            </TableCell>
                                            <TableCell>{version.embedding_dimensions}</TableCell>
                                            <TableCell align="right">
                                                <Stack direction="row" spacing={1} justifyContent="flex-end">
                                                    {version.status === "building" && (
                                                        <Button
                                                            size="small"
                                                            onClick={() =>
                                                                validateMutation.mutate(version.id)
                                                            }
                                                        >
                                                            Validate
                                                        </Button>
                                                    )}
                                                    {version.status === "validated" && (
                                                        <Button
                                                            size="small"
                                                            variant="contained"
                                                            onClick={() =>
                                                                activateMutation.mutate(version.id)
                                                            }
                                                        >
                                                            Activate
                                                        </Button>
                                                    )}
                                                    {version.status === "retired" && (
                                                        <Button
                                                            size="small"
                                                            onClick={() =>
                                                                rollbackMutation.mutate(version.id)
                                                            }
                                                        >
                                                            Rollback
                                                        </Button>
                                                    )}
                                                </Stack>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </SectionCard>
                    </Stack>
                )}
            </QueryBoundary>
        </PageShell>
    );
}
