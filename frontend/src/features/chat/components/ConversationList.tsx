import { DeleteOutline as DeleteIcon } from "@mui/icons-material";
import { CircularProgress, IconButton, ListItemButton, ListItemText, Stack, Typography } from "@mui/material";
import type { ChatConversationSummary } from "../types";

type ConversationListProps = {
    conversations: ChatConversationSummary[];
    activeConversationId: string | null;
    isLoading: boolean;
    onSelect: (conversationId: string) => void;
    onDelete: (conversationId: string) => void;
};

export function ConversationList({ conversations, activeConversationId, isLoading, onSelect, onDelete }: ConversationListProps) {
    if (isLoading) return <CircularProgress size={24} />;
    if (conversations.length === 0) return <Typography variant="body2" color="text.secondary">No conversations yet. Select documents and ask your first question.</Typography>;
    return (
        <Stack spacing={1}>
            {conversations.map((item) => (
                <ListItemButton key={item.id} selected={item.id === activeConversationId} onClick={() => onSelect(item.id)} sx={{ borderRadius: 2 }}>
                    <ListItemText primary={item.title} secondary={item.mode === "documents" ? "Strict documents" : item.mode} primaryTypographyProps={{ noWrap: true }} />
                    <IconButton aria-label={`Delete ${item.title}`} size="small" onClick={(event) => { event.stopPropagation(); onDelete(item.id); }}><DeleteIcon fontSize="small" /></IconButton>
                </ListItemButton>
            ))}
        </Stack>
    );
}
