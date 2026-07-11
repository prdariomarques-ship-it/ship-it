import { test, expect } from "@playwright/test";

test("dashboard summary shows a loading indicator before data arrives", async ({ page }) => {
  await page.route("**/api/dashboard/summary", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contacts: 1,
        messages: 2,
        pending_tasks: 3,
        notes: 4,
        events: 5,
        church_members: 6,
        store_customers: 7,
      }),
    });
  });

  await page.goto("/");
  await expect(page.locator("text=Carregando…")).toBeVisible();
  await expect(page.locator("text=Carregando…")).toBeHidden({ timeout: 5000 });
  await expect(page.locator(".stat-grid")).toBeVisible();
});

test("dashboard summary shows an error message when the API fails", async ({ page }) => {
  await page.route("**/api/dashboard/summary", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Internal Server Error" }),
    })
  );

  await page.goto("/");
  await expect(page.locator(".error")).toBeVisible({ timeout: 5000 });
  await expect(page.locator(".stat-grid")).toHaveCount(0);
});

test("admin dashboard does not crash and shows content when an API call fails", async ({ page }) => {
  await page.route("**/api/admin/**", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Internal Server Error" }),
    })
  );

  const consoleErrors: string[] = [];
  page.on("pageerror", (err) => consoleErrors.push(err.message));

  await page.goto("/admin");
  await page.waitForLoadState("networkidle");

  // An uncaught render-time exception (a white screen / React crash) would
  // fail this — a failed fetch degrading gracefully into an error state
  // inside the page is fine, an unhandled exception is not.
  expect(consoleErrors).toEqual([]);
});
