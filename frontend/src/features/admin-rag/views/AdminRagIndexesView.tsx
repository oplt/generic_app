import { useState, type SyntheticEvent } from "react";
import { Box, Skeleton, Tab, Tabs, Typography } from "@mui/material";
import { SettingsTabs } from "../../../components/layout/SettingsTabs";
import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { PageShell } from "../../../components/ui/PageShell";
import { QueryBoundary } from "../../../components/ui/QueryBoundary";
import { OverviewPanel } from "../components/indexes/OverviewPanel";
import { VersionsPanel } from "../components/indexes/VersionsPanel";
import { useRagIndexes } from "../hooks/useRagIndexes";

const tabs = [
    ["overview", "Overview"],
    ["versions", "Versions"],
] as const;

type TabId = (typeof tabs)[number][0];

export default function AdminRagIndexesView() {
    const m = useRagIndexes();
    const [tab, setTab] = useState<TabId>("overview");
    const data = m.statusQuery.data;

    const pending = m.pendingAction;
    const confirmCopy =
        pending?.type === "activate"
            ? {
                  title: "Activate index version?",
                  description: (
                      <Typography variant="body2">
                          Serve traffic from <strong>{pending.versionKey}</strong>. Only do this
                          after validation succeeds.
                      </Typography>
                  ),
                  confirmLabel: "Activate",
                  confirmColor: "primary" as const,
              }
            : pending?.type === "rollback"
              ? {
                    title: "Roll back index version?",
                    description: (
                        <Typography variant="body2">
                            Restore <strong>{pending.versionKey}</strong> as the active serving
                            version. Retained chunks are reused.
                        </Typography>
                    ),
                    confirmLabel: "Rollback",
                    confirmColor: "warning" as const,
                }
              : {
                    title: "Validate index version?",
                    description: (
                        <Typography variant="body2">
                            Mark <strong>{pending?.versionKey}</strong> as validated so it can be
                            activated.
                        </Typography>
                    ),
                    confirmLabel: "Validate",
                    confirmColor: "primary" as const,
                };

    return (
        <PageShell title="RAG indexes" maxWidth="xl">
            <SettingsTabs />
            <QueryBoundary
                isLoading={m.statusQuery.isLoading}
                isError={m.statusQuery.isError}
                error={m.statusQuery.error}
                errorFallback="Failed to load RAG index status."
                onRetry={() => void m.statusQuery.refetch()}
                loadingFallback={<Skeleton variant="rounded" height={320} />}
            >
                {data && (
                    <>
                        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
                            <Tabs
                                value={tab}
                                onChange={(_event: SyntheticEvent, value: TabId) => setTab(value)}
                                aria-label="RAG index workflows"
                            >
                                {tabs.map(([id, label]) => (
                                    <Tab key={id} value={id} label={label} />
                                ))}
                            </Tabs>
                        </Box>
                        {tab === "overview" && <OverviewPanel data={data} m={m} />}
                        {tab === "versions" && <VersionsPanel data={data} m={m} />}
                    </>
                )}
            </QueryBoundary>

            <ConfirmDialog
                open={Boolean(pending)}
                title={confirmCopy.title}
                description={confirmCopy.description}
                confirmLabel={confirmCopy.confirmLabel}
                confirmColor={confirmCopy.confirmColor}
                pending={m.actionPending}
                onConfirm={() => m.confirmPendingAction()}
                onClose={() => m.setPendingAction(null)}
            />
        </PageShell>
    );
}
