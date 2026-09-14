import { Paper, Stack, Typography } from "@mui/material";
import type { ChatMessage } from "../types";
import { SourceCitationList } from "./SourceCitationList";

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
    const isUser = message.role === "user";
    return (
        <Stack alignItems={isUser ? "flex-end" : "flex-start"} spacing={0.75}>
            <Paper
                elevation={0}
                sx={(theme) => ({
                    maxWidth: { xs: "94%", md: "78%" },
                    px: 2,
                    py: 1.5,
                    borderRadius: 3,
                    backgroundColor: isUser ? theme.palette.primary.main : theme.palette.background.default,
                    color: isUser ? theme.palette.primary.contrastText : "text.primary",
                    border: isUser ? "none" : `1px solid ${theme.palette.divider}`,
                    whiteSpace: "pre-wrap",
                })}
            >
                <Typography variant="body2">{message.content || "Generating answer…"}</Typography>
            </Paper>
            <SourceCitationList sources={message.sources} />
        </Stack>
    );
}
