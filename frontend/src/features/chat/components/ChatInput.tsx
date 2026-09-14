import { Button, Stack, TextField } from "@mui/material";
import { Send as SendIcon, Stop as StopIcon } from "@mui/icons-material";

type ChatInputProps = {
    draft: string;
    streaming: boolean;
    canSend: boolean;
    onDraftChange: (value: string) => void;
    onSend: () => void;
    onCancel: () => void;
};

export function ChatInput({ draft, streaming, canSend, onDraftChange, onSend, onCancel }: ChatInputProps) {
    return (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "flex-end" }}>
            <TextField label="Ask a question" value={draft} onChange={(event) => onDraftChange(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); onSend(); } }} multiline minRows={2} maxRows={6} fullWidth disabled={streaming} helperText={canSend ? "Enter to send · Shift+Enter for a new line" : "Select at least one indexed document for this mode"} />
            <Button variant="contained" onClick={streaming ? onCancel : onSend} disabled={!streaming && (!draft.trim() || !canSend)} startIcon={streaming ? <StopIcon /> : <SendIcon />} aria-label={streaming ? "Stop answer" : "Ask question"} sx={{ minWidth: 120, minHeight: 48 }}>{streaming ? "Stop" : "Ask"}</Button>
        </Stack>
    );
}
