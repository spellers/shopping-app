// Phase 3: ONE long session — pass challenge once, capture everything.
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon3] ${m}`);
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
page.on("response", async (res) => {
  const url = res.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map)(\?|$)/i.test(url)) return;
  if (!/api|token|graphql|mobify|ghs|search|product/i.test(url)) return;
  try {
    const body = (await res.text()).slice(0, 25000);
    keep.push({ url: url.replace(/^https?:\/\/[^/]+/, "H"), status: res.status(), body });
    log(`CAP ${res.status()} ${url.slice(0, 140)}`);
  } catch {}
});
await page.goto("https://groceries.asda.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
const dl = Date.now() + 180000;
while (Date.now() < dl) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  log("challenge..."); await new Promise(r => setTimeout(r, 4000));
}
log(`home title: ${await page.title().catch(() => "?")}`);
await new Promise(r => setTimeout(r, 8000));
// dump any input-like elements
const inputs = await page.evaluate(() =>
  [...document.querySelectorAll("input, [role=searchbox], [role=combobox]")].slice(0, 20)
    .map(el => ({ tag: el.tagName, type: el.type ?? null, ph: el.placeholder ?? null, aria: el.getAttribute("aria-label"), role: el.getAttribute("role"), vis: el.offsetParent !== null }))
);
log("inputs: " + JSON.stringify(inputs, null, 1).slice(0, 2000));
// try search via URL within same session (same cf clearance)
log("goto /search?q=milk");
await page.goto("https://groceries.asda.com/search?q=milk", { waitUntil: "domcontentloaded", timeout: 60000 });
const dl2 = Date.now() + 120000;
while (Date.now() < dl2) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  log("challenge 2..."); await new Promise(r => setTimeout(r, 4000));
}
log(`search title: ${await page.title().catch(() => "?")}`);
await new Promise(r => setTimeout(r, 10000));
// product links?
const prods = await page.evaluate(() => [...document.querySelectorAll('a[href*="/p/"]')].slice(0, 8).map(a => a.href));
log("product links: " + JSON.stringify(prods));
if (prods.length) {
  await page.goto(prods[0], { waitUntil: "domcontentloaded", timeout: 60000 });
  await new Promise(r => setTimeout(r, 9000));
  log(`product title: ${await page.title().catch(() => "?")}`);
}
const cookies = await ctx.cookies("https://www.asda.com");
await writeFile("/tmp/asda_recon3.json", JSON.stringify({ keep, cookies }, null, 2));
log(`saved ${keep.length} api responses + ${cookies.length} cookies`);
await ctx.close();
