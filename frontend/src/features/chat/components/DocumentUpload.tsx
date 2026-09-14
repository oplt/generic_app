import { Button, LinearProgress, Stack, Typography } from "@mui/material";
import { UploadFile as UploadIcon } from "@mui/icons-material";
import type { RagIngestionJob } from "../types";

export type UploadProgressState = {
    filename: string;
    percent: number;
    job: RagIngestionJob | null;
    duplicate?: boolean;
};

type DocumentUploadProps = {
    isUploading: boolean;
    progress: UploadProgressState | null;
    onUploadFile: (file: File) => void;
};

function jobStatusLabel(job: RagIngestionJob) {
    if (job.status === "completed") return "Indexed";
    if (job.status === "failed") return "Indexing failed";
    return job.status === "running" ? "Indexing" : "Queued for indexing";
}

export function DocumentUpload({ isUploading, progress, onUploadFile }: DocumentUploadProps) {
    return (
        <>
            <Button component="label" variant="outlined" startIcon={<UploadIcon />} disabled={isUploading}>
                {isUploading ? "Uploading…" : "Upload document"}
                <input hidden type="file" accept=".pdf,.txt,.md,.docx,.csv" onChange={(event) => { const file = event.target.files?.[0]; if (file) onUploadFile(file); event.currentTarget.value = ""; }} />
            </Button>
            {progress && (
                <Stack spacing={0.5} aria-live="polite">
                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                        <Typography variant="caption" noWrap>{progress.filename}</Typography>
                        <Typography variant="caption" color="text.secondary">{progress.duplicate ? "Already uploaded" : progress.job ? jobStatusLabel(progress.job) : `${progress.percent}% uploaded`}</Typography>
                    </Stack>
                    <LinearProgress variant="determinate" value={progress.percent} />
                </Stack>
            )}
        </>
    );
}
