import { Box, Skeleton, Stack, Typography } from "@mui/material";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { InfoTooltip } from "../../../components/ui/InfoTooltip";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { JobDetailDrawer } from "../components/JobDetailDrawer";
import { JobsFilters } from "../components/JobsFilters";
import { JobsTable } from "../components/JobsTable";
import { useAdminJobs } from "../hooks/useAdminJobs";

export default function AdminJobsView() {
    const m = useAdminJobs();

    return (
        <PageShell
            title={
                <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                    Jobs
                    <InfoTooltip
                        label="About jobs console"
                        title="Aggregates application_jobs and RAG ingestion jobs. Payloads are redacted. Retry is limited to RAG ingestion; cancel only applies to queued/pending jobs."
                    />
                </Box>
            }
            maxWidth="xl"
        >
            <SettingsTabs />
            <QueryBoundary
                isLoading={m.listQuery.isLoading}
                isError={m.listQuery.isError}
                error={m.listQuery.error}
                errorFallback="Failed to load jobs."
                onRetry={() => void m.listQuery.refetch()}
                loadingFallback={<Skeleton variant="rounded" height={320} />}
            >
                <Stack spacing={2.5}>
                    <JobsFilters m={m} />
                    <JobsTable m={m} />
                </Stack>
            </QueryBoundary>

            <JobDetailDrawer m={m} />

            <ConfirmDialog
                open={Boolean(m.cancelTarget)}
                title="Cancel this job?"
                description={
                    <Typography variant="body2">
                        Cancel queued job <strong>{m.cancelTarget?.job_type}</strong>
                        {m.cancelTarget ? ` (${m.cancelTarget.id.slice(0, 8)}…)` : ""}. Running work
                        may not stop immediately.
                    </Typography>
                }
                confirmLabel="Cancel job"
                confirmColor="warning"
                pending={m.cancelMutation.isPending}
                onConfirm={() => {
                    if (m.cancelTarget) m.cancelMutation.mutate(m.cancelTarget);
                }}
                onClose={() => m.setCancelTarget(null)}
            />
        </PageShell>
    );
}
