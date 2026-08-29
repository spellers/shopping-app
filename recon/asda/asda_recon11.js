// Phase 11: full SSR document capture + fetch/XHR interception.
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon11] ${m}`);
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: true,
  viewport: { width: 1360, height: 900 }, locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"], ignoreDefaultArgs: ["--enable-automation"],
});
await ctx.addInitScript(() => { Object.defineProperty(navigator, "webdriver", { get: () => undefined }); });
const page = ctx.pages()[0] ?? (await ctx.newPage());
const calls = [];
await page.exposeBinding("__pw_logFetch", async (_src, url, opts) => { calls.push({ url, opts: String(opts).slice(0, 1500) }); return ""; });
await page.addInitScript(() => {
  const of = window.fetch;
  window.fetch = function (input, opts) {
    try { window.__pw_logFetch?.(String(input?.url ?? input), opts ? { method: opts.method, body: String(opts.body).slice(0, 1000) } : null); } catch {}
    return of.apply(this, arguments);
  };
  const ox = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; this.__m = m; return ox.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) { try { window.__pw_logFetch?.(this.__u, { xhr: 1, method: this.__m, body: b ? String(b).slice(0, 1000) : null }); } catch {}; return os.apply(this, arguments); };
});
await page.goto("https://www.asda.com/groceries/search/milk", { waitUntil: "domcontentloaded", timeout: 60000 });
const d = Date.now() + 120000;
while (Date.now() < d) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await page.waitForTimeout(4000);
}
// scroll to force hydration/lazy load
for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 1500); await page.waitForTimeout(1500); }
const tiles = await page.evaluate(() => {
  const t = document.querySelector('[data-testid^="product-name-btn-"]');
  return { found: !!t, count: document.querySelectorAll('[data-testid^="product-name-btn-"]').length,
           html: t ? t.closest('[data-testid="product-tile"], article, div[class*="tile"]')?.outerHTML?.slice(0, 4000) : null,
           bodyLen: document.body.innerHTML.length };
});
log(JSON.stringify({ tilesFound: tiles.found, count: tiles.count, bodyLen: tiles.bodyLen }));
if (tiles.html) await writeFile("/tmp/asda_tile.html", tiles.html);
await writeFile("/tmp/asda_full_search.html", await page.content());
await writeFile("/tmp/asda_fetch_calls.json", JSON.stringify(calls, null, 2));
await ctx.close();
