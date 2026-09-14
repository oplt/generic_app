import { useQuery } from "@tanstack/react-query";
import { Chip, Stack, Typography } from "@mui/material";
import { getDiagnostics, type OperationalState } from "../../../api/diagnostics";
import { SectionCard } from "../../../components/ui/SectionCard";
import { queryKeys } from "../../../config/queryKeys";

const SAFE_METRIC_KEYS = ["configured", "bucket_name", "endpoint_host", "region"] as const;

function stateColor(state: OperationalState): "default" | "success" | "warning" | "error" | "info" {
    if (state === "healthy") return "success";
    if (state === "degraded") return "warning";
    if (state === "unavailable") return "error";
    if (state === "not_required") return "default";
    return "info";
}

/** Compact object-storage health for Admin Platform (no credentials). */
export function StorageHealthCard() {
    const query = useQuery({
        queryKey: queryKeys.admin.diagnostics,
        queryFn: getDiagnostics,
        staleTime: 30_000,
        retry: false,
    });

    const section = query.data?.storage;
    const state = (section?.state ?? "unknown") as OperationalState;
    const metrics = section?.metrics ?? {};

    return (
        <SectionCard
            title="Object storage"
            description="Health only — credentials never shown here. Full detail lives under Diagnostics."
        >
            {query.isLoading ? (
                <Typography variant="body2" color="text.secondary">
                    Checking storage…
                </Typography>
            ) : query.isError || !section ? (
                <Typography variant="body2" color="text.secondary">
                    Storage status unavailable. Open Diagnostics if you need a deeper probe.
                </Typography>
            ) : (
                <Stack spacing={1.25}>
                    <Stack direction="row" spacing={1} alignItems="center">
                        <Chip size="small" label={state} color={stateColor(state)} />
                        <Typography variant="body2" color="text.secondary">
                            {section.detail || "—"}
                        </Typography>
                    </Stack>
                    <Stack direction="row" flexWrap="wrap" gap={1}>
                        {SAFE_METRIC_KEYS.map((key) => {
                            const value = metrics[key];
                            if (value == null || value === "") return null;
                            return (
                                <Chip
                                    key={key}
                                    size="small"
                                    variant="outlined"
                                    label={`${key}: ${String(value)}`}
                                />
                            );
                        })}
                    </Stack>
                </Stack>
            )}
        </SectionCard>
    );
}
