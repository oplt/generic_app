import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    FormControl,
    FormControlLabel,
    InputLabel,
    MenuItem,
    Select,
    Skeleton,
    Stack,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";
import { useState } from "react";

import {
    cancelConsoleJob,
    getConsoleJob,
    listConsoleJobs,
    retryConsoleJob,
    type ConsoleJob,
} from "../../../api/jobs";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { SectionCard } from "../../../components/ui/SectionCard";
import { useMutationErrorToast } from "../../../hooks/useMutationErrorToast";

const queryKey = ["admin", "jobs"] as const;

function stateColor(state: string): "default" | "success" | "warning" | "error" | "info" {
    if (state === "succeeded") return "success";
    if (state === "failed" || state === "stale") return "error";
    if (state === "running" || state === "retrying") return "warning";
    if (state === "cancelled") return "default";
    return "info";
}

export default function AdminJobsView() {
    const client = useQueryClient();
    const toastError = useMutationErrorToast();
    const [status, setStatus] = useState("");
    const [jobType, setJobType] = useState("");
    const [queue, setQueue] = useState("");
    const [projectId, setProjectId] = useState("");
    const [failedOnly, setFailedOnly] = useState(false);
    const [selected, setSelected] = useState<ConsoleJob | null>(null);

    const listQuery = useQuery({
        queryKey: [...queryKey, status, jobType, queue, projectId, failedOnly],
        queryFn: () =>
            listConsoleJobs({
                status: status || undefined,
                job_type: jobType || undefined,
                queue: queue || undefined,
                project_id: projectId || undefined,
                failed_only: failedOnly || undefined,
                limit: 100,
            }),
    });

    const refresh = () => void client.invalidateQueries({ queryKey });

    const detailMutation = useMutation({
        mutationFn: (job: ConsoleJob) => getConsoleJob(job.id, job.source),
        onSuccess: setSelected,
        onError: (error) => toastError(error, "Failed to load job detail."),
    });
    const retryMutation = useMutation({
        mutationFn: (job: ConsoleJob) => retryConsoleJob(job.id, job.source),
        onSuccess: (job) => {
            setSelected(job);
            refresh();
        },
        onError: (error) => toastError(error, "Retry failed."),
    });
    const cancelMutation = useMutation({
        mutationFn: (job: ConsoleJob) => cancelConsoleJob(job.id, job.source),
        onSuccess: (job) => {
            setSelected(job);
            refresh();
        },
        onError: (error) => toastError(error, "Cancel failed."),
    });

    return (
        <PageShell title="Jobs" maxWidth="xl">
            <SettingsTabs />
            <QueryBoundary
                isLoading={listQuery.isLoading}
                isError={listQuery.isError}
                error={listQuery.error}
                errorFallback="Failed to load jobs."
                onRetry={() => void listQuery.refetch()}
                loadingFallback={<Skeleton variant="rounded" height={320} />}
            >
                <Stack spacing={2.5}>
                    <Alert severity="info">
                        Aggregates <code>application_jobs</code> and RAG ingestion jobs. Payloads are
                        redacted. Retry is limited to RAG ingestion; cancel only applies to queued /
                        pending jobs. No arbitrary Celery invoke.
                    </Alert>

                    <SectionCard title="Filters">
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} useFlexGap>
                            <FormControl sx={{ minWidth: 160 }}>
                                <InputLabel id="status-label">Status</InputLabel>
                                <Select
                                    labelId="status-label"
                                    label="Status"
                                    value={status}
                                    onChange={(event) => setStatus(event.target.value)}
                                >
                                    <MenuItem value="">Any</MenuItem>
                                    {[
                                        "queued",
                                        "running",
                                        "retrying",
                                        "succeeded",
                                        "failed",
                                        "cancelled",
                                        "stale",
                                    ].map((value) => (
                                        <MenuItem key={value} value={value}>
                                            {value}
                                        </MenuItem>
                                    ))}
                                </Select>
                            </FormControl>
                            <TextField
                                label="Job type"
                                value={jobType}
                                onChange={(event) => setJobType(event.target.value)}
                            />
                            <TextField
                                label="Queue"
                                value={queue}
                                onChange={(event) => setQueue(event.target.value)}
                            />
                            <TextField
                                label="Project ID"
                                value={projectId}
                                onChange={(event) => setProjectId(event.target.value)}
                                fullWidth
                            />
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={failedOnly}
                                        onChange={(event) => setFailedOnly(event.target.checked)}
                                    />
                                }
                                label="Failures / stale"
                            />
                        </Stack>
                    </SectionCard>

                    <SectionCard title={`Jobs (${listQuery.data?.total ?? 0})`}>
                        <Table size="small">
                            <TableHead>
                                <TableRow>
                                    <TableCell>Type</TableCell>
                                    <TableCell>State</TableCell>
                                    <TableCell>Queue</TableCell>
                                    <TableCell>Attempts</TableCell>
                                    <TableCell>Created</TableCell>
                                    <TableCell>Error</TableCell>
                                    <TableCell />
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {(listQuery.data?.items ?? []).map((job) => (
                                    <TableRow key={`${job.source}:${job.id}`} hover>
                                        <TableCell>
                                            {job.job_type}
                                            <Typography variant="caption" display="block">
                                                {job.source} · {job.id}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>
                                            <Chip
                                                size="small"
                                                label={job.state}
                                                color={stateColor(job.state)}
                                            />
                                        </TableCell>
                                        <TableCell>{job.queue}</TableCell>
                                        <TableCell>
                                            {job.attempts}/{job.max_attempts}
                                        </TableCell>
                                        <TableCell>
                                            {job.created_at
                                                ? new Date(job.created_at).toLocaleString()
                                                : "—"}
                                        </TableCell>
                                        <TableCell>
                                            {job.safe_error_summary || "—"}
                                        </TableCell>
                                        <TableCell>
                                            <Button
                                                size="small"
                                                onClick={() => detailMutation.mutate(job)}
                                            >
                                                Detail
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </SectionCard>

                    {selected && (
                        <SectionCard title="Job detail">
                            <Stack spacing={1.5}>
                                <Typography variant="body2">
                                    {selected.job_type} · {selected.source} · state={selected.state} ·
                                    queue={selected.queue}
                                </Typography>
                                <Typography variant="body2">
                                    correlation={selected.correlation_id || "—"} · operation=
                                    {selected.operation_id || "—"}
                                </Typography>
                                <Typography variant="body2">
                                    user={selected.related_user_id || "—"} · project=
                                    {selected.related_project_id || "—"} · document=
                                    {selected.related_document_id || "—"}
                                </Typography>
                                <Typography variant="body2">
                                    duration={selected.duration_seconds ?? "—"}s · retries=
                                    {selected.retries} · error=
                                    {selected.safe_error_summary || "none"}
                                </Typography>
                                <Box
                                    component="pre"
                                    sx={{
                                        p: 1.5,
                                        bgcolor: "action.hover",
                                        borderRadius: 1,
                                        whiteSpace: "pre-wrap",
                                    }}
                                >
                                    {JSON.stringify(selected.payload_summary, null, 2)}
                                </Box>
                                {selected.trace_hints && (
                                    <Typography variant="body2" color="text.secondary">
                                        Trace hints: {JSON.stringify(selected.trace_hints)} — use
                                        correlation/operation IDs in Observability / Tempo explore.
                                    </Typography>
                                )}
                                <Stack direction="row" spacing={1}>
                                    <Button
                                        variant="contained"
                                        disabled={!selected.can_retry || retryMutation.isPending}
                                        onClick={() => retryMutation.mutate(selected)}
                                    >
                                        Retry
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        color="warning"
                                        disabled={!selected.can_cancel || cancelMutation.isPending}
                                        onClick={() => cancelMutation.mutate(selected)}
                                    >
                                        Cancel
                                    </Button>
                                    <Button onClick={() => setSelected(null)}>Close</Button>
                                </Stack>
                                {!selected.can_retry && selected.retry_blocked_reason && (
                                    <Typography variant="caption" color="text.secondary">
                                        {selected.retry_blocked_reason}
                                    </Typography>
                                )}
                            </Stack>
                        </SectionCard>
                    )}
                </Stack>
            </QueryBoundary>
        </PageShell>
    );
}
