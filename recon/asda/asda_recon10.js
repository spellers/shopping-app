// Phase 10: find the XHR that populates search results (no content-type filter).
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon10] ${m}`);
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: true,
  viewport: { width: 1360, height: 900 }, locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"], ignoreDefaultArgs: ["--enable-automation"],
});
await ctx.addInitScript(() => { Object.defineProperty(navigator, "webdriver", { get: () => undefined }); });
const page = ctx.pages()[0] ?? (await ctx.newPage());
const keep = [];
page.on("request", (req) => {
  const url = req.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map|gif)(\?|$)/i.test(url)) return;
  if (/\/fps\/|google-analytics|googletagmanager|g\/collect|track\.gif|kampyle|one-trust|adobedtm/i.test(url)) return;
  const h = req.headers();
  keep.push({ kind: "REQ", url, method: req.method(),
    headers: { auth: h["authorization"] ?? null, ct: h["content-type"] ?? null, rid: h["x-request-id"] ?? null,
               xapi: h["x-api-key"] ?? null, xsrf: h["x-xsrf-token"] ?? null, accept: h["accept"] ?? null },
    post: req.postData()?.slice(0, 20000) ?? null });
});
page.on("response", async (res) => {
  const url = res.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map|gif)(\?|$)/i.test(url)) return;
  if (/\/fps\/|google-analytics|googletagmanager|g\/collect|track\.gif|kampyle|one-trust|adobedtm/i.test(url)) return;
  const ct = res.headers()["content-type"] ?? "";
  if (/image|font|text\/css/.test(ct)) return;
  let body = null;
  try { body = (await res.text()).slice(0, 120000); } catch {}
  keep.push({ kind: "RES", url, status: res.status(), ct, body });
});
await page.goto("https://www.asda.com/groceries/search/milk", { waitUntil: "domcontentloaded", timeout: 60000 });
const d = Date.now() + 120000;
while (Date.now() < d) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await page.waitForTimeout(4000);
}
// wait for actual product tiles
try { await page.waitForSelector('[data-testid="product-name-btn-1"], [data-testid^="product-name-btn-"]', { timeout: 45000 }); } catch { log("no product tiles appeared"); }
await page.waitForTimeout(3000);
log(`title=${await page.title().catch(() => "?")} entries=${keep.length}`);
const prods = await page.evaluate(() => [...document.querySelectorAll('a[href*="/p/"]')].slice(0, 6).map(a => a.href));
log("product links: " + JSON.stringify(prods));
await writeFile("/tmp/asda_recon10.json", JSON.stringify(keep, null, 2));
await ctx.close();
