// Real-browser interaction check of /admin/darius against the ISOLATED e2e stack only (13100 -> 18000 -> 18100).
// MODE=main : pagination, approve (desktop), reject (mobile emulation), suspend/resume, permissions.
// MODE=down : run with DARIUS stopped -> error states.  MODE=up : after DARIUS restarted -> recovery.
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire("C:/Users/dario/FlowCore/ship-it/frontend/package.json");
const { chromium } = require("playwright");

const BASE = "http://127.0.0.1:13100";
const API = "http://127.0.0.1:18000/api";
const OUT = "C:/Users/dario/FlowCore/ship-it/docs/evidence/cycle6/ui-flow";
fs.mkdirSync(OUT, { recursive: true });
const MODE = process.env.MODE || "main";
const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? "PASS" : "FAIL"} ${name} ${detail}`); };

async function token(email, password) {
  const r = await fetch(`${API}/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email, password }) });
  const j = await r.json();
  return j.access_token || j.token;
}
async function adminGet(tok, path) {
  const r = await fetch(`${API}${path}`, { headers: { authorization: `Bearer ${tok}` } });
  return { status: r.status, body: await r.json().catch(() => null) };
}
async function login(page, email, password) {
  await page.goto(`${BASE}/login`);
  await page.getByPlaceholder("E-mail").fill(email);
  await page.getByPlaceholder("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 });
}
const tab = (page, name) => page.getByRole("tab", { name });
const ADMIN = ["admin@example.com", "e2e-admin-pass-1"];

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const desktop = { viewport: { width: 1280, height: 900 }, timezoneId: "America/Sao_Paulo", locale: "pt-BR" };
const phone = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, timezoneId: "America/Sao_Paulo", locale: "pt-BR" };

try {
  if (MODE === "main") {
    const adminTok = await token(...ADMIN);
    check("admin login via API", !!adminTok);

    // ---- pagination (Tarefas)
    const ctx = await browser.newContext(desktop);
    const page = await ctx.newPage();
    await login(page, ...ADMIN);
    await page.goto(`${BASE}/admin/darius`);
    await tab(page, "Tarefas").click();
    const next = page.getByRole("button", { name: "PrÃ³xima" });
    await next.waitFor({ timeout: 30000 });
    // the Tarefas tab pages by 25 and shows "Ver <first 8 chars of id>"
    const firstTotal = (await adminGet(adminTok, "/admin/darius/tasks?limit=25&offset=0")).body;
    const second = (await adminGet(adminTok, "/admin/darius/tasks?limit=25&offset=25")).body;
    check("API pagination: total and disjoint pages", firstTotal.total >= 30 && second.items.length > 0 && !second.items.some((t) => firstTotal.items.some((f) => f.id === t.id)), `total=${firstTotal.total} next_offset=${firstTotal.next_offset}`);
    const shows = (txt, items) => items.every((t) => txt.includes(`Ver ${t.id.slice(0, 8)}`));
    const before = await page.locator("main").innerText();
    check("UI page 1 lists exactly the API's first 25", shows(before, firstTotal.items));
    await next.click();
    await page.waitForTimeout(1500);
    const after = await page.locator("main").innerText();
    check("UI PrÃ³xima shows the API's items 26-50", before !== after && shows(after, second.items) && !shows(after, firstTotal.items.slice(0, 3)));
    await page.screenshot({ path: `${OUT}/tarefas-pagina2.png` });
    await page.getByRole("button", { name: "Anterior" }).click();
    await page.waitForTimeout(1500);
    const back = await page.locator("main").innerText();
    check("UI Anterior returns to page 1", shows(back, firstTotal.items));
    // last page: PrÃ³xima disabled
    let guard = 0;
    while (await next.isEnabled() && guard++ < 10) { await next.click(); await page.waitForTimeout(900); }
    check("last page disables PrÃ³xima", !(await next.isEnabled()));

    // ---- approvals: approve on desktop
    await tab(page, "AprovaÃ§Ãµes").click();
    await page.waitForTimeout(1500);
    const approveBtns = page.getByRole("button", { name: /^Aprovar / });
    const n0 = await approveBtns.count();
    check("two tasks await approval", n0 >= 2, `count=${n0}`);
    const idA = (await approveBtns.nth(0).getAttribute("aria-label")).replace("Aprovar ", "");
    const idB = (await approveBtns.nth(1).getAttribute("aria-label")).replace("Aprovar ", "");
    await approveBtns.nth(0).click();
    check("confirmation required (nothing sent yet)", (await adminGet(adminTok, `/admin/darius/tasks/${idA}`)).body?.status === "PAUSED");
    await page.getByRole("group", { name: "Confirmar decisÃ£o" }).getByRole("button", { name: "Voltar" }).click();
    check("Voltar cancels without effect", (await adminGet(adminTok, `/admin/darius/tasks/${idA}`)).body?.status === "PAUSED");
    await approveBtns.nth(0).click();
    await page.getByRole("button", { name: "Confirmar" }).click();
    await page.getByText(new RegExp(`Tarefa ${idA} aprovada`)).waitFor({ timeout: 20000 });
    await page.waitForTimeout(2500);
    const stA = (await adminGet(adminTok, `/admin/darius/tasks/${idA}`)).body;
    check("approve: task left PAUSED in DARIUS", stA?.status !== "PAUSED", `status=${stA?.status}`);
    await page.screenshot({ path: `${OUT}/aprovada-desktop.png` });
    // a second approve of the same id must be refused by the backend (409), not retried
    const r409 = await fetch(`${API}/admin/darius/tasks/${idA}/approve`, { method: "POST", headers: { authorization: `Bearer ${adminTok}`, "content-type": "application/json" }, body: "{}" });
    check("re-approving a decided task is refused", r409.status >= 400 && r409.status < 500, `http=${r409.status}`);
    await ctx.close();

    // ---- reject on a real mobile emulation
    const mctx = await browser.newContext(phone);
    const m = await mctx.newPage();
    await login(m, ...ADMIN);
    await m.goto(`${BASE}/admin/darius`);
    await tab(m, "AprovaÃ§Ãµes").click();
    await m.getByRole("button", { name: `Rejeitar ${idB}` }).tap();
    await m.getByLabel("Motivo da rejeiÃ§Ã£o").fill("teste e2e: reprovado no celular");
    await m.screenshot({ path: `${OUT}/rejeitar-mobile-confirmacao.png` });
    await m.getByRole("button", { name: "Confirmar" }).tap();
    await m.getByText(new RegExp(`Tarefa ${idB} rejeitada`)).waitFor({ timeout: 20000 });
    await m.waitForTimeout(2500);
    const stB = (await adminGet(adminTok, `/admin/darius/tasks/${idB}`)).body;
    check("reject (mobile): task FAILED in DARIUS", stB?.status === "FAILED", `status=${stB?.status}`);
    const resB = await adminGet(adminTok, `/admin/darius/tasks/${idB}/result`);
    check("reject reason persisted", JSON.stringify(resB.body).includes("reprovado no celular"), `http=${resB.status}`);
    const de = await m.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
    check("no horizontal overflow on mobile AprovaÃ§Ãµes", de);

    // ---- suspension (desktop)
    const sctx = await browser.newContext(desktop);
    const s = await sctx.newPage();
    await login(s, ...ADMIN);
    await s.goto(`${BASE}/admin/darius`);
    await tab(s, "SuspensÃ£o").click();
    await s.getByRole("button", { name: "Suspender InstÃ¢ncia store" }).click();
    const confirmBtn = s.getByRole("group", { name: "Confirmar suspensÃ£o" }).getByRole("button", { name: "Confirmar" });
    check("Confirmar disabled without reason", await confirmBtn.isDisabled());
    await s.getByLabel("Motivo").fill("teste e2e de suspensao");
    await confirmBtn.click();
    await s.getByText(/AutomaÃ§Ã£o \(instÃ¢ncia store\) suspensa/).waitFor({ timeout: 20000 });
    let sus = (await adminGet(adminTok, "/admin/automation/suspension")).body;
    check("suspend persisted in backend", JSON.stringify(sus).includes("store") && JSON.stringify(sus).includes("teste e2e de suspensao"));
    await s.screenshot({ path: `${OUT}/suspensao-ativa.png` });
    await s.getByRole("button", { name: "Retomar InstÃ¢ncia store" }).click();
    await s.getByLabel("Motivo").fill("fim do teste e2e");
    await s.getByRole("group", { name: "Confirmar suspensÃ£o" }).getByRole("button", { name: "Confirmar" }).click();
    await s.getByText(/AutomaÃ§Ã£o \(instÃ¢ncia store\) retomada/).waitFor({ timeout: 20000 });
    sus = (await adminGet(adminTok, "/admin/automation/suspension")).body;
    check("resume persisted in backend", !(sus.suspended_instances || []).includes("store"));
    await sctx.close();

    // ---- permissions
    const uTok = await token("user@example.com", "e2e-user-pass-1");
    check("regular user logs in", !!uTok);
    for (const p of ["/admin/darius/status", "/admin/darius/metrics", "/admin/darius/tasks", "/admin/darius/paused-conversations", "/admin/automation/suspension"]) {
      const r = await adminGet(uTok, p);
      check(`regular user 403 on ${p}`, r.status === 403, `http=${r.status}`);
    }
    const w = await fetch(`${API}/admin/darius/tasks/${idA}/approve`, { method: "POST", headers: { authorization: `Bearer ${uTok}`, "content-type": "application/json" }, body: "{}" });
    check("regular user cannot approve (403)", w.status === 403, `http=${w.status}`);
    const un = await fetch(`${API}/admin/darius/status`);
    check("anonymous gets 401/403", [401, 403].includes(un.status), `http=${un.status}`);
    const uctx = await browser.newContext(desktop);
    const u = await uctx.newPage();
    await login(u, "user@example.com", "e2e-user-pass-1");
    await u.goto(`${BASE}/admin/darius`);
    await u.waitForTimeout(2500);
    const txt = await u.locator("body").innerText();
    check("regular user sees 'Acesso restrito' and no approve buttons", /Acesso restrito/.test(txt) && !/Aprovar /.test(txt));
    await u.screenshot({ path: `${OUT}/usuario-comum.png` });
    await uctx.close();
  } else {
    const ctx = await browser.newContext(desktop);
    const page = await ctx.newPage();
    await login(page, ...ADMIN);
    await page.goto(`${BASE}/admin/darius`);
    const panelText = async (name, until) => {
      await tab(page, name).click();
      // wait until the skeleton is gone and the panel has real text (never accept a still-loading panel)
      await page.waitForFunction(() => { const p = document.querySelector('[role="tabpanel"]:not([hidden])'); return p && p.innerText.trim().length > 20; }, null, { timeout: 60000 });
      await page.waitForTimeout(until);
      return page.locator('[role="tabpanel"]:not([hidden])').innerText();
    };
    const tm = await panelText("Métricas", 1500);
    await page.screenshot({ path: `${OUT}/metricas-${MODE}.png` });
    const tv = await panelText("Visão geral", 1500);
    await page.screenshot({ path: `${OUT}/visao-geral-${MODE}.png` });
    const ta = await panelText("Aprovações", 1500);
    await page.screenshot({ path: `${OUT}/aprovacoes-${MODE}.png` });
    const one = (s) => s.replace(/\s+/g, " ").slice(0, 220);
    if (MODE === "down") {
      check("Métricas: explicit unavailability, no figures", /unreachable|indispon|DARIUS/i.test(tm) && !/\b137\b/.test(tm), one(tm));
      check("Visão geral: no stale task numbers presented as current", !/\b137\b/.test(tv), one(tv));
      check("Aprovações: error/circuit message, no approve buttons", /unreachable|circuit|indispon|falh|erro/i.test(ta) && (await page.getByRole("button", { name: /^Aprovar / }).count()) === 0, one(ta));
    } else {
      check("Métricas: real figures are back (137 tasks) and no error text", /\b137\b/.test(tm) && !/unreachable|circuit open/i.test(tm), one(tm));
      check("Visão geral: recovered without reloading the page", !/unreachable|circuit open/i.test(tv), one(tv));
      check("Aprovações: recovered (no error text)", !/unreachable|circuit open/i.test(ta), one(ta));
    }
    await ctx.close();
  }} catch (e) {
  check("script completed without exception", false, String(e).slice(0, 300));
} finally {
  await browser.close();
  fs.writeFileSync(`${OUT}/results-${MODE}.json`, JSON.stringify(results, null, 1));
  console.log(`MODE=${MODE} passed=${results.filter((r) => r.ok).length} failed=${results.filter((r) => !r.ok).length}`);
}
