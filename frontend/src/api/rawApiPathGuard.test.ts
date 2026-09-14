/**
 * Architectural guard: raw `/api/v1/...` path literals must not appear outside
 * approved transport / generated locations. Prefer Orval clients + thin wrappers.
 *
 * Allow-list is intentional; extend only with a documented exception (see
 * docs/frontend-api-contract.md).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const SRC_ROOT = join(import.meta.dirname, "..");
const REPO_FRONTEND_SRC = SRC_ROOT;

const ALLOWED_PREFIXES = ["generated/"];

const ALLOWED_FILES = new Set([
    "api/client.ts",
    "api/axiosClient.ts",
    "api/orvalMutator.ts",
    "api/orvalMutator.test.ts",
    "api/client.test.ts",
    "api/client.refresh.test.ts",
    "api/developerDiagnosticsEvents.test.ts",
    "api/rawApiPathGuard.test.ts",
    // Fixture values for Grafana query encoding — not API client contracts.
    "features/observability/urlBuilders.test.ts",
]);

const RAW_API_V1 = /\/api\/v1\//;

function walk(dir: string, out: string[] = []): string[] {
    for (const entry of readdirSync(dir)) {
        if (entry === "node_modules" || entry === "dist") continue;
        const full = join(dir, entry);
        const st = statSync(full);
        if (st.isDirectory()) {
            walk(full, out);
        } else if (/\.(ts|tsx)$/.test(entry)) {
            out.push(full);
        }
    }
    return out;
}

describe("OpenAPI contract convergence", () => {
    it("disallows raw /api/v1/ path literals outside the allow-list", () => {
        const offenders: string[] = [];
        for (const file of walk(REPO_FRONTEND_SRC)) {
            const rel = relative(REPO_FRONTEND_SRC, file).replaceAll("\\", "/");
            if (ALLOWED_PREFIXES.some((prefix) => rel.startsWith(prefix))) continue;
            if (ALLOWED_FILES.has(rel)) continue;
            const text = readFileSync(file, "utf8");
            if (RAW_API_V1.test(text)) {
                offenders.push(rel);
            }
        }
        expect(offenders, `Move contracts to generated OpenAPI or document an exception:\n${offenders.join("\n")}`).toEqual(
            []
        );
    });
});
