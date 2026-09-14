import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./client", () => ({
    API_BASE: "http://localhost:8000/api/v1",
    apiFetch: vi.fn(async (_path: string) => ({ ok: true })),
}));

import { apiFetch } from "./client";
import { customFetch } from "./orvalMutator";

describe("orvalMutator", () => {
    afterEach(() => {
        vi.mocked(apiFetch).mockClear();
    });

    it("strips /api/v1 prefix for apiFetch", async () => {
        await customFetch("/api/v1/profile", { method: "GET" });
        expect(apiFetch).toHaveBeenCalledWith("/profile", { method: "GET" });
    });

    it("strips absolute API_BASE URLs", async () => {
        await customFetch("http://localhost:8000/api/v1/projects", { method: "GET" });
        expect(apiFetch).toHaveBeenCalledWith("/projects", { method: "GET" });
    });
});
