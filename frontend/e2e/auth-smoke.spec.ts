import { expect, test } from "@playwright/test";

import { expectSignInPage, fillSignInForm, submitSignInForm } from "./helpers/auth";

const user = {
    id: "e2e-user",
    email: "e2e@example.test",
    full_name: "E2E User",
    is_verified: true,
    is_admin: false,
    mfa_enabled: false,
};

const metadata = {
    app_name: "Generic App",
    core_domain_singular: "project",
    core_domain_plural: "projects",
    module_pack: "full_platform",
    enabled_modules: [],
    active_modules: ["projects", "ai", "rag", "chat"],
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
        {
            module_key: "chat",
            label: "Knowledge chat",
            path: "/knowledge-chat",
            group: "workspace",
            icon: "knowledge",
            required_permission: null,
            feature_flag: null,
        },
    ],
    module_routes: [],
    mfa_enabled: false,
};

async function mockPublicShell(page: import("@playwright/test").Page) {
    await page.route("**/api/v1/platform/metadata", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(metadata),
        })
    );
    await page.route("**/api/v1/auth/me", (route) =>
        route.fulfill({
            status: 401,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Not authenticated" }),
        })
    );
    await page.route("**/api/v1/auth/refresh", (route) =>
        route.fulfill({
            status: 401,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Session expired" }),
        })
    );
}

test.describe("authentication smoke flows", () => {
    test("signs in and navigates to the protected dashboard", async ({ page }) => {
        await mockPublicShell(page);
        await page.route("**/api/v1/auth/sign-in", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ user }),
            })
        );

        await page.goto("/");
        await fillSignInForm(page, user.email, "Correct Horse Battery Staple!");
        await submitSignInForm(page);

        await expect(page).toHaveURL(/\/dashboard$/);
    });

    test("submits password reset and shows completion state", async ({ page }) => {
        await mockPublicShell(page);
        let submittedToken = "";
        await page.route("**/api/v1/auth/reset-password", async (route) => {
            const request = route.request();
            const body = request.postDataJSON() as { token?: string };
            submittedToken = body.token ?? "";
            await route.fulfill({ status: 204 });
        });

        await page.goto("/reset-password?token=e2e-reset-token");
        // exact: true avoids matching "Confirm new password"
        await page.getByLabel("New password", { exact: true }).fill("Correct Horse Battery Staple!");
        await page
            .getByLabel("Confirm new password", { exact: true })
            .fill("Correct Horse Battery Staple!");
        await page.getByRole("button", { name: "Reset password", exact: true }).click();

        await expect(page.getByText("Password reset successfully.")).toBeVisible();
        expect(submittedToken).toBe("e2e-reset-token");
    });

    test("redirects unauthenticated users away from protected routes", async ({ page }) => {
        await mockPublicShell(page);

        await page.goto("/dashboard");

        await expect(page).toHaveURL(/\/$/);
        await expectSignInPage(page);
    });
});
