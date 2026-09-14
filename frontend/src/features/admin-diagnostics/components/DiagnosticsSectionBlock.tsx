import { Box, Chip, Stack, Typography } from "@mui/material";
import type { DiagnosticsSection, OperationalState } from "../../../api/diagnostics";
import { SectionCard } from "../../../components/ui/SectionCard";
import { diagnosticsStateColor } from "./diagnosticsStateColor";

export function DiagnosticsSectionBlock({
    title,
    section,
}: {
    title: string;
    section: DiagnosticsSection;
}) {
    const state = (section.state ?? "unknown") as OperationalState;
    return (
        <SectionCard title={title}>
            <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center">
                    <Chip size="small" label={state} color={diagnosticsStateColor(state)} />
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
