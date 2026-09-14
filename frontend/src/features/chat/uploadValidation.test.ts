import { describe, expect, it } from "vitest";

import { validateChatUpload } from "./uploadValidation";

describe("validateChatUpload", () => {
    it("accepts supported RAG files", () => {
        expect(validateChatUpload(new File(["hello"], "notes.md"))).toBeNull();
        expect(validateChatUpload(new File(["hello"], "report.pdf"))).toBeNull();
    });

    it("rejects unsupported and oversized files before network work", () => {
        expect(validateChatUpload(new File(["hello"], "notes.exe"))).toContain(".pdf");
        const oversized = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "notes.txt");
        expect(validateChatUpload(oversized)).toContain("10 MB");
    });
});
