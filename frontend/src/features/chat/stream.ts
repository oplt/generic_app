import type { ChatEvent, ChatEventEnvelope } from "./types";

export function parseSseBuffer(buffer: string): {
    events: ChatEventEnvelope[];
    remainder: string;
} {
    const blocks = buffer.split(/\r?\n\r?\n/);
    const remainder = blocks.pop() ?? "";
    const events = blocks.flatMap((block) => {
        const data = block
            .split(/\r?\n/)
            .find((line) => line.startsWith("data:"))
            ?.slice("data:".length)
            .trim();
        if (!data) return [];
        try {
            const parsed = JSON.parse(data) as ChatEventEnvelope;
            return parsed.payload ? [parsed] : [];
        } catch {
            return [];
        }
    });
    return { events, remainder };
}

export function isFinalEvent(event: ChatEvent): event is Extract<ChatEvent, { event: "final" }> {
    return event.event === "final";
}
