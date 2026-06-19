import { describe, expect, it } from "vitest";

import { queryKeys } from "./queryKeys";

describe("queryKeys", () => {
    it("builds stable auth and user identity keys", () => {
        expect(queryKeys.auth.me).toEqual(["auth", "me"]);
        expect(queryKeys.users.me).toEqual(["users", "me"]);
        expect(queryKeys.users.profile).toEqual(["users", "profile"]);
        expect(queryKeys.users.sessions).toEqual(["users", "sessions"]);
    });

    it("builds stable notification keys", () => {
        expect(queryKeys.notifications.all).toEqual(["notifications"]);
        expect(queryKeys.notifications.preferences).toEqual(["notifications", "preferences"]);
    });

    it("builds stable ai keys", () => {
        expect(queryKeys.ai.overview).toEqual(["ai", "overview"]);
        expect(queryKeys.ai.promptVersions("tpl-1")).toEqual(["ai", "prompt-versions", "tpl-1"]);
    });

    it("builds parameterized project keys", () => {
        expect(queryKeys.projects.detail("abc")).toEqual(["projects", "abc"]);
        expect(queryKeys.projects.tasks("abc")).toEqual(["projects", "abc", "tasks"]);
    });

    it("builds stable admin keys", () => {
        expect(queryKeys.admin.all).toEqual(["admin"]);
        expect(queryKeys.admin.users(0, "alice")).toEqual(["admin", "users", 0, "alice"]);
    });

    it("builds stable platform keys", () => {
        expect(queryKeys.platform.plans).toEqual(["platform", "plans"]);
        expect(queryKeys.platform.subscription).toEqual(["platform", "subscription"]);
        expect(queryKeys.platform.apiKeys).toEqual(["platform", "api-keys"]);
        expect(queryKeys.platform.webhooks).toEqual(["platform", "webhooks"]);
        expect(queryKeys.platform.featureFlags).toEqual(["platform", "feature-flags"]);
    });
});
