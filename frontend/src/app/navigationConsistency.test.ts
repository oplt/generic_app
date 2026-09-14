import { describe, expect, it } from "vitest";
import pageKeys from "./pageKeys.json";
import {
    PAGE_REGISTRY,
    REGISTERED_PAGE_KEYS,
    authPages,
    publicPages,
} from "./pageRegistry";

describe("page registry navigation consistency", () => {
    it("has unique page keys and unique non-param paths among static routes", () => {
        const keys = pageKeys as string[];
        expect(new Set(keys).size).toBe(keys.length);
        expect(REGISTERED_PAGE_KEYS).toEqual(expect.arrayContaining(keys));

        const staticPaths = Object.values(PAGE_REGISTRY)
            .map((page) => page.path)
            .filter((path) => !path.includes(":") && path !== "*");
        expect(new Set(staticPaths).size).toBe(staticPaths.length);
    });

    it("maps every registry entry to a lazy component and stable pageKey", () => {
        for (const key of REGISTERED_PAGE_KEYS) {
            const page = PAGE_REGISTRY[key];
            expect(page.pageKey).toBe(key);
            expect(typeof page.component).toBe("object");
            expect(page.path.startsWith("/") || page.path === "*").toBe(true);
        }
    });

    it("keeps public and auth page partitions disjoint", () => {
        const publicKeys = new Set(publicPages().map((page) => page.pageKey));
        const authKeys = new Set(authPages().map((page) => page.pageKey));
        for (const key of publicKeys) {
            expect(authKeys.has(key)).toBe(false);
        }
    });

    it("marks admin pages for nested requireAdmin routing", () => {
        const adminPages = authPages().filter((page) => page.admin);
        expect(adminPages.length).toBeGreaterThan(3);
        for (const page of adminPages) {
            expect(page.path.startsWith("/admin")).toBe(true);
        }
    });
});
