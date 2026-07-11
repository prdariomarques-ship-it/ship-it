import { test, expect } from "@playwright/test";

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 },
];

const PAGES = ["/", "/conversas", "/admin"];

for (const viewport of VIEWPORTS) {
  test.describe(`Responsividade @ ${viewport.name} (${viewport.width}px)`, () => {
    for (const path of PAGES) {
      test(`${path} has no horizontal overflow`, async ({ page }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto(path);
        await page.waitForLoadState("networkidle");

        const { scrollWidth, clientWidth } = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));

        // A small tolerance absorbs sub-pixel rounding from scrollbars.
        expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2);
      });
    }
  });
}
