const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  const p = await (await b.newContext({viewport:{width:1600,height:1100}})).newPage();
  await p.goto('http://127.0.0.1:3000/bms/ai-operations', { waitUntil: 'networkidle' });
  await p.waitForTimeout(3000);
  const buttons = await p.locator('button').allInnerTexts();
  console.log('buttons:', JSON.stringify(buttons.filter(Boolean).slice(0, 30)));
  console.log('body head:', (await p.locator('body').innerText()).slice(0, 500).replace(/\n+/g,' | '));
  await b.close();
})();
