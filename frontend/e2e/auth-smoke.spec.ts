import { expect, test, type Page } from "@playwright/test";

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
    enabled_modules: ["projects"],
    module_catalog: [],
    available_module_packs: [],
    mfa_enabled: false,
};

async function mockPublicShell(page: Page) {
    await page.route("**/api/v1/platform/metadata", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(metadata) })
    );
    await page.route("**/api/v1/auth/me", (route) =>
        route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Not authenticated" }) })
    );
    await page.route("**/api/v1/auth/refresh", (route) =>
        route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Session expired" }) })
    );
}

test.describe("authentication smoke flows", () => {
    test("signs in and navigates to the protected dashboard", async ({ page }) => {
        await mockPublicShell(page);
        await page.route("**/api/v1/auth/sign-in", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user }) })
        );

        await page.goto("/");
        await page.getByLabel("Email").first().fill(user.email);
        await page.getByLabel("Password").fill("Correct Horse Battery Staple!");
        await page.getByRole("button", { name: "Sign in", exact: true }).click();

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
        await page.getByLabel("New password").fill("Correct Horse Battery Staple!");
        await page.getByLabel("Confirm new password").fill("Correct Horse Battery Staple!");
        await page.getByRole("button", { name: "Reset password", exact: true }).click();

        await expect(page.getByText("Password reset successfully.")).toBeVisible();
        expect(submittedToken).toBe("e2e-reset-token");
    });

    test("redirects unauthenticated users away from protected routes", async ({ page }) => {
        await mockPublicShell(page);

        await page.goto("/dashboard");

        await expect(page).toHaveURL(/\/$/);
        await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    });
});
