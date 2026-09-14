import { describe, expect, it } from "vitest";

import {
    parseDeveloperDiagnosticsHeader,
    publishDeveloperDiagnostics,
    DEVELOPER_DIAGNOSTICS_EVENT,
} from "./developerDiagnosticsEvents";

describe("developer diagnostics events", () => {
    it("parses a safe summary header", () => {
        const summary = parseDeveloperDiagnosticsHeader(
            JSON.stringify({
                method: "GET",
                path: "/api/v1/health/live",
                status_code: 200,
                duration_ms: 12.5,
                correlation_id: "c1",
                trace_id: null,
                sql_query_count: 0,
                db_duration_ms: 0,
                cache_hits: 1,
                cache_misses: 0,
                external_calls: [],
                celery_tasks: [],
                rag_stages: [],
                rag_retrieved_chunk_count: null,
            })
        );
        expect(summary?.cache_hits).toBe(1);
        expect(summary?.path).toBe("/api/v1/health/live");
    });

    it("ignores invalid headers", () => {
        expect(parseDeveloperDiagnosticsHeader("not-json")).toBeNull();
    });

    it("publishes a window event", () => {
        let seen: unknown = null;
        const handler = (event: Event) => {
            seen = (event as CustomEvent).detail;
        };
        window.addEventListener(DEVELOPER_DIAGNOSTICS_EVENT, handler);
        publishDeveloperDiagnostics({
            method: "GET",
            path: "/x",
            status_code: 200,
            duration_ms: 1,
            correlation_id: null,
            trace_id: null,
            sql_query_count: 0,
            db_duration_ms: 0,
            cache_hits: 0,
            cache_misses: 0,
            external_calls: [],
            celery_tasks: [],
            rag_stages: [],
            rag_retrieved_chunk_count: null,
        });
        window.removeEventListener(DEVELOPER_DIAGNOSTICS_EVENT, handler);
        expect(seen).toMatchObject({ path: "/x" });
    });
});
