// E2E do painel em navegador real (Chromium headless). Requer o serviço no ar com motor SIMULADO e: PLAYWRIGHT_MODULE, CHROMIUM_PATH, PANEL_TOKEN (e opcional PANEL_URL).
// Uso: node scripts/e2e_painel.cjs captura.png
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox'] });
  const page = await b.newPage();
  const errors = []; page.on('pageerror', e => errors.push(String(e))); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto((process.env.PANEL_URL || 'http://127.0.0.1:18791') + '/panel');
  await page.fill('#token', 'errado'.padEnd(40, 'x')); await page.click('#connectBtn');
  await page.waitForFunction(() => document.getElementById('connectMsg').textContent.includes('recusado'));
  console.log('token errado ->', await page.textContent('#connectMsg'), '| painel oculto:', await page.isHidden('#panel'));
  await page.fill('#token', process.env.PANEL_TOKEN); await page.click('#connectBtn');
  await page.waitForSelector('#modeBanner:visible');
  console.log('banner ->', await page.textContent('#modeBanner'));
  console.log('checklist ->', (await page.$$eval('#checklist li', l => l.map(x => x.textContent))).join(' | '));
  console.log('campo do token vazio após conectar:', (await page.inputValue('#token')) === '');
  await page.click('#synthBtn');
  await page.waitForSelector('#player:visible', { timeout: 15000 });
  console.log('rótulo do áudio ->', await page.textContent('#synthLabel'));
  const info = await page.evaluate(async () => { const p = document.getElementById('player'); await new Promise(r => p.readyState >= 1 ? r() : p.addEventListener('loadedmetadata', r)); return { src: p.src.slice(0, 5), duration: p.duration }; });
  console.log('player ->', JSON.stringify(info));
  await page.waitForFunction(() => document.querySelectorAll('#recent tr').length >= 1, null, { timeout: 8000 });
  console.log('recentes ->', (await page.$$eval('#recent tr', r => r.map(x => x.textContent))).join(' // '));
  console.log('stored/ttl ->', await page.textContent('#queue'));
  console.log('erros de página:', JSON.stringify(errors));
  await page.screenshot({ path: process.argv[2], fullPage: true });
  await b.close();
})().catch(e => { console.error('FALHA', e); process.exit(1); });
