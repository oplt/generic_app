import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(__dirname, "../..");

const orchestrationViews = [
    "src/features/admin-rag/views/AdminRagEvaluationView.tsx",
    "src/features/admin-rag/views/AdminRagIndexesView.tsx",
    "src/features/admin-users/views/AdminUsersView.tsx",
    "src/features/admin-jobs/views/AdminJobsView.tsx",
    "src/features/admin-diagnostics/views/AdminDiagnosticsView.tsx",
] as const;

describe("admin view orchestration", () => {
    it.each(orchestrationViews)("%s stays orchestration-only (no useMutation)", (relativePath) => {
        const source = readFileSync(resolve(root, relativePath), "utf8");
        expect(source).not.toMatch(/\buseMutation\b/);
        expect(source).toMatch(/\bPageShell\b/);
    });

    it("RAG evaluation view wires tabs without embedding candidate tables", () => {
        const source = readFileSync(
            resolve(root, "src/features/admin-rag/views/AdminRagEvaluationView.tsx"),
            "utf8"
        );
        expect(source).toMatch(/ProbePanel/);
        expect(source).toMatch(/DatasetsCasesPanel/);
        expect(source).toMatch(/RunsPanel/);
        expect(source).not.toMatch(/CandidateTable/);
    });
});
