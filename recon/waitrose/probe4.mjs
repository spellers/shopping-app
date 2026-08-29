import { chromium } from '/home/spellers/Projects/myapp/node_modules/playwright/index.mjs';
const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--no-sandbox'] });
const ctx = await browser.newContext();
const page = await ctx.newPage();
const t0 = Date.now();
try {
  const resp = await page.goto('https://www.waitrose.com/api/graphql-prod/graph/live', { waitUntil: 'domcontentloaded', timeout: 20000 });
  console.log('api status', resp && resp.status(), ((Date.now()-t0)/1000) + 's');
} catch (e) { console.log('api ERR', e.message.split('\n')[0]); }
await browser.close();
