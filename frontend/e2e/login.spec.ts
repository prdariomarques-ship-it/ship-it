import { test, expect } from "@playwright/test";

const TEST_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "e2e-admin@example.com";
const TEST_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "E2ePassw0rd!";

test.describe("Login", () => {
  test("real credentials log the user in and redirect away from /login", async ({ page }) => {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill(TEST_EMAIL);
    await page.locator('input[type="password"]').fill(TEST_PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15000 });
    expect(page.url()).not.toContain("/login");
  });

  test("wrong credentials show an inline error and stay on /login", async ({ page }) => {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill("e2e-admin@example.com");
    await page.locator('input[type="password"]').fill("wrong-password");
    await page.locator('button[type="submit"]').click();
    await expect(page.locator(".error")).toBeVisible({ timeout: 10000 });
    expect(page.url()).toContain("/login");
  });

  test("login form is keyboard-navigable end to end", async ({ page }) => {
    await page.goto("/login");
    await page.locator('input[type="email"]').focus();
    await expect(page.locator('input[type="email"]')).toBeFocused();
    await page.keyboard.type(TEST_EMAIL);
    await page.keyboard.press("Tab");
    await expect(page.locator('input[type="password"]')).toBeFocused();
    await page.keyboard.type(TEST_PASSWORD);
    await page.keyboard.press("Tab");
    await expect(page.locator('button[type="submit"]')).toBeFocused();
    await page.keyboard.press("Enter");
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 15000 });
  });
});
