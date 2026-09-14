import { describe, expect, it } from "vitest";

import { getVisibleSettingsTabs } from "./useSettingsTabs";

const paths = (
    isAdmin: boolean,
    hasUserPlatformModule: boolean,
    hasAiModule: boolean,
    activeModules: string[] = []
) =>
    getVisibleSettingsTabs({
        isAdmin,
        hasUserPlatformModule,
        hasAiModule,
        activeModules: new Set(activeModules),
    }).map((tab) => tab.path);

describe("settings tab visibility", () => {
    it("keeps capability and admin tabs hidden for a basic user", () => {
        expect(paths(false, false, false)).toEqual(["/profile", "/observability"]);
    });

    it("shows capability tabs independently", () => {
        expect(paths(false, true, false)).toContain("/platform");
        expect(paths(false, false, true, ["ai"])).toContain("/ai");
    });

    it("shows all admin tabs only to admins when modules are active", () => {
        const adminPaths = paths(true, true, true, ["ai", "rag", "jobs", "diagnostics"]);
        expect(adminPaths).toEqual(
            expect.arrayContaining([
                "/admin/settings",
                "/admin/users",
                "/admin/rag-indexes",
                "/admin/rag/evaluation",
                "/admin/jobs",
                "/admin/diagnostics",
                "/admin/platform",
            ])
        );
        expect(paths(false, true, true, ["ai", "rag"]).some((path) => path.startsWith("/admin/"))).toBe(
            false
        );
    });

    it("hides RAG/jobs/diagnostics admin tabs when those modules are inactive", () => {
        const adminPaths = paths(true, true, false, []);
        expect(adminPaths).not.toContain("/admin/rag-indexes");
        expect(adminPaths).not.toContain("/admin/jobs");
        expect(adminPaths).not.toContain("/admin/diagnostics");
        expect(adminPaths).toContain("/admin/users");
    });
});
