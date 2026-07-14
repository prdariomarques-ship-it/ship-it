import { chromium } from 'playwright';

const DASHBOARD_URL = 'http://localhost:3000';
const BACKEND_URL = 'http://localhost:8000';
const RUNTIME_URL = 'http://localhost:5000';

const pages_to_test = [
  '/',
  '/conversas',
  '/agenda',
  '/calendario',
  '/tarefas',
  '/loja',
  '/igreja',
  '/analytics',
  '/logs',
  '/configuracoes',
  '/admin',
];

async function validatePlatform() {
  let browser;
  const results = {
    timestamp: new Date().toISOString(),
    services: { backend: null, runtime: null, frontend: null },
    pages: {},
    browserConsoleErrors: [],
    networkErrors: [],
    networkRequests: [],
    issues: [],
    success: true
  };

  try {
    // ============================================================
    // 1. VALIDATE SERVICES
    // ============================================================
    console.log('\n═══════════════════════════════════════════════');
    console.log('1. VALIDATING SERVICES');
    console.log('═══════════════════════════════════════════════\n');

    // Backend
    try {
      const backendResp = await fetch(`${BACKEND_URL}/health`);
      results.services.backend = {
        status: backendResp.status,
        ok: backendResp.ok,
        data: await backendResp.json()
      };
      console.log(`✓ Backend: HTTP ${backendResp.status}`);
      if (!backendResp.ok) {
        results.issues.push(`Backend returned HTTP ${backendResp.status}`);
        results.success = false;
      }
    } catch (e) {
      results.services.backend = { error: e.message };
      console.log(`✗ Backend: ${e.message}`);
      results.issues.push(`Backend unreachable: ${e.message}`);
      results.success = false;
    }

    // Runtime
    try {
      const runtimeResp = await fetch(`${RUNTIME_URL}/health`);
      results.services.runtime = {
        status: runtimeResp.status,
        ok: runtimeResp.ok,
        data: await runtimeResp.json()
      };
      console.log(`✓ Runtime: HTTP ${runtimeResp.status}`);
      if (!runtimeResp.ok) {
        results.issues.push(`Runtime returned HTTP ${runtimeResp.status}`);
        results.success = false;
      }
    } catch (e) {
      results.services.runtime = { error: e.message };
      console.log(`✗ Runtime: ${e.message}`);
      results.issues.push(`Runtime unreachable: ${e.message}`);
      results.success = false;
    }

    // Frontend
    try {
      const frontendResp = await fetch(DASHBOARD_URL);
      results.services.frontend = {
        status: frontendResp.status,
        ok: frontendResp.ok,
        contentLength: (await frontendResp.text()).length
      };
      console.log(`✓ Frontend: HTTP ${frontendResp.status}`);
      if (!frontendResp.ok) {
        results.issues.push(`Frontend returned HTTP ${frontendResp.status}`);
        results.success = false;
      }
    } catch (e) {
      results.services.frontend = { error: e.message };
      console.log(`✗ Frontend: ${e.message}`);
      results.issues.push(`Frontend unreachable: ${e.message}`);
      results.success = false;
    }

    // ============================================================
    // 2. BROWSER VALIDATION
    // ============================================================
    console.log('\n═══════════════════════════════════════════════');
    console.log('2. BROWSER VALIDATION');
    console.log('═══════════════════════════════════════════════\n');

    browser = await chromium.launch({
      executablePath: '/opt/pw-browsers/chromium',
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const context = await browser.newContext();
    const page = await context.newPage();

    // Set up listeners for console messages and network errors
    page.on('console', msg => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        results.browserConsoleErrors.push({
          type: msg.type(),
          text: msg.text()
        });
      }
    });

    page.on('response', response => {
      results.networkRequests.push({
        url: response.url(),
        status: response.status(),
        ok: response.ok()
      });

      if (!response.ok() && response.status() >= 400) {
        results.networkErrors.push({
          url: response.url(),
          status: response.status()
        });
        results.issues.push(`Network error: ${response.status()} ${response.url()}`);
        results.success = false;
      }
    });

    // ============================================================
    // 3. TEST EACH PAGE
    // ============================================================
    console.log('Testing pages:\n');

    for (const pagePath of pages_to_test) {
      try {
        const url = `${DASHBOARD_URL}${pagePath}`;
        console.log(`  → ${pagePath}`);

        const response = await page.goto(url, {
          waitUntil: 'domcontentloaded',
          timeout: 10000
        });

        const status = response?.status() || 'unknown';
        const html = await page.content();
        const hasLoadingText = html.includes('Carregando') || html.includes('Loading');
        const pageTitle = await page.title();

        results.pages[pagePath] = {
          status: status,
          ok: status === 200,
          hasContent: html.length > 100,
          pageTitle: pageTitle,
          networkErrorsOnPage: results.networkErrors.filter(e => e.url.includes(pagePath)).length
        };

        if (status === 200) {
          console.log(`      ✓ HTTP 200, ${html.length} bytes`);
        } else {
          console.log(`      ✗ HTTP ${status}`);
          results.success = false;
        }

        // Wait a moment for any async content
        await page.waitForTimeout(500);

      } catch (error) {
        console.log(`      ✗ Error: ${error.message}`);
        results.pages[pagePath] = {
          status: 'error',
          error: error.message,
          ok: false
        };
        results.issues.push(`Page load failed: ${pagePath} - ${error.message}`);
        results.success = false;
      }
    }

    await context.close();

  } catch (error) {
    console.log(`\n✗ CRITICAL ERROR: ${error.message}`);
    results.issues.push(`Critical error: ${error.message}`);
    results.success = false;
  } finally {
    if (browser) {
      await browser.close();
    }
  }

  // ============================================================
  // 4. REPORT RESULTS
  // ============================================================
  console.log('\n═══════════════════════════════════════════════');
  console.log('3. VALIDATION RESULTS');
  console.log('═══════════════════════════════════════════════\n');

  console.log('SERVICES:');
  console.log(`  Backend:   ${results.services.backend?.ok ? '✓ OK' : '✗ FAILED'}`);
  console.log(`  Runtime:   ${results.services.runtime?.ok ? '✓ OK' : '✗ FAILED'}`);
  console.log(`  Frontend:  ${results.services.frontend?.ok ? '✓ OK' : '✗ FAILED'}`);

  console.log(`\nPAGES TESTED: ${Object.keys(results.pages).length}`);
  const pagesPassed = Object.values(results.pages).filter(p => p.ok).length;
  console.log(`  Passed: ${pagesPassed}/${Object.keys(results.pages).length}`);

  console.log(`\nNETWORK REQUESTS: ${results.networkRequests.length} total`);
  console.log(`  Errors: ${results.networkErrors.length}`);

  if (results.networkErrors.length > 0) {
    console.log('\n  Failed requests:');
    results.networkErrors.forEach(e => {
      console.log(`    - HTTP ${e.status}: ${e.url}`);
    });
  }

  console.log(`\nBROWSER CONSOLE ERRORS: ${results.browserConsoleErrors.length}`);
  if (results.browserConsoleErrors.length > 0) {
    results.browserConsoleErrors.forEach(e => {
      console.log(`  [${e.type}] ${e.text}`);
    });
  }

  if (results.issues.length > 0) {
    console.log(`\nISSUES FOUND: ${results.issues.length}`);
    results.issues.forEach((issue, i) => {
      console.log(`  ${i + 1}. ${issue}`);
    });
  }

  console.log(`\n═══════════════════════════════════════════════`);
  if (results.success) {
    console.log('✓ PLATFORM VALIDATION PASSED');
  } else {
    console.log('✗ PLATFORM VALIDATION FAILED');
  }
  console.log('═══════════════════════════════════════════════\n');

  console.log(JSON.stringify(results, null, 2));

  process.exit(results.success ? 0 : 1);
}

validatePlatform().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
