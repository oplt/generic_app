/**
 * Unit tests for OpenAPI path template normalization used by contract coverage.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function normalizeTemplate(path) {
  return path
    .replace(/\$\{[^}]+\}/g, "{}")
    .replace(/\{[^}]+\}/g, "{}")
    .replace(/\?.*$/, "")
    .replace(/\/+$/, "") || "/";
}

describe("api-contract-coverage helpers", () => {
  it("normalizes OpenAPI and Orval path templates to the same key", () => {
    assert.equal(
      normalizeTemplate("/api/v1/memory/{memory_id}"),
      normalizeTemplate("/api/v1/memory/${memoryId}")
    );
    assert.equal(
      normalizeTemplate("/api/v1/admin/jobs/{job_id}"),
      "/api/v1/admin/jobs/{}"
    );
  });

  it("intentional allow-list references real OpenAPI operations", () => {
    const spec = JSON.parse(readFileSync(join(root, "openapi/openapi.json"), "utf8"));
    const allow = JSON.parse(
      readFileSync(join(root, "openapi/intentional-api-only.json"), "utf8")
    );
    const known = new Set();
    for (const [path, methods] of Object.entries(spec.paths || {})) {
      for (const method of Object.keys(methods)) {
        if (["get", "post", "put", "patch", "delete"].includes(method)) {
          known.add(`${method.toUpperCase()} ${path}`);
        }
      }
    }
    for (const op of allow.operations || []) {
      assert.ok(known.has(op), `allow-list entry missing from OpenAPI: ${op}`);
    }
  });
});
