const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(`[console] ${m.text()}`); });
  page.on('pageerror', e => errors.push(`[pageerror] ${e.message}`));
  page.on('requestfailed', r => errors.push(`[reqfail] ${r.url()} ${r.failure()?.errorText}`));

  const routes = [
    ['home', '/'],
    ['bms-overview', '/bms'],
    ['bms-ai-ops', '/bms/ai-operations'],
    ['bms-control-lab', '/bms/control-lab'],
    ['ems-portfolio', '/ems'],
    ['ems-network', '/ems/network'],
    ['ems-scenario-lab', '/ems/scenario-lab'],
  ];
  for (const [name, route] of routes) {
    await page.goto(`http://127.0.0.1:3000${route}`, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `/tmp/shots/${name}.png`, fullPage: true });
    const text = await page.evaluate(() => document.body.innerText.slice(0, 400));
    console.log(`=== ${name} (${route})`);
    console.log(text.split('\n').filter(Boolean).slice(0, 12).join(' | '));
  }
  console.log('\n=== issues ===');
  console.log(errors.length ? [...new Set(errors)].join('\n') : 'none');
  await browser.close();
})();
