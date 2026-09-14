import {
    Box,
    Button,
    Drawer,
    IconButton,
    Stack,
    Typography,
} from "@mui/material";
import { Close as CloseIcon } from "@mui/icons-material";
import { IdCell } from "../../../components/ui/IdCell";
import type { AdminJobsModel } from "../hooks/useAdminJobs";

export function JobDetailDrawer({ m }: { m: AdminJobsModel }) {
    const selected = m.selected;

    return (
        <Drawer
            anchor="right"
            open={Boolean(selected)}
            onClose={() => m.setSelected(null)}
            PaperProps={{ sx: { width: { xs: "100%", sm: 440 } } }}
        >
            {selected && (
                <Box sx={{ p: 2.5 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="h6">{selected.job_type}</Typography>
                        <IconButton
                            aria-label="Close job detail"
                            onClick={() => m.setSelected(null)}
                        >
                            <CloseIcon />
                        </IconButton>
                    </Stack>
                    <Stack spacing={1.25} sx={{ mt: 2 }}>
                        <Typography variant="body2" color="text.secondary">
                            {selected.source} · {selected.state} · {selected.queue}
                        </Typography>
                        <IdCell id={selected.id} />
                        <Typography variant="body2">
                            correlation={selected.correlation_id || "—"} · operation=
                            {selected.operation_id || "—"}
                        </Typography>
                        <Typography variant="body2">
                            duration={selected.duration_seconds ?? "—"}s · retries=
                            {selected.retries}
                        </Typography>
                        <Typography variant="body2">
                            error={selected.safe_error_summary || "none"}
                        </Typography>
                        <Box
                            component="pre"
                            sx={{
                                p: 1.5,
                                bgcolor: "action.hover",
                                borderRadius: 1,
                                whiteSpace: "pre-wrap",
                                fontSize: 12,
                                maxHeight: 240,
                                overflow: "auto",
                            }}
                        >
                            {JSON.stringify(selected.payload_summary, null, 2)}
                        </Box>
                        <Stack direction="row" spacing={1}>
                            <Button
                                variant="contained"
                                disabled={!selected.can_retry || m.retryMutation.isPending}
                                onClick={() => m.retryMutation.mutate(selected)}
                            >
                                Retry
                            </Button>
                            <Button
                                variant="outlined"
                                color="warning"
                                disabled={!selected.can_cancel || m.cancelMutation.isPending}
                                onClick={() => m.setCancelTarget(selected)}
                            >
                                Cancel
                            </Button>
                        </Stack>
                        {!selected.can_retry && selected.retry_blocked_reason && (
                            <Typography variant="caption" color="text.secondary">
                                {selected.retry_blocked_reason}
                            </Typography>
                        )}
                    </Stack>
                </Box>
            )}
        </Drawer>
    );
}
