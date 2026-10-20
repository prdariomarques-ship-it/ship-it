// Real mobile viewport check of /admin/darius against the ISOLATED e2e stack (127.0.0.1:13100 -> 18000 -> 18100).
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire("C:/Users/dario/FlowCore/ship-it/frontend/package.json");
const { chromium, devices } = require("playwright");

const OUT = "C:/Users/dario/FlowCore/ship-it/docs/evidence/cycle6/mobile";
fs.mkdirSync(OUT, { recursive: true });
const BASE = "http://127.0.0.1:13100";
const profiles = {
  "iphone-390x844": { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true },
  "small-360x640": { viewport: { width: 360, height: 640 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};
const TABS = ["Vis\u00e3o geral", "Tarefas", "Aprova\u00e7\u00f5es", "M\u00e9tricas", "WhatsApp", "Conversas pausadas", "Telegram", "Suspens\u00e3o", "Logs"];
const report = [];

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
for (const [name, opts] of Object.entries(profiles)) {
  const ctx = await browser.newContext({ ...opts, timezoneId: "America/Sao_Paulo", locale: "pt-BR" });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.getByPlaceholder("E-mail").fill("admin@example.com");
  await page.getByPlaceholder("Senha").fill("e2e-admin-pass-1");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 });
  await page.goto(`${BASE}/admin/darius`);
  await page.getByRole("tab", { name: "Tarefas" }).waitFor({ timeout: 30000 });
  for (const tab of TABS) {
    await page.getByRole("tab", { name: tab }).click();
    await page.waitForTimeout(1500);
    const m = await page.evaluate(() => {
      const de = document.documentElement;
      const wide = [...document.querySelectorAll("main *")].filter((e) => {
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.right > de.clientWidth + 1;
      }).slice(0, 5).map((e) => `${e.tagName.toLowerCase()}.${String(e.className).slice(0, 40)}:${Math.round(e.getBoundingClientRect().right)}`);
      return { innerWidth: window.innerWidth, scrollWidth: de.scrollWidth, overflowX: de.scrollWidth > de.clientWidth + 1, wide };
    });
    const tabEl = await page.getByRole("tab", { name: tab }).boundingBox();
    const inView = !!tabEl && tabEl.x >= -1 && tabEl.x + tabEl.width <= m.innerWidth + 1;
    report.push({ profile: name, tab, ...m, tabFullyVisible: inView });
    await page.screenshot({ path: `${OUT}/${name}-${tab.replace(/\s+/g, "_").normalize("NFD").replace(/[^\w_-]/g, "")}.png`, fullPage: false });
  }
  // the suspension timestamp must now read local time (UTC-3), not UTC
  await page.getByRole("tab", { name: "Suspens\u00e3o" }).click();
  report.push({ profile: name, tab: "SuspensÃ£o-text", text: (await page.locator("main").innerText()).split("\n").filter((l) => /desde/).slice(0, 2) });
  await ctx.close();
}
await browser.close();
fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 1));
const bad = report.filter((r) => r.overflowX);
console.log(`checked ${report.length} entries; horizontal overflow on ${bad.length}`);
for (const r of report) console.log(JSON.stringify(r));

