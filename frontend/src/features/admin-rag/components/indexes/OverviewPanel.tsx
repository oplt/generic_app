import {
    Alert,
    Box,
    Button,
    Stack,
} from "@mui/material";
import {
    FactCheck as FactCheckIcon,
    Storage as StorageIcon,
    Sync as SyncIcon,
    WorkOutline as JobsIcon,
} from "@mui/icons-material";
import type { RagIndexStatus } from "../../../../api/ragIndexes";
import { SectionCard } from "../../../../components/ui/SectionCard";
import { StatCard } from "../../../../components/ui/StatCard";
import { getQueryErrorMessage } from "../../../../utils/queryErrors";
import type { RagIndexesModel } from "../../hooks/useRagIndexes";
import { CoverageCaption, PipelineMetadataGrid } from "./PipelineMetadata";

type OverviewPanelProps = {
    data: RagIndexStatus;
    m: RagIndexesModel;
};

export function OverviewPanel({ data, m }: OverviewPanelProps) {
    const readiness = data.building_readiness;

    return (
        <Stack spacing={2.5}>
            {data.dimension_migration_required && (
                <Alert severity="warning">
                    Active embedding dimensions differ from the pgvector column (
                    {data.schema_embedding_dimensions}). Run an Alembic vector-schema migration
                    before activating a mismatched index version.
                </Alert>
            )}
            {data.desired_index_version &&
                data.desired_index_version !== data.active_version.key && (
                    <Alert severity="info">
                        Runtime config desires {data.desired_index_version}. Active remains{" "}
                        {data.active_version.key}
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
                action={
                    <Stack direction="row" spacing={1}>
                        <Button
                            variant="outlined"
                            onClick={() => m.createMutation.mutate()}
                            disabled={m.createMutation.isPending}
                        >
                            Snapshot version
                        </Button>
                        <Button
                            variant="contained"
                            onClick={() => m.reindexMutation.mutate()}
                            disabled={
                                m.reindexMutation.isPending ||
                                (data.documents_incomplete ?? data.documents_stale) === 0
                            }
                        >
                            Build missing
                        </Button>
                    </Stack>
                }
            >
                <Stack spacing={1.25}>
                    <PipelineMetadataGrid version={data.active_version} />
                    <CoverageCaption
                        indexed={data.documents_indexed}
                        total={data.documents_total}
                        failedJobs={data.jobs_failed}
                        coverage={readiness ? Number(readiness.coverage) : undefined}
                        incomplete={
                            readiness?.documents_incomplete != null
                                ? String(readiness.documents_incomplete)
                                : undefined
                        }
                        chunks={
                            readiness?.chunk_count != null
                                ? String(readiness.chunk_count)
                                : undefined
                        }
                    />
                    {m.reindexMutation.isSuccess && (
                        <Alert severity="success">
                            Enqueued {m.reindexMutation.data.enqueued} job(s) targeting{" "}
                            {m.reindexMutation.data.target_index_version ??
                                m.reindexMutation.data.active_index_version}
                            .
                        </Alert>
                    )}
                    {m.reindexMutation.isError && (
                        <Alert severity="error">
                            {getQueryErrorMessage(
                                m.reindexMutation.error,
                                "Failed to enqueue reindex jobs."
                            )}
                        </Alert>
                    )}
                </Stack>
            </SectionCard>
        </Stack>
    );
}
