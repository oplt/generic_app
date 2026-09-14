import { useQuery } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Skeleton,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";

import { getDiagnostics, type DiagnosticsSection, type OperationalState } from "../../../api/diagnostics";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { SectionCard } from "../../../components/ui/SectionCard";

const queryKey = ["admin", "diagnostics"] as const;

function stateColor(state: OperationalState): "default" | "success" | "warning" | "error" | "info" {
    if (state === "healthy") return "success";
    if (state === "degraded") return "warning";
    if (state === "unavailable") return "error";
    if (state === "not_required") return "default";
    return "info";
}

function SectionBlock({ title, section }: { title: string; section: DiagnosticsSection }) {
    return (
        <SectionCard title={title}>
            <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center">
                    <Chip size="small" label={section.state} color={stateColor(section.state)} />
                    <Typography variant="body2" color="text.secondary">
                        {section.detail || "—"}
                    </Typography>
                </Stack>
                <Box
                    component="pre"
                    sx={{
                        m: 0,
                        p: 1.5,
                        bgcolor: "action.hover",
                        borderRadius: 1,
                        whiteSpace: "pre-wrap",
                        fontSize: 12,
                        maxHeight: 280,
                        overflow: "auto",
                    }}
                >
                    {JSON.stringify(section.metrics, null, 2)}
                </Box>
            </Stack>
        </SectionCard>
    );
}

export default function AdminDiagnosticsView() {
    const query = useQuery({
        queryKey,
        queryFn: getDiagnostics,
        refetchInterval: 30_000,
    });

    return (
        <PageShell title="Diagnostics" maxWidth="xl">
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
                        <Alert severity="info">
                            Production-safe status for app, PostgreSQL, Redis, Celery, storage, AI
                            configuration, and RAG. Credentials and secret values are never included.
                            Paid AI APIs are not called from this page.
                        </Alert>

                        <Stack direction="row" spacing={1.5} alignItems="center" useFlexGap flexWrap="wrap">
                            <Chip
                                label={`overall: ${query.data.overall_state}`}
                                color={stateColor(query.data.overall_state)}
                            />
                            <Typography variant="body2" color="text.secondary">
                                Generated {new Date(query.data.generated_at).toLocaleString()}
                            </Typography>
                            <Button size="small" onClick={() => void query.refetch()}>
                                Refresh
                            </Button>
                        </Stack>

                        <SectionBlock title="Application" section={query.data.application} />
                        <SectionBlock title="PostgreSQL" section={query.data.postgresql} />
                        <SectionBlock title="Redis" section={query.data.redis} />
                        <SectionBlock title="Celery" section={query.data.celery} />
                        <SectionBlock title="Object storage" section={query.data.storage} />
                        <SectionBlock title="RAG" section={query.data.rag} />

                        <SectionCard title="AI providers">
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>Provider</TableCell>
                                        <TableCell>State</TableCell>
                                        <TableCell>Configured</TableCell>
                                        <TableCell>Detail</TableCell>
                                        <TableCell>Latency (ms)</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {query.data.ai_providers.map((provider) => (
                                        <TableRow key={provider.key}>
                                            <TableCell>{provider.label}</TableCell>
                                            <TableCell>
                                                <Chip
                                                    size="small"
                                                    label={provider.state}
                                                    color={stateColor(provider.state)}
                                                />
                                            </TableCell>
                                            <TableCell>{provider.configured ? "yes" : "no"}</TableCell>
                                            <TableCell>{provider.detail}</TableCell>
                                            <TableCell>
                                                {provider.latency_summary_ms != null
                                                    ? provider.latency_summary_ms.toFixed(1)
                                                    : "—"}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </SectionCard>

                        <SectionCard title="Observability hints">
                            <Stack spacing={1}>
                                <Box
                                    component="pre"
                                    sx={{
                                        m: 0,
                                        p: 1.5,
                                        bgcolor: "action.hover",
                                        borderRadius: 1,
                                        whiteSpace: "pre-wrap",
                                        fontSize: 12,
                                    }}
                                >
                                    {JSON.stringify(query.data.observability_hints, null, 2)}
                                </Box>
                                <Stack direction="row" spacing={1}>
                                    <Button
                                        size="small"
                                        href={
                                            typeof query.data.observability_hints
                                                .grafana_base_url === "string"
                                                ? String(
                                                      query.data.observability_hints
                                                          .grafana_base_url
                                                  )
                                                : "/observability"
                                        }
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        Grafana
                                    </Button>
                                    <Button
                                        size="small"
                                        href={
                                            typeof query.data.observability_hints
                                                .tempo_explore_url === "string"
                                                ? String(
                                                      query.data.observability_hints
                                                          .tempo_explore_url
                                                  )
                                                : "/observability"
                                        }
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        Tempo
                                    </Button>
                                    <Button size="small" href="/observability">
                                        Observability page
                                    </Button>
                                </Stack>
                            </Stack>
                        </SectionCard>
                    </Stack>
                )}
            </QueryBoundary>
        </PageShell>
    );
}
