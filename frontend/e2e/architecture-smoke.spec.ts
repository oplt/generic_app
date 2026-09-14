import { expect, test, type Page } from "@playwright/test";

import { expectSignInPage, fillSignInForm, submitSignInForm } from "./helpers/auth";

const user = {
    id: "e2e-user",
    email: "e2e@example.test",
    full_name: "E2E User",
    is_verified: true,
    is_admin: false,
    mfa_enabled: false,
};

const adminUser = { ...user, id: "e2e-admin", email: "admin@example.test", is_admin: true };

const profile = {
    id: user.id,
    email: user.email,
    full_name: user.full_name,
    avatar_url: null,
    bio: null,
    timezone: "UTC",
    locale: "en",
};

function baseMetadata(overrides: Record<string, unknown> = {}) {
    return {
        app_name: "Generic App",
        core_domain_singular: "project",
        core_domain_plural: "projects",
        module_pack: "full_platform",
        enabled_modules: [],
        active_modules: ["projects", "ai", "rag", "chat", "admin", "platform", "settings"],
        module_catalog: [],
        available_module_packs: [],
        module_nav: [
            {
                module_key: "projects",
                label: "Projects",
                path: "/projects",
                group: "workspace",
                icon: "projects",
                required_permission: null,
                feature_flag: null,
            },
        ],
        module_routes: [
            { page_key: "dashboard.main", path: "/dashboard" },
            { page_key: "projects.list", path: "/projects" },
            { page_key: "ai.studio", path: "/ai" },
            { page_key: "admin.users", path: "/admin/users" },
            { page_key: "profile.settings", path: "/profile" },
            { page_key: "platform.workspace", path: "/platform" },
        ],
        mfa_enabled: false,
        ...overrides,
    };
}

/** Shared shell mocks — keep AppLayout from 401-ing and clearing the session. */
async function mockShellApis(
    page: Page,
    options: {
        metadata?: Record<string, unknown>;
        who?: typeof user | null;
    } = {}
) {
    const metadata = options.metadata ?? baseMetadata();
    const who = options.who === undefined ? null : options.who;

    await page.route("**/api/v1/platform/metadata", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(metadata),
        })
    );

    await page.route("**/api/v1/auth/me", (route) => {
        if (!who) {
            return route.fulfill({
                status: 401,
                contentType: "application/json",
                body: JSON.stringify({ detail: "Not authenticated" }),
            });
        }
        // Backend returns AuthUserResponse directly (not wrapped).
        return route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(who),
        });
    });

    await page.route("**/api/v1/auth/refresh", (route) => {
        if (!who) {
            return route.fulfill({
                status: 401,
                contentType: "application/json",
                body: JSON.stringify({ detail: "Session expired" }),
            });
        }
        return route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ user: who }),
        });
    });

    await page.route("**/api/v1/auth/logout", (route) => route.fulfill({ status: 204 }));

    await page.route("**/api/v1/profile**", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ...profile,
                id: who?.id ?? profile.id,
                email: who?.email ?? profile.email,
                full_name: who?.full_name ?? profile.full_name,
            }),
        })
    );

    await page.route("**/api/v1/notifications**", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], total: 0, limit: 20, offset: 0, unread_count: 0 }),
        })
    );

    await page.route("**/api/v1/projects**", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }),
        })
    );
}

async function signInAs(page: Page, who: typeof user) {
    await page.route("**/api/v1/auth/sign-in", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ user: who }),
        })
    );
    await page.goto("/");
    await fillSignInForm(page, who.email, "Correct Horse Battery Staple!");
    await submitSignInForm(page);
    await expect(page).toHaveURL(/\/dashboard$/);
}

/** Prefer cookie-less “already authenticated” entry for hard navigations. */
async function enterAuthenticated(page: Page, who: typeof user, metadata?: Record<string, unknown>) {
    await mockShellApis(page, { who, metadata });
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/dashboard$/);
}

test.describe("architecture smoke (mocked)", () => {
    test("persists session via refresh then auth/me", async ({ page }) => {
        let meCalls = 0;
        await mockShellApis(page, { who: user });
        await page.unroute("**/api/v1/auth/me");
        await page.route("**/api/v1/auth/me", (route) => {
            meCalls += 1;
            return route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(user),
            });
        });

        await page.goto("/dashboard");
        await expect(page).toHaveURL(/\/dashboard$/);
        expect(meCalls).toBeGreaterThan(0);
    });

    test("loads projects path after sign-in", async ({ page }) => {
        await mockShellApis(page, { who: null });
        await signInAs(page, user);
        await mockShellApis(page, { who: user });
        await page.goto("/projects");
        await expect(page).toHaveURL(/\/projects$/);
        await expect(page.locator("main")).toBeVisible();
    });

    test("blocks non-admin from admin users", async ({ page }) => {
        await enterAuthenticated(page, user);
        await page.goto("/admin/users");
        await expect(page).toHaveURL(/\/dashboard$/);
    });

    test("allows admin users path for admins", async ({ page }) => {
        await enterAuthenticated(page, adminUser);
        await page.route("**/api/v1/admin/users**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
            })
        );
        await page.goto("/admin/users");
        await expect(page).toHaveURL(/\/admin\/users$/);
    });

    test("core profile gates AI studio as not found", async ({ page }) => {
        await enterAuthenticated(
            page,
            user,
            baseMetadata({
                module_pack: "core",
                active_modules: ["projects"],
                module_routes: [
                    { page_key: "dashboard.main", path: "/dashboard" },
                    { page_key: "projects.list", path: "/projects" },
                ],
            })
        );
        await page.goto("/ai");
        await expect(page.getByText("Page not found")).toBeVisible();
    });

    test("rag-enabled profile allows AI studio route key", async ({ page }) => {
        await enterAuthenticated(
            page,
            user,
            baseMetadata({
                module_pack: "rag",
                active_modules: ["projects", "ai", "rag"],
            })
        );
        await page.route("**/api/v1/ai/**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                    providers: [],
                    prompt_templates: [],
                    recent_runs: [],
                    documents: [],
                    datasets: [],
                    prompt_templates_count: 0,
                    recent_runs_count: 0,
                    documents_count: 0,
                    datasets_count: 0,
                }),
            })
        );
        await page.goto("/ai");
        await expect(page).toHaveURL(/\/ai$/);
        await expect(page.getByText("Page not found")).toHaveCount(0);
    });

    test("unknown path shows not-found", async ({ page }) => {
        await enterAuthenticated(page, user);
        await page.goto("/this-route-does-not-exist-e2e");
        await expect(page.getByText("Page not found")).toBeVisible();
    });

    test("logout returns to sign-in", async ({ page }) => {
        await enterAuthenticated(page, user);

        let signedOut = false;
        await page.unroute("**/api/v1/auth/me");
        await page.route("**/api/v1/auth/me", (route) => {
            if (signedOut) {
                return route.fulfill({
                    status: 401,
                    contentType: "application/json",
                    body: JSON.stringify({ detail: "Not authenticated" }),
                });
            }
            return route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(user),
            });
        });
        await page.unroute("**/api/v1/auth/logout");
        await page.route("**/api/v1/auth/logout", async (route) => {
            signedOut = true;
            await route.fulfill({ status: 204 });
        });

        await expect(page).toHaveURL(/\/dashboard$/);
        await page.getByRole("button", { name: /sign out/i }).click();
        await expect(page).toHaveURL(/\/$/);
        await expectSignInPage(page);
    });
});
