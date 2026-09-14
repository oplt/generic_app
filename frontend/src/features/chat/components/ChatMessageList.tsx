import { Stack } from "@mui/material";
import { Description as DocumentIcon } from "@mui/icons-material";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ChatMessageBubble } from "./ChatMessageBubble";
import type { ChatMessage } from "../types";

type ChatMessageListProps = {
    messages: ChatMessage[];
    streaming: { user: string; answer: string; sources: ChatMessage["sources"] } | null;
    mode: ChatMessage["mode"];
};

export function ChatMessageList({ messages, streaming, mode }: ChatMessageListProps) {
    return messages.length === 0 && !streaming ? (
        <EmptyState icon={<DocumentIcon />} title="Start with a question" description="Select documents for grounded answers, or choose general/web mode for other questions." />
    ) : (
        <Stack spacing={2}>
            {messages.map((message) => <ChatMessageBubble key={message.id} message={message} />)}
            {streaming && <>
                <ChatMessageBubble message={{ id: "streaming-user", role: "user", content: streaming.user, mode, document_ids: [], status: "completed", ai_run_id: null, model_name: null, route_reason: null, route_confidence: null, created_at: new Date().toISOString(), sources: [] }} />
                <ChatMessageBubble message={{ id: "streaming-answer", role: "assistant", content: streaming.answer, mode, document_ids: [], status: "generating", ai_run_id: null, model_name: null, route_reason: null, route_confidence: null, created_at: new Date().toISOString(), sources: streaming.sources }} />
            </>}
        </Stack>
    );
}
