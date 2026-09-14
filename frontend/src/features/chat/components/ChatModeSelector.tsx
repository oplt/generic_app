import { FormControl, FormControlLabel, InputLabel, MenuItem, Select, Stack, Switch } from "@mui/material";
import type { ChatConversation, ChatMode } from "../types";

type ChatModeSelectorProps = {
    mode: ChatMode;
    conversation: Pick<ChatConversation, "mode" | "memory_enabled" | "memory_write_enabled"> | undefined;
    memoryEnabled: boolean;
    memoryWriteEnabled: boolean;
    onModeChange: (mode: ChatMode) => void;
    onMemoryChange: (kind: "read" | "write", checked: boolean) => void;
};

export function ChatModeSelector({ mode, conversation, memoryEnabled, memoryWriteEnabled, onModeChange, onMemoryChange }: ChatModeSelectorProps) {
    const effectiveMode = conversation?.mode ?? mode;
    return (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "center" }}>
            <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id="chat-mode-label">Chat mode</InputLabel>
                <Select labelId="chat-mode-label" label="Chat mode" value={effectiveMode} disabled={Boolean(conversation)} onChange={(event) => onModeChange(event.target.value as ChatMode)}>
                    <MenuItem value="auto">Auto route</MenuItem>
                    <MenuItem value="documents">Documents only</MenuItem>
                    <MenuItem value="general">General + memory</MenuItem>
                    <MenuItem value="web">Web search</MenuItem>
                </Select>
            </FormControl>
            {(effectiveMode === "auto" || effectiveMode === "general") && (
                <Stack direction={{ xs: "column", sm: "row" }}>
                    <FormControlLabel control={<Switch checked={conversation?.memory_enabled ?? memoryEnabled} onChange={(event) => onMemoryChange("read", event.target.checked)} />} label="Use saved memory" />
                    <FormControlLabel control={<Switch checked={conversation?.memory_write_enabled ?? memoryWriteEnabled} onChange={(event) => onMemoryChange("write", event.target.checked)} />} label="Save useful turns" />
                </Stack>
            )}
        </Stack>
    );
}
