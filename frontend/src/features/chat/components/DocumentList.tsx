import { CheckCircle as IndexedIcon, DeleteOutline as DeleteIcon, Description as DocumentIcon } from "@mui/icons-material";
import { Button, CircularProgress, Chip, IconButton, List, ListItem, ListItemButton, ListItemText, Stack } from "@mui/material";
import { EmptyState } from "../../../components/ui/EmptyState";
import type { RagDocument } from "../types";

type DocumentListProps = {
    documents: RagDocument[];
    selectedDocumentIds: string[];
    isLoading: boolean;
    onToggleDocument: (document: RagDocument) => void;
    onReindex: (documentId: string) => void;
    reindexPending: boolean;
    onDelete: (documentId: string) => void;
    deletePending: boolean;
};

function statusLabel(status: string) {
    return status === "indexed" ? "Indexed" : status.replaceAll("_", " ");
}

export function DocumentList({ documents, selectedDocumentIds, isLoading, onToggleDocument, onReindex, reindexPending, onDelete, deletePending }: DocumentListProps) {
    const indexedDocuments = documents.filter((document) => document.status === "indexed");
    if (isLoading) return <CircularProgress size={24} />;
    if (indexedDocuments.length === 0) {
        return <EmptyState icon={<DocumentIcon />} title="No indexed documents" description="Upload a PDF, text, Markdown, DOCX, or CSV file, then wait for indexing to finish." />;
    }
    return (
        <Stack spacing={1}>
            <List dense disablePadding>
                {documents.map((document) => (
                    <ListItem key={document.id} disablePadding secondaryAction={<IconButton aria-label={`Delete ${document.original_filename || document.filename}`} size="small" onClick={() => onDelete(document.id)} disabled={deletePending}><DeleteIcon fontSize="small" /></IconButton>}>
                        <ListItemButton selected={selectedDocumentIds.includes(document.id)} disabled={document.status !== "indexed" || document.needs_reindex} onClick={() => onToggleDocument(document)} sx={{ borderRadius: 2, pr: document.needs_reindex ? 12 : undefined }}>
                            <ListItemText primary={document.original_filename || document.filename} secondary={document.needs_reindex ? "Re-index required" : statusLabel(document.status)} />
                            {document.status === "indexed" && <IndexedIcon color={selectedDocumentIds.includes(document.id) ? "primary" : "disabled"} fontSize="small" />}
                        </ListItemButton>
                        {document.needs_reindex && <Button size="small" onClick={() => onReindex(document.id)} disabled={reindexPending}>Re-index</Button>}
                    </ListItem>
                ))}
            </List>
            {selectedDocumentIds.length > 0 && <Chip size="small" label={`${selectedDocumentIds.length} selected`} color="primary" variant="outlined" />}
        </Stack>
    );
}
