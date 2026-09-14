import {
    Box,
    Button,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { SectionCard } from "../../../../components/ui/SectionCard";
import type { RagEvaluationModel } from "../../hooks/useRagEvaluation";
import { AssembledContextViewer, CandidateTable } from "./CandidateInspection";

export function ProbePanel({ m }: { m: RagEvaluationModel }) {
    return (
        <SectionCard title="Interactive probe">
            <Stack spacing={1.5}>
                <TextField
                    label="Query"
                    value={m.query}
                    onChange={(event) => m.setQuery(event.target.value)}
                    fullWidth
                />
                <Box
                    sx={{
                        display: "grid",
                        gap: 1.5,
                        gridTemplateColumns: {
                            xs: "1fr",
                            md: "minmax(160px, 0.35fr) 120px minmax(0, 1fr) auto",
                        },
                        alignItems: "start",
                    }}
                >
                    <FormControl fullWidth>
                        <InputLabel id="strategy-label">Strategy</InputLabel>
                        <Select
                            labelId="strategy-label"
                            label="Strategy"
                            value={m.strategy}
                            onChange={(event) =>
                                m.setStrategy(event.target.value as typeof m.strategy)
                            }
                        >
                            <MenuItem value="hybrid_rrf">hybrid_rrf</MenuItem>
                            <MenuItem value="vector">vector</MenuItem>
                            <MenuItem value="lexical">lexical</MenuItem>
                        </Select>
                    </FormControl>
                    <TextField
                        label="top_k"
                        type="number"
                        value={m.topK}
                        onChange={(event) => m.setTopK(Number(event.target.value) || 5)}
                    />
                    <TextField
                        label="Project ID (optional)"
                        value={m.projectId}
                        onChange={(event) => m.setProjectId(event.target.value)}
                        fullWidth
                    />
                    <Button
                        variant="contained"
                        onClick={() => m.probeMutation.mutate()}
                        disabled={m.probeMutation.isPending || !m.query.trim()}
                        sx={{ height: 56 }}
                    >
                        Probe
                    </Button>
                </Box>
                {m.probe && (
                    <Stack spacing={1.5}>
                        <Typography variant="caption" color="text.secondary">
                            strategy={m.probe.strategy} · latencies(ms):{" "}
                            {Object.entries(m.probe.latencies_ms ?? {})
                                .map(([key, value]) => `${key}=${value}`)
                                .join(" · ")}
                        </Typography>
                        <CandidateTable candidates={m.probe.candidates ?? []} />
                        <AssembledContextViewer context={m.probe.assembled_context || ""} />
                    </Stack>
                )}
            </Stack>
        </SectionCard>
    );
}
