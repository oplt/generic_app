import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, apiFetchItems, type ApiError } from "./client";

describe("apiFetchItems", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("returns items without changing request behavior", async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(
                JSON.stringify({ items: [{ id: "item-1" }], total: 1, limit: 50, offset: 0 }),
                { status: 200, headers: { "Content-Type": "application/json" } }
            )
        );
        vi.stubGlobal("fetch", fetchMock);

        const items = await apiFetchItems<{ id: string }>("/items");

        expect(items).toEqual([{ id: "item-1" }]);
        expect(fetchMock).toHaveBeenCalledWith(
            "http://localhost:8000/api/v1/items",
            expect.objectContaining({ credentials: "include" })
        );
    });

    it("exposes structured API failures to callers", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(
                new Response(JSON.stringify({ detail: "Validation failed" }), {
                    status: 422,
                    headers: { "Content-Type": "application/json", "X-Correlation-ID": "req-1" },
                })
            )
        );

        await expect(apiFetch("/items")).rejects.toMatchObject({
            name: "ApiError",
            message: "Validation failed",
            status: 422,
            correlationId: "req-1",
            retryable: false,
        });
    });

    it("preserves field validation details and cancellation state", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(
                new Response(JSON.stringify({ detail: [
                    { loc: ["body", "name"], msg: "Name is required" },
                ] }), { status: 422 })
            )
        );

        await expect(apiFetch("/items")).rejects.toMatchObject({
            fieldErrors: { name: ["Name is required"] },
        });

        const controller = new AbortController();
        controller.abort();
        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")));

        await expect(apiFetch("/items", { signal: controller.signal })).rejects.toMatchObject({
            name: "ApiError",
            cancelled: true,
            retryable: false,
        } satisfies Partial<ApiError>);
    });
});
