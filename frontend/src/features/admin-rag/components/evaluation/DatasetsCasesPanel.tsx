import {
    Box,
    Button,
    FormControl,
    InputLabel,
    MenuItem,
    Select,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";
import { EmptyState } from "../../../../components/ui/EmptyState";
import { SectionCard } from "../../../../components/ui/SectionCard";
import type { RagEvaluationModel } from "../../hooks/useRagEvaluation";

export function DatasetsCasesPanel({ m }: { m: RagEvaluationModel }) {
    return (
        <Stack spacing={2.5}>
            <SectionCard title="Datasets">
                <Box
                    sx={{
                        display: "grid",
                        gap: 1.5,
                        gridTemplateColumns: {
                            xs: "1fr",
                            md: "auto auto minmax(0, 1fr)",
                        },
                        mb: 1.5,
                        alignItems: "start",
                    }}
                >
                    <Button
                        variant="contained"
                        onClick={() => m.createDatasetMutation.mutate()}
                        disabled={m.createDatasetMutation.isPending}
                    >
                        New dataset
                    </Button>
                    <Button
                        variant="outlined"
                        onClick={() => m.importGoldenMutation.mutate()}
                        disabled={m.importGoldenMutation.isPending}
                    >
                        Import golden_v1
                    </Button>
                    <FormControl fullWidth>
                        <InputLabel id="dataset-label">Dataset</InputLabel>
                        <Select
                            labelId="dataset-label"
                            label="Dataset"
                            value={m.datasetId}
                            onChange={(event) => m.setDatasetId(event.target.value)}
                        >
                            {(m.datasetsQuery.data ?? []).map((dataset) => (
                                <MenuItem key={dataset.id} value={dataset.id}>
                                    {dataset.name}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>
                </Box>
                {m.selectedDataset ? (
                    <Typography variant="caption" color="text.secondary">
                        {m.selectedDataset.description || "No description"} · tags:{" "}
                        {m.selectedDataset.tags?.join(", ") || "none"}
                    </Typography>
                ) : null}
            </SectionCard>

            <SectionCard title="Cases">
                {!m.datasetId ? (
                    <EmptyState
                        title="Select a dataset"
                        description="Choose or create a dataset to manage evaluation cases."
                    />
                ) : (
                    <Stack spacing={1.5}>
                        <Box
                            sx={{
                                display: "grid",
                                gap: 1.5,
                                gridTemplateColumns: {
                                    xs: "1fr",
                                    md: "minmax(0, 1.2fr) minmax(0, 1fr) auto",
                                },
                                alignItems: "start",
                            }}
                        >
                            <TextField
                                label="Question"
                                value={m.caseQuestion}
                                onChange={(event) => m.setCaseQuestion(event.target.value)}
                                fullWidth
                            />
                            <TextField
                                label="Expected chunk IDs"
                                value={m.caseChunks}
                                onChange={(event) => m.setCaseChunks(event.target.value)}
                                fullWidth
                                placeholder="comma-separated"
                            />
                            <Button
                                variant="outlined"
                                onClick={() => m.createCaseMutation.mutate()}
                                disabled={m.createCaseMutation.isPending || !m.caseQuestion.trim()}
                                sx={{ height: 56 }}
                            >
                                Add case
                            </Button>
                        </Box>
                        <Table size="small" stickyHeader>
                            <TableHead>
                                <TableRow>
                                    <TableCell>Question</TableCell>
                                    <TableCell>Expected chunks</TableCell>
                                    <TableCell>Tags</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {(m.casesQuery.data ?? []).map((item) => (
                                    <TableRow key={item.id} hover>
                                        <TableCell>{item.question}</TableCell>
                                        <TableCell>
                                            <Typography
                                                variant="caption"
                                                sx={{
                                                    fontFamily: "ui-monospace, monospace",
                                                    display: "block",
                                                    maxWidth: 280,
                                                    overflow: "hidden",
                                                    textOverflow: "ellipsis",
                                                    whiteSpace: "nowrap",
                                                }}
                                                title={item.expected_chunk_ids?.join(", ") || undefined}
                                            >
                                                {item.expected_chunk_ids?.join(", ") || "—"}
                                            </Typography>
                                        </TableCell>
                                        <TableCell>{item.tags?.join(", ") || "—"}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </Stack>
                )}
            </SectionCard>
        </Stack>
    );
}
