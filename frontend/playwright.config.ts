import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const runProvisioned = ["1", "true", "yes"].includes(
    (process.env.E2E_PROVISIONED ?? "").toLowerCase()
);

/** Declared browsers. Default is Chromium only; install with `npm run test:e2e:install`. */
const browserNames = (process.env.E2E_BROWSERS ?? "chromium")
    .split(",")
    .map((name) => name.trim().toLowerCase())
    .filter(Boolean);

const deviceByBrowser: Record<string, (typeof devices)[string]> = {
    chromium: devices["Desktop Chrome"],
    firefox: devices["Desktop Firefox"],
    webkit: devices["Desktop Safari"],
};

const projects = browserNames.map((name) => {
    const device = deviceByBrowser[name];
    if (!device) {
        throw new Error(
            `Unknown E2E_BROWSERS entry "${name}". Use chromium, firefox, and/or webkit.`
        );
    }
    return { name, use: { ...device } };
});

export default defineConfig({
    testDir: "./e2e",
    fullyParallel: true,
    retries: process.env.CI ? 2 : 0,
    reporter: process.env.CI ? "github" : "html",
    timeout: 60_000,
    // Mocked smoke is the default suite. Credential-backed flows opt in with E2E_PROVISIONED=1.
    grep: runProvisioned ? /@provisioned/ : undefined,
    grepInvert: runProvisioned ? undefined : /@provisioned/,
    use: {
        baseURL,
        trace: "on-first-retry",
    },
    projects,
    webServer: process.env.E2E_BASE_URL
        ? undefined
        : {
              command: "npm run dev",
              url: baseURL,
              reuseExistingServer: !process.env.CI,
          },
});
