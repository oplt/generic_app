import { describe, expect, it } from "vitest";

import type { ChatEvent, ChatMessageRequest } from "./types";

describe("chat Phase 0 contracts", () => {
    it("keeps ownership out of client request payloads", () => {
        const request = {
            content: "Summarize the selected document",
            mode: "documents",
            project_id: "project-1",
            document_ids: ["document-1"],
        } satisfies ChatMessageRequest;

        expect(request).not.toHaveProperty("user_id");
        expect(request).not.toHaveProperty("organization_id");
    });

    it("represents a typed final stream event", () => {
        const event = {
            event: "final",
            message_id: "message-1",
            answer: "The document describes the rollout.",
            sources: [],
        } satisfies ChatEvent;

        expect(event.event).toBe("final");
        expect(event.sources).toEqual([]);
    });
});
