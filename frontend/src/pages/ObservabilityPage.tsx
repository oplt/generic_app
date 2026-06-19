import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    MenuItem,
    Skeleton,
    Stack,
    TextField,
} from "@mui/material";
import {
    Api as ApiIcon,
    Assessment as OverviewIcon,
    BugReport as ErrorIcon,
    Cached as CacheIcon,
    Dns as DatabaseIcon,
    Hub as ObservabilityIcon,
    OpenInNew as OpenInNewIcon,
    QueryStats as MetricsIcon,
    Route as RouteIcon,
    Schedule as ScheduleIcon,
    Speed as LatencyIcon,
    Storage as PrometheusIcon,
    Timeline as TracesIcon,
    Web as FrontendIcon,
    WorkHistory as WorkerIcon,
} from "@mui/icons-material";
import { getObservabilityLinks, getObservabilityStatus } from "../features/observability/api";
import { HealthStatusCard } from "../features/observability/components/HealthStatusCard";
import { ObservabilityShortcutCard } from "../features/observability/components/ObservabilityShortcutCard";
import type {
    GrafanaUrlContext,
    ObservabilityLinks,
    ObservabilityStatus,
    ObservabilityStatusItem,
} from "../features/observability/types";
import { buildGrafanaUrl, buildTempoExploreUrl, openExternalUrl } from "../features/observability/urlBuilders";
import { useAuth } from "../hooks/useAuth";
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
import { SettingsTabs } from "../components/layout/SettingsTabs";
import { SectionCard } from "../components/ui/SectionCard";

type HealthKey =
    | "api"
    | "frontend"
    | "database"
    | "cache"
    | "workers"
    | "backgroundJobs"
    | "errorRate"
    | "requestLatency"
    | "prometheus"
    | "grafana"
    | "tempo";

type HealthCardDefinition = {
    key: HealthKey;
    title: string;
    icon: ReactNode;
};

const SERVICES = ["backend", "frontend", "worker"];
const ENVIRONMENTS = ["local", "development", "staging", "production"];
const TIME_RANGES = [
    { label: "Last 15 minutes", from: "now-15m", to: "now" },
    { label: "Last hour", from: "now-1h", to: "now" },
    { label: "Last 6 hours", from: "now-6h", to: "now" },
    { label: "Last 24 hours", from: "now-24h", to: "now" },
];

function buildHealthItems(status?: ObservabilityStatus): Record<HealthKey, ObservabilityStatusItem | undefined> {
    return {
        api: status?.api,
        frontend: status?.frontend,
        database: status?.database,
        cache: status?.cache,
        workers: status?.workers,
        backgroundJobs: status?.background_jobs,
        errorRate: status?.error_rate,
        requestLatency: status?.request_latency,
        prometheus: status?.prometheus,
        grafana: status?.grafana,
        tempo: status?.tempo,
    };
}

function metricFor(item?: ObservabilityStatusItem) {
    return item?.value ??
        (item?.queue_depth !== undefined && item.queue_depth !== null ? `${item.queue_depth} queued` : null);
}

function fallbackItem(detail: string): ObservabilityStatusItem {
    return { status: "unknown", detail };
}

function buildContext(values: {
    service: string;
    environment: string;
    route: string;
    jobName: string;
    traceId: string;
    requestId: string;
    timeRangeIndex: number;
}): GrafanaUrlContext {
    const timeRange = TIME_RANGES[values.timeRangeIndex] ?? TIME_RANGES[1];
    return {
        service: values.service,
        environment: values.environment,
        route: values.route,
        jobName: values.jobName,
        traceId: values.traceId,
        requestId: values.requestId,
        from: timeRange.from,
        to: timeRange.to,
        orgId: "1",
    };
}

function dashboardUrl(link: ObservabilityLinks | undefined, dashboard: keyof ObservabilityLinks["dashboards"], context: GrafanaUrlContext) {
    return buildGrafanaUrl(link?.dashboards[dashboard].url, context);
}

export default function ObservabilityPage() {
    const { isAdmin } = useAuth();
    const [service, setService] = useState("backend");
    const [environment, setEnvironment] = useState("local");
    const [route, setRoute] = useState("");
    const [jobName, setJobName] = useState("");
    const [traceId, setTraceId] = useState("");
    const [requestId, setRequestId] = useState("");
    const [timeRangeIndex, setTimeRangeIndex] = useState(1);

    const linksQuery = useQuery({
        queryKey: ["observability", "links"],
        queryFn: getObservabilityLinks,
        staleTime: 5 * 60_000,
    });
    const statusQuery = useQuery({
        queryKey: ["observability", "status"],
        queryFn: getObservabilityStatus,
        refetchInterval: 60_000,
    });

    const context = useMemo(
        () => buildContext({ service, environment, route, jobName, traceId, requestId, timeRangeIndex }),
        [environment, jobName, requestId, route, service, timeRangeIndex, traceId]
    );
    const healthItems = buildHealthItems(statusQuery.data);
    const technicalAccess = isAdmin && (linksQuery.data?.grafana_base_url.allowed ?? false);

    const healthCards: HealthCardDefinition[] = [
        { key: "api", title: "API Status", icon: <ApiIcon fontSize="small" /> },
        { key: "frontend", title: "Frontend Status", icon: <FrontendIcon fontSize="small" /> },
        { key: "database", title: "Database", icon: <DatabaseIcon fontSize="small" /> },
        { key: "cache", title: "Cache / Redis", icon: <CacheIcon fontSize="small" /> },
        { key: "workers", title: "Worker Queue", icon: <WorkerIcon fontSize="small" /> },
        { key: "backgroundJobs", title: "Background Jobs", icon: <ScheduleIcon fontSize="small" /> },
        { key: "errorRate", title: "Error Rate", icon: <ErrorIcon fontSize="small" /> },
        { key: "requestLatency", title: "Request Latency", icon: <LatencyIcon fontSize="small" /> },
        { key: "prometheus", title: "Prometheus", icon: <PrometheusIcon fontSize="small" /> },
        { key: "grafana", title: "Grafana", icon: <MetricsIcon fontSize="small" /> },
        { key: "tempo", title: "Tempo", icon: <TracesIcon fontSize="small" /> },
    ];

    const links = linksQuery.data;
    const shortcuts = [
        {
            title: "Application Overview",
            description: "High-level service health, request volume, latency, errors, and saturation.",
            buttonText: "Open dashboard",
            link: links?.dashboards.application_overview,
            url: dashboardUrl(links, "application_overview", context),
            icon: <OverviewIcon color="primary" />,
        },
        {
            title: "Backend API",
            description: "HTTP latency, request rate, error rate, status codes, and slow endpoints.",
            buttonText: "Open API view",
            link: links?.dashboards.api,
            url: dashboardUrl(links, "api", context),
            icon: <ApiIcon color="primary" />,
        },
        {
            title: "Frontend Performance",
            description: "Frontend availability, client-side errors, page load timing, and user experience signals.",
            buttonText: "Open frontend view",
            link: links?.dashboards.frontend,
            url: dashboardUrl(links, "frontend", context),
            icon: <FrontendIcon color="primary" />,
        },
        {
            title: "Database",
            description: "Connection pool usage, query latency, slow queries, locks, and availability.",
            buttonText: "Open database view",
            link: links?.dashboards.database,
            url: dashboardUrl(links, "database", context),
            icon: <DatabaseIcon color="primary" />,
        },
        {
            title: "Cache / Redis",
            description: "Cache hit rate, memory usage, command latency, evictions, and availability.",
            buttonText: "Open cache view",
            link: links?.dashboards.cache,
            url: dashboardUrl(links, "cache", context),
            icon: <CacheIcon color="primary" />,
        },
        {
            title: "Workers / Background Jobs",
            description: "Queue depth, task duration, retries, failures, and worker availability.",
            buttonText: "Open workers",
            link: links?.dashboards.workers,
            url: dashboardUrl(links, "workers", context),
            icon: <WorkerIcon color="primary" />,
        },
        {
            title: "Scheduled Tasks",
            description: "Cron jobs, periodic jobs, execution duration, failed runs, and missed schedules.",
            buttonText: "Open schedules",
            link: links?.dashboards.scheduled_tasks,
            url: dashboardUrl(links, "scheduled_tasks", context),
            icon: <ScheduleIcon color="primary" />,
        },
        {
            title: "Error Investigation",
            description: "Recent errors, failing routes, affected services, and related traces.",
            buttonText: "Open errors",
            link: links?.dashboards.errors,
            url: dashboardUrl(links, "errors", context),
            icon: <ErrorIcon color="primary" />,
        },
        {
            title: "Tempo Traces",
            description: "Investigate slow requests, failed workflows, and cross-service latency through Grafana Explore.",
            buttonText: "Explore traces",
            link: links?.tempo_explore_url,
            url: buildTempoExploreUrl(links?.tempo_explore_url.url, context),
            icon: <TracesIcon color="primary" />,
        },
        {
            title: "Prometheus Debug",
            description: "Raw PromQL query UI for developer and admin investigation.",
            buttonText: "Open Prometheus",
            link: links?.prometheus_url,
            url: buildGrafanaUrl(links?.prometheus_url.url, context),
            icon: <PrometheusIcon color="primary" />,
            adminOnly: true,
        },
    ].filter((item) => !item.adminOnly || isAdmin);

    return (
        <PageShell maxWidth="xl">
            <SettingsTabs />

            <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
                <Button
                    variant="contained"
                    startIcon={<OpenInNewIcon />}
                    disabled={!technicalAccess || !links?.dashboards.application_overview.url}
                    onClick={() => {
                        const url = dashboardUrl(links, "application_overview", context);
                        if (url) {
                            openExternalUrl(url);
                        }
                    }}
                >
                    Open Grafana
                </Button>
            </Stack>

            {linksQuery.isError && (
                <Alert severity="warning">
                    Observability links are unavailable. Health checks can still render when the status endpoint responds.
                </Alert>
            )}

            <SectionCard
                title="Investigation context"
                description="These fields are passed as safe Grafana query parameters when a dashboard supports them."
            >
                <Box
                    sx={{
                        display: "grid",
                        gap: 2,
                        gridTemplateColumns: {
                            xs: "1fr",
                            md: "repeat(2, minmax(0, 1fr))",
                            xl: "repeat(3, minmax(0, 1fr))",
                        },
                    }}
                >
                    <TextField select label="Service" value={service} onChange={(event) => setService(event.target.value)}>
                        {SERVICES.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
                    </TextField>
                    <TextField
                        select
                        label="Environment"
                        value={environment}
                        onChange={(event) => setEnvironment(event.target.value)}
                    >
                        {ENVIRONMENTS.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
                    </TextField>
                    <TextField
                        select
                        label="Time range"
                        value={timeRangeIndex}
                        onChange={(event) => setTimeRangeIndex(Number(event.target.value))}
                    >
                        {TIME_RANGES.map((item, index) => <MenuItem key={item.from} value={index}>{item.label}</MenuItem>)}
                    </TextField>
                    <TextField
                        label="Route"
                        value={route}
                        onChange={(event) => setRoute(event.target.value)}
                        placeholder="/api/v1/users"
                    />
                    <TextField
                        label="Job"
                        value={jobName}
                        onChange={(event) => setJobName(event.target.value)}
                        placeholder="email"
                    />
                    <TextField
                        label="Request or trace"
                        value={requestId}
                        onChange={(event) => setRequestId(event.target.value)}
                        placeholder="request id"
                    />
                    <TextField
                        label="Trace ID"
                        value={traceId}
                        onChange={(event) => setTraceId(event.target.value)}
                        placeholder="trace id"
                    />
                </Box>
            </SectionCard>

            <SectionCard title="System health" description="Lightweight checks from the app plus local observability tool reachability.">
                {statusQuery.isLoading ? (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", xl: "repeat(4, 1fr)" },
                        }}
                    >
                        {Array.from({ length: 8 }).map((_, index) => (
                            <Skeleton key={index} variant="rounded" height={180} sx={{ borderRadius: 4 }} />
                        ))}
                    </Box>
                ) : statusQuery.isError ? (
                    <EmptyState
                        icon={<ObservabilityIcon />}
                        title="Health checks are unavailable"
                        description="The page could not load observability status right now. Tool links remain available when configured."
                    />
                ) : (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", xl: "repeat(4, 1fr)" },
                        }}
                    >
                        {healthCards.map((card) => {
                            const item = healthItems[card.key] ?? fallbackItem("Status check is not configured");
                            return (
                                <HealthStatusCard
                                    key={card.key}
                                    title={card.title}
                                    status={item.status}
                                    detail={item.detail}
                                    metric={metricFor(item)}
                                    lastCheckedAt={item.last_checked_at}
                                    icon={card.icon}
                                />
                            );
                        })}
                    </Box>
                )}
            </SectionCard>

            <SectionCard
                title="Shortcuts"
                description="Open Grafana as the main investigation surface. Prometheus is kept as an admin debug tool."
            >
                {linksQuery.isLoading ? (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)", xl: "repeat(3, 1fr)" },
                        }}
                    >
                        {Array.from({ length: 6 }).map((_, index) => (
                            <Skeleton key={index} variant="rounded" height={218} sx={{ borderRadius: 4 }} />
                        ))}
                    </Box>
                ) : shortcuts.length === 0 ? (
                    <EmptyState
                        icon={<RouteIcon />}
                        title="No observability shortcuts"
                        description="Configure Grafana, Tempo, or Prometheus public URLs to enable launch links."
                    />
                ) : (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)", xl: "repeat(3, 1fr)" },
                        }}
                    >
                        {shortcuts.map((item) => (
                            <ObservabilityShortcutCard
                                key={item.title}
                                title={item.title}
                                description={item.description}
                                buttonText={item.buttonText}
                                url={item.url}
                                allowed={item.link?.allowed ?? false}
                                configured={item.link?.configured ?? false}
                                icon={item.icon}
                                onOpen={openExternalUrl}
                            />
                        ))}
                    </Box>
                )}
            </SectionCard>
        </PageShell>
    );
}
