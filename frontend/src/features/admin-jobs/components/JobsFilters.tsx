import {
    Box,
    FormControl,
    FormControlLabel,
    InputLabel,
    MenuItem,
    Select,
    Switch,
    TextField,
} from "@mui/material";
import { SectionCard } from "../../../components/ui/SectionCard";
import type { AdminJobsModel } from "../hooks/useAdminJobs";

export function JobsFilters({ m }: { m: AdminJobsModel }) {
    return (
        <SectionCard title="Filters">
            <Box
                sx={{
                    display: "grid",
                    gap: 1.5,
                    gridTemplateColumns: {
                        xs: "1fr",
                        md: "minmax(140px, 0.35fr) repeat(3, minmax(0, 1fr)) auto",
                    },
                    alignItems: "center",
                }}
            >
                <FormControl fullWidth>
                    <InputLabel id="status-label">Status</InputLabel>
                    <Select
                        labelId="status-label"
                        label="Status"
                        value={m.status}
                        onChange={(event) => m.setStatus(event.target.value)}
                    >
                        <MenuItem value="">Any</MenuItem>
                        {[
                            "queued",
                            "running",
                            "retrying",
                            "succeeded",
                            "failed",
                            "cancelled",
                            "stale",
                        ].map((value) => (
                            <MenuItem key={value} value={value}>
                                {value}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>
                <TextField
                    label="Job type"
                    value={m.jobType}
                    onChange={(event) => m.setJobType(event.target.value)}
                    fullWidth
                />
                <TextField
                    label="Queue"
                    value={m.queue}
                    onChange={(event) => m.setQueue(event.target.value)}
                    fullWidth
                />
                <TextField
                    label="Project ID"
                    value={m.projectId}
                    onChange={(event) => m.setProjectId(event.target.value)}
                    fullWidth
                />
                <FormControlLabel
                    control={
                        <Switch
                            checked={m.failedOnly}
                            onChange={(event) => m.setFailedOnly(event.target.checked)}
                        />
                    }
                    label="Failures"
                />
            </Box>
        </SectionCard>
    );
}
