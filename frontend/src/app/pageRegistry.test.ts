import { describe, expect, it } from "vitest";
import {
    assertPageRegistryComplete,
    PAGE_REGISTRY,
    REGISTERED_PAGE_KEYS,
} from "./pageRegistry";

describe("pageRegistry contract", () => {
    it("registers every page key from pageKeys.json", () => {
        expect(() => assertPageRegistryComplete()).not.toThrow();
        expect(REGISTERED_PAGE_KEYS.length).toBeGreaterThan(10);
        for (const key of REGISTERED_PAGE_KEYS) {
            expect(PAGE_REGISTRY[key]?.pageKey).toBe(key);
            expect(PAGE_REGISTRY[key]?.path).toBeTruthy();
        }
    });

    it("keeps module-gated pages distinct from shell/public pages", () => {
        expect(PAGE_REGISTRY["dashboard.main"].shell).toBe(true);
        expect(PAGE_REGISTRY["auth.home"].public).toBe(true);
        expect(PAGE_REGISTRY["chat.knowledge"].moduleKey).toBe("chat");
        expect(PAGE_REGISTRY["admin.users"].admin).toBe(true);
    });
});
