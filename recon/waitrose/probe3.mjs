import { chromium } from '/home/spellers/Projects/myapp/node_modules/playwright/index.mjs';
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--no-sandbox'] });
const page = await (await browser.newContext()).newPage();
const t0 = Date.now();
try {
  const resp = await page.goto('https://www.waitrose.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  console.log('status', resp && resp.status(), ((Date.now()-t0)/1000) + 's', JSON.stringify(await page.title()));
} catch (e) { console.log('ERR', e.message.split('\n')[0]); }
await browser.close();
