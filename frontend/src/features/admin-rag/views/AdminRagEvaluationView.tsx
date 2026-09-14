import { useState, type SyntheticEvent } from "react";
import { Box, Skeleton, Tab, Tabs } from "@mui/material";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { InfoTooltip } from "../../../components/ui/InfoTooltip";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { DatasetsCasesPanel } from "../components/evaluation/DatasetsCasesPanel";
import { ProbePanel } from "../components/evaluation/ProbePanel";
import { RunsPanel } from "../components/evaluation/RunsPanel";
import { useRagEvaluation } from "../hooks/useRagEvaluation";

const tabs = [
    ["probe", "Probe"],
    ["datasets", "Datasets & Cases"],
    ["runs", "Runs / Comparison"],
] as const;

type TabId = (typeof tabs)[number][0];

export default function AdminRagEvaluationView() {
    const m = useRagEvaluation();
    const [tab, setTab] = useState<TabId>("probe");

    function handleTabChange(_event: SyntheticEvent, value: TabId) {
        setTab(value);
    }

    return (
        <PageShell
            title={
                <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                    RAG evaluation
                    <InfoTooltip
                        label="About RAG evaluation"
                        title="Admin workbench for comparing retrieval strategies. Datasets and runs are tenant-scoped. Generation LLM judges stay off by default."
                    />
                </Box>
            }
            maxWidth="xl"
        >
            <SettingsTabs />
            <QueryBoundary
                isLoading={m.datasetsQuery.isLoading}
                isError={m.datasetsQuery.isError}
                error={m.datasetsQuery.error}
                errorFallback="Failed to load evaluation datasets."
                onRetry={() => void m.datasetsQuery.refetch()}
                loadingFallback={<Skeleton variant="rounded" height={320} />}
            >
                <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
                    <Tabs
                        value={tab}
                        onChange={handleTabChange}
                        variant="scrollable"
                        scrollButtons="auto"
                        allowScrollButtonsMobile
                        aria-label="RAG evaluation workflows"
                    >
                        {tabs.map(([id, label]) => (
                            <Tab key={id} id={`rag-eval-${id}-tab`} value={id} label={label} />
                        ))}
                    </Tabs>
                </Box>
                <Box role="tabpanel" aria-labelledby={`rag-eval-${tab}-tab`}>
                    {tab === "probe" && <ProbePanel m={m} />}
                    {tab === "datasets" && <DatasetsCasesPanel m={m} />}
                    {tab === "runs" && <RunsPanel m={m} />}
                </Box>
            </QueryBoundary>
        </PageShell>
    );
}
