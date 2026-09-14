import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import { clearUserScopedQueryState, queryKeys } from "./queryKeys";

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
        expect(queryKeys.platform.admin.config).toEqual(["platform", "admin", "config"]);
        expect(queryKeys.platform.admin.plans).toEqual(["platform", "admin", "plans"]);
        expect(queryKeys.platform.admin.featureFlags).toEqual([
            "platform",
            "admin",
            "feature-flags",
        ]);
        expect(queryKeys.platform.admin.emailTemplates).toEqual([
            "platform",
            "admin",
            "email-templates",
        ]);
    });

    it("builds stable settings and observability keys", () => {
        expect(queryKeys.settings.config).toEqual(["settings", "config"]);
        expect(queryKeys.settings.database).toEqual(["settings", "database"]);
        expect(queryKeys.observability.links).toEqual(["observability", "links"]);
        expect(queryKeys.observability.status).toEqual(["observability", "status"]);
    });

    it("clears user-scoped cache while preserving auth state", async () => {
        const client = new QueryClient();
        client.setQueryData(queryKeys.auth.me, { id: "user-a" });
        client.setQueryData(queryKeys.projects.all, [{ id: "private-project" }]);
        client.setQueryData(queryKeys.notifications.all, [{ id: "private-notification" }]);

        await clearUserScopedQueryState(client);

        expect(client.getQueryData(queryKeys.auth.me)).toEqual({ id: "user-a" });
        expect(client.getQueryData(queryKeys.projects.all)).toBeUndefined();
        expect(client.getQueryData(queryKeys.notifications.all)).toBeUndefined();
    });
});
