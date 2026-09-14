import { expect, type Locator, type Page } from "@playwright/test";

/** Sign-in form on `/` — scoped so mode-toggle "Sign in" is not confused with submit. */
export function signInForm(page: Page): Locator {
    return page.locator("form").filter({
        has: page.getByRole("button", { name: "Sign in", exact: true }),
    });
}

export async function fillSignInForm(
    page: Page,
    email: string,
    password: string
): Promise<void> {
    const form = signInForm(page);
    await form.getByLabel("Email", { exact: true }).fill(email);
    await form.getByLabel("Password", { exact: true }).fill(password);
}

export async function submitSignInForm(page: Page): Promise<void> {
    await signInForm(page).getByRole("button", { name: "Sign in", exact: true }).click();
}

export async function expectSignInPage(page: Page): Promise<void> {
    await expect(page.getByRole("heading", { name: "Welcome back", exact: true })).toBeVisible();
    await expect(
        signInForm(page).getByRole("button", { name: "Sign in", exact: true })
    ).toBeVisible();
}
