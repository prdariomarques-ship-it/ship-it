// Timezone validation: persisted value (PostgreSQL, server tz Asia/Tokyo) -> API value -> value shown in the UI (browser tz America/Sao_Paulo).
// The UI at 13100 is served by the isolated Next, but its API calls are re-routed to the PostgreSQL-backed backend on 18001.
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
const require = createRequire("C:/Users/dario/FlowCore/ship-it/frontend/package.json");
const { chromium } = require("playwright");
const BASE = "http://127.0.0.1:13100", API = "http://127.0.0.1:18001/api";
const OUT = "C:/Users/dario/FlowCore/ship-it/docs/evidence/cycle6/timezone";
fs.mkdirSync(OUT, { recursive: true });
const rows = [], log = [];
const rec = (r) => { rows.push(r); console.log(JSON.stringify(r)); };
const psql = (sql) => execFileSync("docker", ["exec", "c6-pg-tz", "psql", "-U", "postgres", "-d", "c6", "-tAF", "|", "-c", sql], { encoding: "utf8" }).trim();
const ms = (iso) => new Date(iso).getTime();
const pgInstant = (s) => ms(s.replace(" ", "T").replace(/\+00$/, "Z").replace(/([+-]\d\d)$/, "$1:00"));

const login = await (await fetch(`${API}/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: "admin@example.com", password: "e2e-admin-pass-1" }) })).json();
const tok = login.access_token;
const H = { authorization: `Bearer ${tok}` };
const get = async (p) => (await fetch(`${API}${p}`, { headers: H })).json();

// make sure a suspension row exists to compare
await fetch(`${API}/admin/automation/suspension/instances/store`, { method: "PUT", headers: { ...H, "content-type": "application/json" }, body: JSON.stringify({ suspended: true, reason: "teste tz postgres" }) });

const server = psql("show timezone");
log.push(`postgres server timezone: ${server}`);

// ---- 1) WhatsApp links (darius_whatsapp_tasks.created_at)
const db1 = psql("select id, created_at::text, to_char(created_at at time zone 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US') from darius_whatsapp_tasks order by id limit 1").split("|");
const wa = await get("/admin/darius/whatsapp-tasks?limit=50");
const item = (wa.items || wa).find((x) => String(x.id) === db1[0]);
// ---- 2) paused conversation
const tbl = "conversation_control_audit.created_at"; let db2 = true;
const pc = await get("/admin/darius/paused-conversations");
const pitems = pc.items || pc;
// ---- 3) suspension
const db3 = psql("select created_at::text, to_char(created_at at time zone 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US') from automation_suspensions where scope='instance:store' limit 1").split("|");
const sus = await get("/admin/automation/suspension");

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, timezoneId: "America/Sao_Paulo", locale: "pt-BR" });
const page = await ctx.newPage();
const CORS = { "access-control-allow-origin": BASE, "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS", "access-control-allow-credentials": "true" };
await page.route("http://127.0.0.1:18000/api/**", async (route) => {
  const req = route.request();
  if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
  const url = req.url().replace("127.0.0.1:18000", "127.0.0.1:18001");
  const r = await fetch(url, { method: req.method(), headers: Object.fromEntries(Object.entries(req.headers()).filter(([k]) => !["host", "origin", "referer", "content-length"].includes(k))), body: ["GET", "HEAD"].includes(req.method()) ? undefined : req.postData() });
  return route.fulfill({ status: r.status, headers: { ...CORS, "content-type": r.headers.get("content-type") || "application/json" }, body: Buffer.from(await r.arrayBuffer()) });
});
await page.goto(`${BASE}/login`);
await page.getByPlaceholder("E-mail").fill("admin@example.com");
await page.getByPlaceholder("Senha").fill("e2e-admin-pass-1");
await page.getByRole("button", { name: "Entrar" }).click();
await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 });
await page.goto(`${BASE}/admin/darius`);
const shown = async (tabName, iso) => {
  await page.getByRole("tab", { name: tabName }).click();
  await page.waitForFunction(() => { const p = document.querySelector('[role="tabpanel"]:not([hidden])'); return p && p.innerText.trim().length > 20; }, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  const expected = await page.evaluate((v) => new Date(v).toLocaleString("pt-BR"), iso);
  const text = await page.locator('[role="tabpanel"]:not([hidden])').innerText();
  await page.screenshot({ path: `${OUT}/${tabName.replace(/\s+/g, "_").normalize("NFD").replace(/[^\w_-]/g, "")}.png` });
  return { expected, found: text.includes(expected) };
};

if (item) {
  const apiIso = item.created_at;
  const ui = await shown("WhatsApp", apiIso);
  rec({ field: "darius_whatsapp_tasks.created_at", persisted_pg_session_tz_tokyo: db1[1], persisted_utc: db1[2], api: apiIso,
        api_equals_persisted_instant: Math.abs(ms(apiIso) - ms(db1[2] + "Z")) < 2, api_has_offset: /(Z|[+-]\d\d:\d\d)$/.test(apiIso), ui_expected_brt: ui.expected, ui_shows_it: ui.found });
} else rec({ field: "darius_whatsapp_tasks.created_at", error: "row not found in API listing", id: db1[0] });

if (pitems.length) {
  const p = pitems.slice().sort((a, b) => ms(a.paused_since) - ms(b.paused_since))[0];
  const row = psql(`select created_at::text, to_char(created_at at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US') from conversation_control_audit where created_at = '${p.paused_since}'::timestamptz limit 1`).split("|");
  const ui = await shown("Conversas pausadas", p.paused_since);
  rec({ field: tbl + " (paused_since)", persisted_pg_session_tz_tokyo: row[0], persisted_utc: row[1], api: p.paused_since,
        api_equals_persisted_instant: !!row[1] && Math.abs(ms(p.paused_since) - ms(row[1] + "Z")) < 2, api_has_offset: /(Z|[+-]\d\d:\d\d)$/.test(p.paused_since), ui_expected_brt: ui.expected, ui_shows_it: ui.found });
} else rec({ field: "paused conversation", error: "no paused conversations in API" });

const det = (sus.details || sus.suspensions || []).find((d) => String(d.scope || d.key || "").includes("store")) || {};
const sinceIso = det.since;
if (sinceIso) {
  const ui = await shown("Suspensão", sinceIso);
  rec({ field: "automation_suspensions (since)", persisted_pg_session_tz_tokyo: db3[0], persisted_utc: db3[1], api: sinceIso,
        api_equals_persisted_instant: Math.abs(ms(sinceIso) - ms(db3[1] + "Z")) < 2, api_has_offset: /(Z|[+-]\d\d:\d\d)$/.test(sinceIso), ui_expected_brt: ui.expected, ui_shows_it: ui.found });
} else rec({ field: "automation_suspensions (since)", error: "since missing in API", api: JSON.stringify(sus).slice(0, 300) });

await browser.close();
fs.writeFileSync(`${OUT}/pg-timezone-results.json`, JSON.stringify({ log, rows }, null, 1));
const bad = rows.filter((r) => r.error || r.api_equals_persisted_instant === false || r.api_equals_persisted_instant_within_1s === false || r.api_has_offset === false || r.ui_shows_it === false);
console.log(`rows=${rows.length} problems=${bad.length}`);
