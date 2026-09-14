import { useEffect, useState } from "react";
import {
    Box,
    Button,
    Chip,
    Collapse,
    Divider,
    IconButton,
    Paper,
    Stack,
    Typography,
} from "@mui/material";
import {
    BugReport as BugReportIcon,
    Close as CloseIcon,
    OpenInNew as OpenInNewIcon,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";

import {
    DEVELOPER_DIAGNOSTICS_EVENT,
    getDeveloperDiagnosticsStatus,
    type DeveloperRequestSummary,
} from "../../api/developerDiagnostics";
import {
    buildGrafanaUrl,
    buildTempoExploreUrl,
    openExternalUrl,
} from "../observability/urlBuilders";

function MetricLine({ label, value }: { label: string; value: string | number | null | undefined }) {
    return (
        <Typography variant="caption" component="div" sx={{ fontFamily: "ui-monospace, monospace" }}>
            <Box component="span" sx={{ color: "text.secondary" }}>
                {label}:{" "}
            </Box>
            {value ?? "—"}
        </Typography>
    );
}

export function DeveloperDiagnosticsPanel() {
    const [open, setOpen] = useState(false);
    const [latest, setLatest] = useState<DeveloperRequestSummary | null>(null);

    const statusQuery = useQuery({
        queryKey: ["developer-diagnostics", "status"],
        queryFn: getDeveloperDiagnosticsStatus,
        staleTime: 60_000,
        retry: false,
    });

    useEffect(() => {
        const handler = (event: Event) => {
            const detail = (event as CustomEvent<DeveloperRequestSummary>).detail;
            if (detail) setLatest(detail);
        };
        window.addEventListener(DEVELOPER_DIAGNOSTICS_EVENT, handler);
        return () => window.removeEventListener(DEVELOPER_DIAGNOSTICS_EVENT, handler);
    }, []);

    if (!statusQuery.data?.enabled) {
        return null;
    }

    const tempoUrl = buildTempoExploreUrl(statusQuery.data.tempo_explore_url, {
        traceId: latest?.trace_id ?? undefined,
        requestId: latest?.correlation_id ?? undefined,
    });
    const grafanaUrl = buildGrafanaUrl(statusQuery.data.grafana_base_url, {
        route: latest?.path,
    });

    return (
        <Box
            sx={{
                position: "fixed",
                right: 16,
                bottom: 16,
                zIndex: (theme) => theme.zIndex.snackbar,
                maxWidth: 420,
            }}
        >
            {!open ? (
                <Button
                    variant="contained"
                    color="secondary"
                    size="small"
                    startIcon={<BugReportIcon />}
                    onClick={() => setOpen(true)}
                >
                    Dev diagnostics
                </Button>
            ) : (
                <Paper elevation={8} sx={{ p: 1.5, width: 400 }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1}>
                        <Stack direction="row" spacing={1} alignItems="center">
                            <BugReportIcon fontSize="small" />
                            <Typography variant="subtitle2">Developer diagnostics</Typography>
                            <Chip size="small" label={statusQuery.data.environment} />
                        </Stack>
                        <IconButton size="small" onClick={() => setOpen(false)} aria-label="Close">
                            <CloseIcon fontSize="small" />
                        </IconButton>
                    </Stack>
                    <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                        Bodies and secrets are never captured. Relies on OTEL-friendly request hooks.
                    </Typography>
                    <Collapse in={Boolean(latest)}>
                        {latest && (
                            <Stack spacing={0.75}>
                                <Typography variant="subtitle2">Request</Typography>
                                <MetricLine
                                    label="route"
                                    value={`${latest.method} ${latest.path}`}
                                />
                                <MetricLine label="status" value={latest.status_code} />
                                <MetricLine label="duration_ms" value={latest.duration_ms} />
                                <MetricLine label="correlation" value={latest.correlation_id} />
                                <MetricLine label="trace" value={latest.trace_id} />
                                <Divider />
                                <Typography variant="subtitle2">DB</Typography>
                                <MetricLine label="sql_count" value={latest.sql_query_count} />
                                <MetricLine label="db_ms" value={latest.db_duration_ms} />
                                <Divider />
                                <Typography variant="subtitle2">Cache</Typography>
                                <MetricLine label="hits" value={latest.cache_hits} />
                                <MetricLine label="misses" value={latest.cache_misses} />
                                <Divider />
                                <Typography variant="subtitle2">External APIs</Typography>
                                <MetricLine
                                    label="calls"
                                    value={
                                        latest.external_calls.length
                                            ? latest.external_calls
                                                  .map(
                                                      (call) =>
                                                          `${call.provider}/${call.operation}` +
                                                          (call.latency_ms != null
                                                              ? `@${call.latency_ms}ms`
                                                              : "")
                                                  )
                                                  .join(", ")
                                            : "none"
                                    }
                                />
                                <Divider />
                                <Typography variant="subtitle2">RAG</Typography>
                                <MetricLine
                                    label="stages"
                                    value={latest.rag_stages.join(", ") || "none"}
                                />
                                <MetricLine
                                    label="chunks"
                                    value={latest.rag_retrieved_chunk_count}
                                />
                                <Divider />
                                <Typography variant="subtitle2">Tasks</Typography>
                                <MetricLine
                                    label="celery"
                                    value={latest.celery_tasks.join(", ") || "none"}
                                />
                            </Stack>
                        )}
                    </Collapse>
                    {!latest && (
                        <Typography variant="body2" color="text.secondary">
                            Make an API request to populate the latest summary.
                        </Typography>
                    )}
                    <Stack direction="row" spacing={1} mt={1.5}>
                        <Button
                            size="small"
                            startIcon={<OpenInNewIcon />}
                            disabled={!tempoUrl}
                            onClick={() => tempoUrl && openExternalUrl(tempoUrl)}
                        >
                            Tempo
                        </Button>
                        <Button
                            size="small"
                            startIcon={<OpenInNewIcon />}
                            disabled={!grafanaUrl}
                            onClick={() => grafanaUrl && openExternalUrl(grafanaUrl)}
                        >
                            Grafana
                        </Button>
                    </Stack>
                </Paper>
            )}
        </Box>
    );
}
