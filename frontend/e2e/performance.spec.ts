import { test, expect } from "@playwright/test";

const PAGES = ["/", "/conversas", "/admin"];

for (const path of PAGES) {
  test(`${path} loads with no console errors and under 5s`, async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    const start = Date.now();
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const elapsed = Date.now() - start;

    expect(elapsed).toBeLessThan(5000);
    expect(consoleErrors).toEqual([]);
  });
}
