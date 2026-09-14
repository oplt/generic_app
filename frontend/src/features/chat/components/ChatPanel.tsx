import { Alert, Box, Button, Divider, Stack } from "@mui/material";
import { AutoAwesome as ChatIcon } from "@mui/icons-material";
import { SectionCard } from "../../../components/ui/SectionCard";
import { ChatInput } from "./ChatInput";
import { ChatMessageList } from "./ChatMessageList";
import { ChatModeSelector } from "./ChatModeSelector";
import type { ChatConversation, ChatMessage, ChatMode } from "../types";

type StreamingState = { user: string; answer: string; sources: ChatMessage["sources"] };

type ChatPanelProps = {
    mode: ChatMode;
    conversation: Pick<ChatConversation, "mode" | "memory_enabled" | "memory_write_enabled"> | undefined;
    messages: ChatMessage[];
    streaming: StreamingState | null;
    draft: string;
    memoryEnabled: boolean;
    memoryWriteEnabled: boolean;
    canSend: boolean;
    onModeChange: (mode: ChatMode) => void;
    onMemoryChange: (kind: "read" | "write", checked: boolean) => void;
    onDraftChange: (value: string) => void;
    onSend: () => void;
    onCancel: () => void;
    onClear: () => void;
    clearPending: boolean;
};

export function ChatPanel({
    mode,
    conversation,
    messages,
    streaming,
    draft,
    memoryEnabled,
    memoryWriteEnabled,
    canSend,
    onModeChange,
    onMemoryChange,
    onDraftChange,
    onSend,
    onCancel,
    onClear,
    clearPending,
}: ChatPanelProps) {
    const effectiveMode = conversation?.mode ?? mode;
    return (
        <SectionCard title="Knowledge chat" description="Choose how the assistant should use documents, memory, and the web." action={conversation ? <Button size="small" color="inherit" onClick={onClear} disabled={clearPending}>Clear history</Button> : undefined}>
            <Stack spacing={2}>
                <ChatModeSelector mode={mode} conversation={conversation} memoryEnabled={memoryEnabled} memoryWriteEnabled={memoryWriteEnabled} onModeChange={onModeChange} onMemoryChange={onMemoryChange} />
                <Alert severity="info" icon={<ChatIcon />}>
                    {effectiveMode === "documents" ? "Documents only · answers use selected indexed sources." : effectiveMode === "web" ? "Web search · results are untrusted and cited separately." : effectiveMode === "general" ? "General · uses the normal AI path and optional scoped memory." : "Auto route · chooses documents, web, or general based on the question."}
                </Alert>
                <Box role="log" aria-live="polite" aria-busy={Boolean(streaming)} aria-label="Chat messages" sx={{ minHeight: 380, maxHeight: "58vh", overflowY: "auto", pr: 0.5 }}>
                    <ChatMessageList messages={messages} streaming={streaming} mode={effectiveMode} />
                </Box>
                <Divider />
                <ChatInput draft={draft} streaming={Boolean(streaming)} canSend={canSend} onDraftChange={onDraftChange} onSend={onSend} onCancel={onCancel} />
            </Stack>
        </SectionCard>
    );
}
