// Phase 6: robust search capture.
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon6] ${m}`);
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
page.on("request", (req) => {
  const url = req.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map)(\?|$)/i.test(url)) return;
  const h = req.headers();
  keep.push({ kind: "REQ", url: url.replace(/^https?:\/\/[^/]+/, "H"), method: req.method(),
    headers: { auth: h["authorization"] ?? null, ct: h["content-type"] ?? null, rid: h["x-request-id"] ?? null },
    post: req.postData()?.slice(0, 8000) ?? null });
});
page.on("response", async (res) => {
  const url = res.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map)(\?|$)/i.test(url)) return;
  const ct = res.headers()["content-type"] ?? "";
  if (!ct.includes("json")) return;
  try { keep.push({ kind: "RES", url: url.replace(/^https?:\/\/[^/]+/, "H"), status: res.status(), body: (await res.text()).slice(0, 80000) }); } catch {}
});
await page.goto("https://groceries.asda.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
const dl = Date.now() + 120000;
while (Date.now() < dl) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await new Promise(r => setTimeout(r, 4000));
}
await new Promise(r => setTimeout(r, 6000));

// Try several ways to get the search box focused
const methods = [
  async () => { await page.click('a[href="#search"]', { timeout: 5000 }); await page.waitForSelector('input[placeholder="Search for..."]', { timeout: 8000 }); },
  async () => { await page.waitForSelector('input[placeholder="Search for..."]', { timeout: 8000 }); },
];
let ok = false;
for (const m of methods) { try { await m(); ok = true; break; } catch (e) { log("method failed: " + e.message.split("\n")[0]); } }
if (!ok) throw new Error("could not find search input");

const before = keep.length;
const input = page.locator('input[placeholder="Search for..."]');
await input.pressSequentially("milk", { delay: 80 });
await page.waitForTimeout(1500);
await page.keyboard.press("Enter");
await page.waitForTimeout(12000);
log(`after search: url=${page.url()}, new traffic=${keep.length - before}`);
const prods = await page.evaluate(() => [...document.querySelectorAll('a[href*="/p/"]')].slice(0, 5).map(a => a.href));
log("product links: " + JSON.stringify(prods));
if (prods.length) {
  const b2 = keep.length;
  await page.goto(prods[0], { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(10000);
  log(`product page: title=${await page.title().catch(() => "?")}, new traffic=${keep.length - b2}`);
}
await writeFile("/tmp/asda_recon6.json", JSON.stringify(keep, null, 2));
log(`saved ${keep.length}`);
await ctx.close();
