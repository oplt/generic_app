import { useEffect, useState, type SyntheticEvent } from "react";
import { Box, Skeleton, Stack, Tab, Tabs } from "@mui/material";
import { Approval as ReviewIcon, Dataset as DatasetIcon, Description as DocumentIcon, PsychologyAlt as PromptIcon } from "@mui/icons-material";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryErrorAlert } from "../../../components/ui/QueryBoundary";
import { StatCard } from "../../../components/ui/StatCard";
import { StatCardSkeletonGrid } from "../../../components/ui/StatCardSkeletonGrid";
import { PromptLibraryPanel } from "../components/PromptLibraryPanel";
import { AiProviderPanel } from "../components/AiProviderPanel";
import { RetrievalDocumentsPanel } from "../components/RetrievalDocumentsPanel";
import { ReviewsEvaluationsPanel } from "../components/ReviewsEvaluationsPanel";
import { RunPlaygroundPanel } from "../components/RunPlaygroundPanel";
import { VersionBuilderPanel } from "../components/VersionBuilderPanel";
import { useAiStudioView } from "../hooks/useAiStudioView";

const sections = [
    ["ai-providers", "AI Provider"],
    ["ai-prompts", "Prompts"],
    ["ai-runs", "Run"],
    ["ai-versions", "Versions"],
    ["ai-documents", "Documents"],
    ["ai-evaluations", "Evaluations"],
] as const;

type SectionId = (typeof sections)[number][0];

function sectionFromHash(): SectionId {
    const hash = typeof window === "undefined" ? "" : window.location.hash.slice(1);
    return sections.some(([id]) => id === hash) ? (hash as SectionId) : "ai-prompts";
}

export default function AiStudioPage() {
    const m = useAiStudioView();
    const [activeSection, setActiveSection] = useState<SectionId>(sectionFromHash);

    useEffect(() => {
        const handleHashChange = () => setActiveSection(sectionFromHash());
        window.addEventListener("hashchange", handleHashChange);
        return () => window.removeEventListener("hashchange", handleHashChange);
    }, []);

    function handleSectionChange(_event: SyntheticEvent, value: SectionId) {
        setActiveSection(value);
        window.history.replaceState(null, "", `#${value}`);
    }

    if (m.isLoading) return <PageShell maxWidth="xl"><SettingsTabs /><StatCardSkeletonGrid /><Stack spacing={2} sx={{ mt: 2 }}><Skeleton variant="rounded" height={320} /><Skeleton variant="rounded" height={280} /></Stack></PageShell>;
    if (m.isError || !m.overview) return <PageShell maxWidth="xl"><SettingsTabs /><QueryErrorAlert error={m.error ?? new Error("Failed to load AI studio overview.")} fallback="Failed to load AI studio overview." onRetry={() => void m.refetch()} /></PageShell>;

    const activePanel = {
        "ai-providers": <AiProviderPanel providers={m.providers} />,
        "ai-prompts": <PromptLibraryPanel m={m} />,
        "ai-runs": <RunPlaygroundPanel m={m} />,
        "ai-versions": <VersionBuilderPanel m={m} />,
        "ai-documents": <RetrievalDocumentsPanel m={m} />,
        "ai-evaluations": <ReviewsEvaluationsPanel m={m} />,
    }[activeSection];

    return <PageShell maxWidth="xl"><SettingsTabs />
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "repeat(2,1fr)", xl: "repeat(4,1fr)" } }}>
            <StatCard label="Prompt templates" value={m.overview.prompt_templates_count} description={`Showing ${m.promptTemplates.length} of ${m.overview.prompt_templates_count} templates`} icon={<PromptIcon />} />
            <StatCard label="Documents" value={m.overview.documents_count} description={`Showing ${m.documents.length} of ${m.overview.documents_count} indexed sources`} icon={<DocumentIcon />} color="secondary" />
            <StatCard label="Pending reviews" value={m.reviews.filter((item) => item.status === "pending").length} description="Runs waiting for human review" icon={<ReviewIcon />} color="warning" />
            <StatCard label="Datasets" value={m.overview.datasets_count} description={`Showing ${m.datasets.length} of ${m.overview.datasets_count} evaluation datasets`} icon={<DatasetIcon />} color="success" />
        </Box>
        <Box sx={{ mt: 2, borderBottom: 1, borderColor: "divider" }}>
            <Tabs
                value={activeSection}
                onChange={handleSectionChange}
                variant="scrollable"
                scrollButtons="auto"
                allowScrollButtonsMobile
                aria-label="AI Studio sections"
            >
                {sections.map(([id, label]) => (
                    <Tab key={id} id={`${id}-tab`} value={id} label={label} aria-controls={id} />
                ))}
            </Tabs>
        </Box>
        <Box
            id={activeSection}
            role="tabpanel"
            aria-labelledby={`${activeSection}-tab`}
            sx={{ mt: 2, scrollMarginTop: 88 }}
        >
            {activePanel}
        </Box>
    </PageShell>;
}
