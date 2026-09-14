import { describe, expect, it } from "vitest";

import { validateDocumentUpload } from "./uploadValidation";

describe("validateDocumentUpload", () => {
    it("accepts supported files within the size budget", () => {
        expect(validateDocumentUpload(new File(["hello"], "notes.md"))).toBeNull();
    });

    it("rejects unsupported file types and oversized files", () => {
        expect(validateDocumentUpload(new File(["hello"], "notes.pdf"))).toContain(".txt");
        const oversized = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "notes.txt");
        expect(validateDocumentUpload(oversized)).toContain("10 MB");
    });
});
