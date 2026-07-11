import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const PAGES = ["/", "/conversas", "/admin"];

for (const path of PAGES) {
  test(`accessibility: ${path} has no serious or critical axe violations`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const seriousOrCritical = results.violations.filter(
      (violation) => violation.impact === "serious" || violation.impact === "critical"
    );

    if (seriousOrCritical.length > 0) {
      console.log(
        `${path} axe violations:`,
        JSON.stringify(seriousOrCritical.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })), null, 2)
      );
    }
    expect(seriousOrCritical).toEqual([]);
  });
}
