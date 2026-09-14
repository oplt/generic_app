import { useQuery } from "@tanstack/react-query";
import {
    Box,
    Button,
    Chip,
    Skeleton,
    Stack,
    Typography,
} from "@mui/material";
import { getDiagnostics, type OperationalState } from "../../../api/diagnostics";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { InfoTooltip } from "../../../components/ui/InfoTooltip";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { queryKeys } from "../../../config/queryKeys";
import { AiProvidersTable } from "../components/AiProvidersTable";
import { DiagnosticsSectionBlock } from "../components/DiagnosticsSectionBlock";
import { diagnosticsStateColor } from "../components/diagnosticsStateColor";
import { ObservabilityHintsCard } from "../components/ObservabilityHintsCard";

export default function AdminDiagnosticsView() {
    const query = useQuery({
        queryKey: queryKeys.admin.diagnostics,
        queryFn: getDiagnostics,
        refetchInterval: 30_000,
    });

    return (
        <PageShell
            title={
                <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                    Diagnostics
                    <InfoTooltip
                        label="About diagnostics"
                        title="Production-safe status for app, PostgreSQL, Redis, Celery, storage, AI configuration, and RAG. Credentials are never included. Paid AI APIs are not called."
                    />
                </Box>
            }
            maxWidth="xl"
        >
            <SettingsTabs />
            <QueryBoundary
                isLoading={query.isLoading}
                isError={query.isError}
                error={query.error}
                errorFallback="Failed to load diagnostics."
                onRetry={() => void query.refetch()}
                loadingFallback={<Skeleton variant="rounded" height={360} />}
            >
                {query.data && (
                    <Stack spacing={2.5}>
                        <Stack
                            direction="row"
                            spacing={1.5}
                            alignItems="center"
                            useFlexGap
                            flexWrap="wrap"
                        >
                            <Chip
                                label={`overall: ${query.data.overall_state}`}
                                color={diagnosticsStateColor(
                                    query.data.overall_state as OperationalState
                                )}
                            />
                            <Typography variant="body2" color="text.secondary">
                                Generated {new Date(query.data.generated_at).toLocaleString()}
                            </Typography>
                            <Button size="small" onClick={() => void query.refetch()}>
                                Refresh
                            </Button>
                        </Stack>

                        <DiagnosticsSectionBlock
                            title="Application"
                            section={query.data.application}
                        />
                        <DiagnosticsSectionBlock
                            title="PostgreSQL"
                            section={query.data.postgresql}
                        />
                        <DiagnosticsSectionBlock title="Redis" section={query.data.redis} />
                        <DiagnosticsSectionBlock title="Celery" section={query.data.celery} />
                        <DiagnosticsSectionBlock
                            title="Object storage"
                            section={query.data.storage}
                        />
                        <DiagnosticsSectionBlock title="RAG" section={query.data.rag} />

                        <AiProvidersTable providers={query.data.ai_providers ?? []} />
                        <ObservabilityHintsCard hints={query.data.observability_hints} />
                    </Stack>
                )}
            </QueryBoundary>
        </PageShell>
    );
}
