import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../../api/client";
import { streamChatMessage } from "../api";
import { isFinalEvent, parseSseBuffer } from "../stream";
import type { ChatMessage, ChatMessageRequest } from "../types";

export type ActiveChatStream = {
    user: string;
    answer: string;
    sources: ChatMessage["sources"];
};

type UseChatStreamOptions = {
    onSettled?: (conversationId: string) => Promise<void> | void;
    onError?: (error: unknown) => void;
};

export function useChatStream({ onSettled, onError }: UseChatStreamOptions = {}) {
    const [streaming, setStreaming] = useState<ActiveChatStream | null>(null);
    const [error, setError] = useState<unknown>(null);
    const [cancelled, setCancelled] = useState(false);
    const abortRef = useRef<AbortController | null>(null);

    const cancel = useCallback(() => abortRef.current?.abort(), []);

    const send = useCallback(async (conversationId: string, payload: ChatMessageRequest) => {
        if (streaming) return;
        setError(null);
        setCancelled(false);
        setStreaming({ user: payload.content, answer: "", sources: [] });
        const controller = new AbortController();
        abortRef.current = controller;
        try {
            const response = await streamChatMessage(conversationId, payload, controller.signal);
            const reader = response.body?.getReader();
            if (!reader) throw new Error("The chat stream was unavailable.");
            const decoder = new TextDecoder();
            let buffer = "";
            let lastSequence = 0;
            while (true) {
                const result = await reader.read();
                buffer += decoder.decode(result.value ?? new Uint8Array(), { stream: !result.done });
                const parsed = parseSseBuffer(buffer);
                buffer = parsed.remainder;
                for (const envelope of parsed.events) {
                    if (envelope.contract_version !== "v1" || envelope.sequence <= lastSequence) {
                        throw new ApiError("The chat stream contract was invalid.", { code: "invalid_request" });
                    }
                    lastSequence = envelope.sequence;
                    const event = envelope.payload;
                    if (event.event === "token") {
                        setStreaming((current) => current ? { ...current, answer: current.answer + event.token } : current);
                    } else if (event.event === "source") {
                        setStreaming((current) => current ? { ...current, sources: [...current.sources, event.source] } : current);
                    } else if (event.event === "error") {
                        throw new ApiError(event.message, { code: event.code, retryable: event.retryable });
                    } else if (isFinalEvent(event)) {
                        setStreaming((current) => current ? { ...current, answer: event.answer, sources: event.sources } : current);
                    }
                }
                if (result.done) break;
            }
        } catch (error) {
            const cancelled = controller.signal.aborted
                || error instanceof ApiError && error.cancelled
                || error instanceof DOMException && error.name === "AbortError";
            if (cancelled) {
                setCancelled(true);
            } else {
                setError(error);
                onError?.(error);
            }
        } finally {
            abortRef.current = null;
            setStreaming(null);
            try {
                await onSettled?.(conversationId);
            } catch {
                // Stream cleanup must not surface a secondary cache error.
            }
        }
    }, [onError, onSettled, streaming]);

    useEffect(() => () => abortRef.current?.abort(), []);

    return { streaming, error, cancelled, send, cancel };
}
