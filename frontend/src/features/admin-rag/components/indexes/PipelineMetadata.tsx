import { Box, Chip, Stack, Typography } from "@mui/material";
import type { RagIndexVersion } from "../../../../api/ragIndexes";
import { InfoTooltip } from "../../../../components/ui/InfoTooltip";

const META_KEYS = [
    ["provider", "embedding_provider"],
    ["model", "embedding_model"],
    ["dims", "embedding_dimensions"],
    ["parser", "parser_version"],
    ["chunker", "chunker_version"],
    ["schema", "embedding_schema_version"],
] as const;

type PipelineMetadataGridProps = {
    version: RagIndexVersion;
};

/** Compact metadata chips; full strings available via tooltip. */
export function PipelineMetadataGrid({ version }: PipelineMetadataGridProps) {
    return (
        <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center">
            {META_KEYS.map(([label, key]) => {
                const value = String(version[key as keyof RagIndexVersion] ?? "—");
                return (
                    <Chip
                        key={key}
                        size="small"
                        variant="outlined"
                        label={`${label}: ${value}`}
                        title={`${label}: ${value}`}
                    />
                );
            })}
            <InfoTooltip
                label="About pipeline metadata"
                title="Parser, chunker, and embedding schema identify the active retrieval pipeline. Mismatched dimensions require a vector-schema migration before activation."
            />
        </Stack>
    );
}

type CoverageCaptionProps = {
    indexed: number;
    total: number;
    failedJobs: number;
    coverage?: number;
    incomplete?: number | string;
    chunks?: number | string;
};

export function CoverageCaption({
    indexed,
    total,
    failedJobs,
    coverage,
    incomplete,
    chunks,
}: CoverageCaptionProps) {
    return (
        <Box>
            <Typography variant="caption" color="text.secondary" display="block">
                Indexed {indexed} / {total} documents · {failedJobs} failed jobs
            </Typography>
            {coverage != null && (
                <Typography variant="caption" color="text.secondary" display="block">
                    Candidate coverage {(Number(coverage) * 100).toFixed(1)}% · incomplete{" "}
                    {String(incomplete)} · chunks {String(chunks)}
                </Typography>
            )}
        </Box>
    );
}
