const { chromium } = require('playwright');
const EXE = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(`[pageerror] ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`[console] ${m.text().slice(0, 160)}`); });

  const go = async (route) => { await page.goto(`http://127.0.0.1:3000${route}`, { waitUntil: 'networkidle', timeout: 60000 }); await page.waitForTimeout(1800); };
  const click = async (name, opts = {}) => {
    const el = page.getByRole('button', { name, ...opts }).first();
    await el.waitFor({ state: 'visible', timeout: 15000 });
    await el.click();
  };

  // --- BMS: inject a hot day, check detection ---
  await go('/bms/ai-operations');
  await click(/Hot Day/);
  await page.waitForTimeout(4000);
  await page.screenshot({ path: '/tmp/shots/flow-1-hotday.png', fullPage: true });
  const insightCount = await page.locator('article').count();
  console.log(`hot-day insights rendered: ${insightCount}`);

  // expand explanation + safety gate on the first recommendation, if present
  const hasRec = await page.getByText('AI RECOMMENDATION').first().isVisible().catch(() => false);
  console.log('recommendation present:', hasRec);
  if (hasRec) {
    await click(/View explanation/); await page.waitForTimeout(600);
    await click(/Run safety gate/); await page.waitForTimeout(2500);
    await page.screenshot({ path: '/tmp/shots/flow-2-recommendation.png', fullPage: true });
    const gate = await page.getByText(/Safety gate:/).first().innerText().catch(() => 'n/a');
    console.log('safety gate ->', gate);
  }

  // --- BMS Control Lab ---
  await go('/bms/control-lab');
  await page.screenshot({ path: '/tmp/shots/flow-3-controllab.png', fullPage: true });
  const labText = await page.locator('body').innerText();
  console.log('control lab has comparison:', labText.includes('Baseline vs AI control'));

  // --- EMS: EV surge -> optimise -> cross-module ---
  await go('/ems/scenario-lab');
  await click(/EV Charging Surge/);
  await page.waitForTimeout(3500);
  await page.screenshot({ path: '/tmp/shots/flow-4-evsurge.png', fullPage: true });
  const riskText = await page.getByText(/PREDICTED PEAK LOADING/i).first().locator('..').innerText().catch(() => 'n/a');
  console.log('risk panel ->', riskText.replace(/\n/g, ' | ').slice(0, 160));

  await click(/Run flexible-load optimisation/);
  await page.waitForTimeout(6000);
  await page.screenshot({ path: '/tmp/shots/flow-5-optimised.png', fullPage: true });
  const optText = await page.locator('body').innerText();
  console.log('optimisation rendered:', optText.includes('Verified by load flow'));

  await click(/Open BMS analysis/);
  await page.waitForTimeout(9000);
  await page.screenshot({ path: '/tmp/shots/flow-6-crossmodule.png', fullPage: true });
  const chainText = await page.locator('body').innerText();
  console.log('cross-module chain rendered:', chainText.includes('power risk to building action'));

  // --- provenance popover ---
  await go('/bms');
  const badge = page.locator('button[aria-label^="Provenance"]').first();
  await badge.click();
  await page.waitForTimeout(900);
  await page.screenshot({ path: '/tmp/shots/flow-7-provenance.png', clip: { x: 0, y: 200, width: 1100, height: 700 } });

  console.log('\n=== issues ===');
  console.log(errors.length ? [...new Set(errors)].join('\n') : 'none');
  await browser.close();
})();
