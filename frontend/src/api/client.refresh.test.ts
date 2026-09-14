import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
    AUTH_SESSION_EXPIRED_EVENT,
    ApiError,
    apiFetch,
    apiFetchStream,
    apiUpload,
    beginAuthLogout,
    markAuthSessionActive,
} from "./client";

type Deferred<T> = {
    promise: Promise<T>;
    resolve: (value: T) => void;
};

function deferred<T>(): Deferred<T> {
    let resolve!: (value: T) => void;
    const promise = new Promise<T>((promiseResolve) => {
        resolve = promiseResolve;
    });
    return { promise, resolve };
}

type XhrResult = { status: number; body: string };

class MockXMLHttpRequest {
    static results: XhrResult[] = [];
    static instances: MockXMLHttpRequest[] = [];

    status = 0;
    responseText = "";
    withCredentials = false;
    timeout = 0;
    upload = { onprogress: null as ((event: ProgressEvent) => void) | null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    ontimeout: (() => void) | null = null;
    onabort: (() => void) | null = null;
    url = "";

    constructor() {
        MockXMLHttpRequest.instances.push(this);
    }

    open(_method: string, url: string) {
        this.url = url;
    }

    setRequestHeader() {}

    send() {
        const result = MockXMLHttpRequest.results.shift();
        if (!result) throw new Error("Missing mock XHR result");
        this.status = result.status;
        this.responseText = result.body;
        queueMicrotask(() => this.onload?.());
    }

    abort() {
        this.onabort?.();
    }
}

function requestCount(fetchMock: ReturnType<typeof vi.fn>, suffix: string) {
    return fetchMock.mock.calls.filter(([input]) => String(input).endsWith(suffix)).length;
}

function installConcurrentFetch(refreshResponse: Promise<Response>) {
    const attempts = new Map<string, number>();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/auth/refresh")) return refreshResponse;
        const attempt = (attempts.get(url) ?? 0) + 1;
        attempts.set(url, attempt);
        if (attempt === 1) return Promise.resolve(new Response(null, { status: 401 }));
        if (url.endsWith("/events")) {
            return Promise.resolve(new Response("event: done\n\n", { status: 200 }));
        }
        return Promise.resolve(
            new Response(JSON.stringify({ ok: true }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        );
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

describe("shared refresh coordination", () => {
    beforeEach(() => {
        markAuthSessionActive();
        MockXMLHttpRequest.results = [];
        MockXMLHttpRequest.instances = [];
        vi.stubGlobal("XMLHttpRequest", MockXMLHttpRequest);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("single-flights concurrent fetch, upload, and SSE retries", async () => {
        const refresh = deferred<Response>();
        const fetchMock = installConcurrentFetch(refresh.promise);
        MockXMLHttpRequest.results = [
            { status: 401, body: "{}" },
            { status: 201, body: JSON.stringify({ uploaded: true }) },
        ];

        const jsonRequest = apiFetch<{ ok: boolean }>("/items");
        const streamRequest = apiFetchStream("/events");
        const uploadRequest = apiUpload<{ uploaded: boolean }>(
            "/upload",
            new FormData(),
        );

        await vi.waitFor(() => expect(requestCount(fetchMock, "/auth/refresh")).toBe(1));
        refresh.resolve(new Response(null, { status: 204 }));

        await expect(jsonRequest).resolves.toEqual({ ok: true });
        await expect(streamRequest).resolves.toBeInstanceOf(Response);
        await expect(uploadRequest).resolves.toEqual({ uploaded: true });
        expect(requestCount(fetchMock, "/auth/refresh")).toBe(1);
        expect(requestCount(fetchMock, "/items")).toBe(2);
        expect(requestCount(fetchMock, "/events")).toBe(2);
        expect(MockXMLHttpRequest.instances).toHaveLength(2);
    });

    it("lets an aborted waiter leave without cancelling the shared refresh", async () => {
        const refresh = deferred<Response>();
        const fetchMock = installConcurrentFetch(refresh.promise);
        const streamController = new AbortController();
        const uploadController = new AbortController();
        MockXMLHttpRequest.results = [{ status: 401, body: "{}" }];

        const eligibleRequest = apiFetch<{ ok: boolean }>("/items");
        const abortedStream = apiFetchStream("/events", { signal: streamController.signal });
        const abortedUpload = apiUpload("/upload", new FormData(), {
            signal: uploadController.signal,
        });

        await vi.waitFor(() => expect(requestCount(fetchMock, "/auth/refresh")).toBe(1));
        streamController.abort();
        uploadController.abort();
        await expect(abortedStream).rejects.toMatchObject({
            name: "ApiError",
            cancelled: true,
        } satisfies Partial<ApiError>);
        await expect(abortedUpload).rejects.toMatchObject({
            name: "ApiError",
            cancelled: true,
        } satisfies Partial<ApiError>);

        refresh.resolve(new Response(null, { status: 204 }));
        await expect(eligibleRequest).resolves.toEqual({ ok: true });
        expect(requestCount(fetchMock, "/events")).toBe(1);
        expect(requestCount(fetchMock, "/auth/refresh")).toBe(1);
        expect(MockXMLHttpRequest.instances).toHaveLength(1);
    });

    it("expires the session once when the shared refresh fails", async () => {
        const refresh = deferred<Response>();
        const fetchMock = installConcurrentFetch(refresh.promise);
        const sessionExpired = vi.fn();
        window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, sessionExpired);
        MockXMLHttpRequest.results = [{ status: 401, body: "{}" }];

        const requests = [
            apiFetch("/items"),
            apiFetchStream("/events"),
            apiUpload("/upload", new FormData()),
        ];
        await vi.waitFor(() => expect(requestCount(fetchMock, "/auth/refresh")).toBe(1));
        refresh.resolve(new Response(null, { status: 401 }));

        const results = await Promise.allSettled(requests);
        expect(results.every((result) => result.status === "rejected")).toBe(true);
        for (const result of results) {
            if (result.status === "rejected") {
                expect(result.reason).toMatchObject({ name: "ApiError", status: 401 });
            }
        }
        expect(sessionExpired).toHaveBeenCalledOnce();
        expect(requestCount(fetchMock, "/auth/refresh")).toBe(1);
        window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, sessionExpired);
    });

    it("does not retry queued callers after logout wins the race", async () => {
        const refresh = deferred<Response>();
        const fetchMock = installConcurrentFetch(refresh.promise);
        const first = apiFetch("/first");
        const second = apiFetchStream("/events");

        await vi.waitFor(() => expect(requestCount(fetchMock, "/auth/refresh")).toBe(1));
        beginAuthLogout();
        refresh.resolve(new Response(null, { status: 204 }));

        await expect(first).rejects.toMatchObject({ status: 401 });
        await expect(second).rejects.toMatchObject({ status: 401 });
        expect(requestCount(fetchMock, "/first")).toBe(1);
        expect(requestCount(fetchMock, "/events")).toBe(1);
    });
});
