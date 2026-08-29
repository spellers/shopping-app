// Phase 8: direct navigation to search + product, full API capture.
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon8] ${m}`);
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: process.env.HEADLESS === "1",
  viewport: { width: 1360, height: 900 }, locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"], ignoreDefaultArgs: ["--enable-automation"],
});
await ctx.addInitScript(() => { Object.defineProperty(navigator, "webdriver", { get: () => undefined }); });
const page = ctx.pages()[0] ?? (await ctx.newPage());
const keep = [];
let phase = "";
page.on("request", (req) => {
  const url = req.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map)(\?|$)/i.test(url)) return;
  const h = req.headers();
  keep.push({ phase, kind: "REQ", url: url.replace(/^https?:\/\/[^/]+/, "H"), method: req.method(),
    headers: { auth: h["authorization"] ?? null, ct: h["content-type"] ?? null, rid: h["x-request-id"] ?? null },
    post: req.postData()?.slice(0, 8000) ?? null });
});
page.on("response", async (res) => {
  const url = res.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map)(\?|$)/i.test(url)) return;
  const ct = res.headers()["content-type"] ?? "";
  if (!ct.includes("json")) return;
  try { keep.push({ phase, kind: "RES", url: url.replace(/^https?:\/\/[^/]+/, "H"), status: res.status(), body: (await res.text()).slice(0, 80000) }); } catch {}
});
const waitOut = async () => {
  const d = Date.now() + 120000;
  while (Date.now() < d) {
    const t = await page.title().catch(() => "");
    if (!/just a moment|attention/i.test(t)) break;
    await page.waitForTimeout(4000);
  }
};
phase = "search";
await page.goto("https://www.asda.com/groceries/search/milk", { waitUntil: "domcontentloaded", timeout: 60000 });
await waitOut();
await page.waitForTimeout(10000);
log(`search: title=${await page.title().catch(() => "?")}`);
const prods = await page.evaluate(() => [...document.querySelectorAll('a[href*="/p/"]')].slice(0, 4).map(a => a.href));
log("product links: " + JSON.stringify(prods));
if (prods.length) {
  phase = "product";
  await page.goto(prods[0], { waitUntil: "domcontentloaded", timeout: 60000 });
  await waitOut();
  await page.waitForTimeout(10000);
  log(`product: title=${await page.title().catch(() => "?")}, url=${page.url()}`);
}
await writeFile("/tmp/asda_recon8.json", JSON.stringify(keep, null, 2));
log(`saved ${keep.length}`);
await ctx.close();
