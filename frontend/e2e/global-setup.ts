import { chromium, type FullConfig } from "@playwright/test";
import path from "path";

const CHROMIUM_EXECUTABLE = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const TEST_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "e2e-admin@example.com";
const TEST_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "E2ePassw0rd!";

export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:3000";
  const browser = await chromium.launch({ executablePath: CHROMIUM_EXECUTABLE });
  const page = await browser.newPage({ baseURL });

  await page.goto("/login");
  await page.locator('input[type="email"]').fill(TEST_EMAIL);
  await page.locator('input[type="password"]').fill(TEST_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15000 });

  await page.context().storageState({ path: path.join(__dirname, ".auth", "admin.json") });
  await browser.close();
}
