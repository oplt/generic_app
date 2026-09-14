import {
    Button,
    List,
    ListItem,
    ListItemText,
    Stack,
    Typography,
} from "@mui/material";
import type { RagDocument, RagIngestionJob } from "../types";
import { DocumentList } from "./DocumentList";
import { DocumentUpload, type UploadProgressState } from "./DocumentUpload";

type DocumentPanelProps = {
    documents: RagDocument[];
    selectedDocumentIds: string[];
    isLoading: boolean;
    isUploading: boolean;
    uploadProgress: UploadProgressState | null;
    jobs: RagIngestionJob[];
    retryPending: boolean;
    onUploadFile: (file: File) => void;
    onToggleDocument: (document: RagDocument) => void;
    onReindex: (documentId: string) => void;
    reindexPending: boolean;
    onRetryJob: (jobId: string) => void;
    onDelete: (documentId: string) => void;
    deletePending: boolean;
};

export function DocumentPanel({
    documents,
    selectedDocumentIds,
    isLoading,
    isUploading,
    uploadProgress,
    jobs,
    retryPending,
    onUploadFile,
    onToggleDocument,
    onReindex,
    reindexPending,
    onRetryJob,
    onDelete,
    deletePending,
}: DocumentPanelProps) {
    return (
        <Stack spacing={1.25}>
            <DocumentUpload isUploading={isUploading} progress={uploadProgress} onUploadFile={onUploadFile} />
            <DocumentList documents={documents} selectedDocumentIds={selectedDocumentIds} isLoading={isLoading} onToggleDocument={onToggleDocument} onReindex={onReindex} reindexPending={reindexPending} onDelete={onDelete} deletePending={deletePending} />
            {jobs.length > 0 && (
                <Stack spacing={0.75}>
                    <Typography variant="caption" color="text.secondary">Ingestion history</Typography>
                    <List dense disablePadding>
                        {jobs.slice(0, 8).map((job) => (
                            <ListItem key={job.id} disableGutters secondaryAction={job.status === "failed" ? <Button size="small" onClick={() => onRetryJob(job.id)} disabled={retryPending}>Retry</Button> : undefined}>
                                <ListItemText primary={job.status === "completed" ? "Indexed" : job.status === "failed" ? "Indexing failed" : job.status === "running" ? "Indexing" : "Queued for indexing"} secondary={job.error_message || new Date(job.created_at).toLocaleString()} />
                            </ListItem>
                        ))}
                    </List>
                </Stack>
            )}
        </Stack>
    );
}
