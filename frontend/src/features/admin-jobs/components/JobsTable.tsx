import {
    Button,
    Chip,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    Typography,
} from "@mui/material";
import { IdCell } from "../../../components/ui/IdCell";
import { SectionCard } from "../../../components/ui/SectionCard";
import { jobStateColor, type AdminJobsModel } from "../hooks/useAdminJobs";

export function JobsTable({ m }: { m: AdminJobsModel }) {
    return (
        <SectionCard title={`Jobs (${m.listQuery.data?.total ?? 0})`}>
            <Table size="small" stickyHeader>
                <TableHead>
                    <TableRow>
                        <TableCell>Type</TableCell>
                        <TableCell>State</TableCell>
                        <TableCell>Queue</TableCell>
                        <TableCell>Attempts</TableCell>
                        <TableCell>Created</TableCell>
                        <TableCell>Error</TableCell>
                        <TableCell align="right">Actions</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {(m.listQuery.data?.items ?? []).map((job) => (
                        <TableRow key={`${job.source}:${job.id}`} hover>
                            <TableCell>
                                <IdCell id={job.id} label={job.job_type} mono={false} />
                                <Typography variant="caption" color="text.secondary">
                                    {job.source}
                                </Typography>
                            </TableCell>
                            <TableCell>
                                <Chip
                                    size="small"
                                    label={job.state}
                                    color={jobStateColor(job.state)}
                                />
                            </TableCell>
                            <TableCell>{job.queue}</TableCell>
                            <TableCell>
                                {job.attempts}/{job.max_attempts}
                            </TableCell>
                            <TableCell>
                                {job.created_at ? new Date(job.created_at).toLocaleString() : "—"}
                            </TableCell>
                            <TableCell>
                                <Typography
                                    variant="body2"
                                    noWrap
                                    sx={{ maxWidth: 180 }}
                                    title={job.safe_error_summary || undefined}
                                >
                                    {job.safe_error_summary || "—"}
                                </Typography>
                            </TableCell>
                            <TableCell align="right">
                                <Button size="small" onClick={() => m.detailMutation.mutate(job)}>
                                    Detail
                                </Button>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </SectionCard>
    );
}
