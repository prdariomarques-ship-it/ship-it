import { defineConfig, devices } from "@playwright/test";

const CHROMIUM_EXECUTABLE = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  reporter: [["list"]],
  globalSetup: require.resolve("./e2e/global-setup"),
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_SKIP_EXECUTABLE_PATH ? undefined : CHROMIUM_EXECUTABLE,
    },
  },
  projects: [
    {
      name: "unauthenticated",
      testMatch: /login\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "authenticated",
      testIgnore: /login\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], storageState: "./e2e/.auth/admin.json" },
    },
  ],
});
