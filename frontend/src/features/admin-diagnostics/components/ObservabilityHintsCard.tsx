import { Box, Button, Stack } from "@mui/material";
import type { DiagnosticsReport } from "../../../api/diagnostics";
import { SectionCard } from "../../../components/ui/SectionCard";

export function ObservabilityHintsCard({
    hints,
}: {
    hints: DiagnosticsReport["observability_hints"];
}) {
    const grafana =
        typeof hints?.grafana_base_url === "string"
            ? String(hints.grafana_base_url)
            : "/observability";
    const tempo =
        typeof hints?.tempo_explore_url === "string"
            ? String(hints.tempo_explore_url)
            : "/observability";

    return (
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
                    {JSON.stringify(hints ?? {}, null, 2)}
                </Box>
                <Stack direction="row" spacing={1}>
                    <Button size="small" href={grafana} target="_blank" rel="noreferrer">
                        Grafana
                    </Button>
                    <Button size="small" href={tempo} target="_blank" rel="noreferrer">
                        Tempo
                    </Button>
                    <Button size="small" href="/observability">
                        Observability page
                    </Button>
                </Stack>
            </Stack>
        </SectionCard>
    );
}
