import { test, expect } from "@playwright/test";

test("dashboard sidebar links are reachable and activatable via keyboard", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const firstLink = page.locator(".sidebar a").first();
  await firstLink.focus();
  await expect(firstLink).toBeFocused();

  const conversasLink = page.locator('.sidebar a[href="/conversas"]');
  await conversasLink.focus();
  await page.keyboard.press("Enter");
  await page.waitForURL("**/conversas");
  expect(page.url()).toContain("/conversas");
});

test("admin sidebar links are reachable via Tab and have visible focus", async ({ page }) => {
  await page.goto("/admin");
  await page.waitForLoadState("networkidle");

  const navLinks = page.locator("nav a");
  const count = await navLinks.count();
  expect(count).toBeGreaterThan(0);

  const firstNavLink = navLinks.first();
  await firstNavLink.focus();
  await expect(firstNavLink).toBeFocused();

  const outline = await firstNavLink.evaluate((el) => getComputedStyle(el).outlineStyle);
  // Either a visible outline or the browser's default focus ring must apply —
  // "none" with no replacement would mean keyboard users lose track of focus.
  expect(outline).not.toBe("none");
});
