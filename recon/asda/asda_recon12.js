// Phase 12: click add-to-basket and capture the API calls.
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon12] ${m}`);
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
  if (/\/fps\/|google-analytics|googletagmanager|g\/collect|track\.gif|kampyle|one-trust|adobedtm|algolia/i.test(url)) return;
  const h = req.headers();
  keep.push({ kind: "REQ", url, method: req.method(),
    headers: { auth: h["authorization"] ?? null, ct: h["content-type"] ?? null, rid: h["x-request-id"] ?? null },
    post: req.postData()?.slice(0, 10000) ?? null });
});
page.on("response", async (res) => {
  const url = res.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map|gif)(\?|$)/i.test(url)) return;
  if (/\/fps\/|google-analytics|googletagmanager|g\/collect|track\.gif|kampyle|one-trust|adobedtm|algolia/i.test(url)) return;
  const ct = res.headers()["content-type"] ?? "";
  if (/image|font|text\/css/.test(ct)) return;
  let body = null;
  try { body = (await res.text()).slice(0, 60000); } catch {}
  keep.push({ kind: "RES", url, status: res.status(), body });
});
await page.goto("https://www.asda.com/groceries/search/milk", { waitUntil: "domcontentloaded", timeout: 60000 });
const d = Date.now() + 120000;
while (Date.now() < d) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await page.waitForTimeout(4000);
}
await page.waitForSelector('[data-testid^="product-name-btn-"]', { timeout: 45000 }).catch(() => log("no tiles"));
// find an add-to-basket button within the first tile
const tile = await page.$('[data-testid^="product-name-btn-"]');
const btn = await page.$('[data-testid="add-btn"]');
log(`tile=${!!tile} btn=${!!btn}`);
if (btn) {
  await btn.click();
  await page.waitForTimeout(8000);
  log(`after click: ${await page.title().catch(() => "?")}`);
} else {
  // fallback: go to product page and click there
  const link = await page.$('a[href*="/p/"]');
  log("no add button on search; product link: " + (link ? await link.getAttribute("href") : "none"));
  if (link) {
    await link.click();
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(6000);
    const btn2 = await page.$('button:has-text("Add to basket"), [data-testid*="add-to-basket"]');
    log(`product page add btn: ${!!btn2}`);
    if (btn2) { await btn2.click(); await page.waitForTimeout(8000); log(`after click: ${await page.title().catch(() => "?")}`); }
  }
}
await writeFile("/tmp/asda_recon12.json", JSON.stringify(keep, null, 2));
log(`saved ${keep.length}`);
await ctx.close();
