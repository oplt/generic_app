import { describe, expect, it } from "vitest";

import { parseSseBuffer } from "./stream";

describe("chat SSE parser", () => {
    it("parses complete events and preserves a partial block", () => {
        const result = parseSseBuffer(
            'event: token\ndata: {"contract_version":"v1","sequence":1,"payload":{"event":"token","token":"Hello "}}\n\n' +
            'event: final\ndata: {"contract_version":"v1","sequence":2,"payload":{"event":"final","message_id":"m1","answer":"Hello","sources":[]}}\n\n' +
            "event: status\ndata: {",
        );

        expect(result.events).toHaveLength(2);
        expect(result.events[0].payload.event).toBe("token");
        expect(result.events[1].payload.event).toBe("final");
        expect(result.remainder).toContain("event: status");
    });
});
