import {
    Box,
    Button,
    Stack,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TextField,
    Typography,
} from "@mui/material";
import { ragEvalExportUrl } from "../../../../api/ragEvaluation";
import { EmptyState } from "../../../../components/ui/EmptyState";
import { IdCell } from "../../../../components/ui/IdCell";
import { SectionCard } from "../../../../components/ui/SectionCard";
import type { RagEvaluationModel } from "../../hooks/useRagEvaluation";

export function RunsPanel({ m }: { m: RagEvaluationModel }) {
    return (
        <SectionCard title="Runs / comparison">
            {!m.datasetId ? (
                <EmptyState
                    title="Select a dataset"
                    description="Runs are scoped to the selected evaluation dataset."
                />
            ) : (
                <Stack spacing={1.5}>
                    <Box
                        sx={{
                            display: "grid",
                            gap: 1.5,
                            gridTemplateColumns: {
                                xs: "1fr",
                                md: "minmax(0, 1fr) auto",
                            },
                            alignItems: "start",
                        }}
                    >
                        <TextField
                            label="Baseline run ID (optional)"
                            value={m.baselineRunId}
                            onChange={(event) => m.setBaselineRunId(event.target.value)}
                            fullWidth
                        />
                        <Button
                            variant="contained"
                            onClick={() => m.runMutation.mutate()}
                            disabled={m.runMutation.isPending}
                            sx={{ height: 56 }}
                        >
                            Run evaluation
                        </Button>
                    </Box>
                    <Table size="small" stickyHeader>
                        <TableHead>
                            <TableRow>
                                <TableCell>Name</TableCell>
                                <TableCell>Status</TableCell>
                                <TableCell>Metrics</TableCell>
                                <TableCell>Δ vs baseline</TableCell>
                                <TableCell align="right">Export</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {(m.runsQuery.data ?? []).map((run) => (
                                <TableRow key={run.id} hover>
                                    <TableCell>
                                        <IdCell id={run.id} label={run.name} mono={false} />
                                    </TableCell>
                                    <TableCell>{run.status}</TableCell>
                                    <TableCell>
                                        <Typography variant="caption" component="span">
                                            R@K={String(run.metrics?.recall_at_k ?? "—")} · MRR=
                                            {String(run.metrics?.mrr ?? "—")} · nDCG=
                                            {String(run.metrics?.ndcg_at_k ?? "—")}
                                        </Typography>
                                    </TableCell>
                                    <TableCell>
                                        <Typography variant="caption" component="span">
                                            {run.comparison?.deltas
                                                ? Object.entries(run.comparison.deltas)
                                                      .map(
                                                          ([key, value]) =>
                                                              `${key}:${value > 0 ? "+" : ""}${value}`
                                                      )
                                                      .join(" · ")
                                                : "—"}
                                        </Typography>
                                    </TableCell>
                                    <TableCell align="right">
                                        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                                            <Button size="small" href={ragEvalExportUrl(run.id, "json")}>
                                                JSON
                                            </Button>
                                            <Button size="small" href={ragEvalExportUrl(run.id, "csv")}>
                                                CSV
                                            </Button>
                                        </Stack>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </Stack>
            )}
        </SectionCard>
    );
}
