// Phase 2: get Mobify API details — token manager response bodies + search API calls
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon2] ${m}`);
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: process.env.HEADLESS === "1",
  viewport: { width: 1360, height: 900 }, locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"],
  ignoreDefaultArgs: ["--enable-automation"],
});
await ctx.addInitScript(() => { Object.defineProperty(navigator, "webdriver", { get: () => undefined }); });
const page = ctx.pages()[0] ?? (await ctx.newPage());
const keep = [];
page.on("response", async (res) => {
  const url = res.url();
  if (!/asda\.com/.test(url) || /\.(js|css|png|jpe?g|svg|woff2?|ico|avif|map)(\?|$)/i.test(url)) return;
  if (!/api|token|graphql|mobify|ghs/i.test(url)) return;
  try {
    const body = (await res.text()).slice(0, 20000);
    keep.push({ url: url.replace(/https?:\/\/[^/]+/, "H"), status: res.status(), body });
    log(`CAP ${res.status()} ${url.slice(0, 120)}`);
  } catch {}
});
await page.goto("https://groceries.asda.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
await new Promise(r => setTimeout(r, 8000));
// search via URL (Mobify standard search route)
log("navigating to /search?q=milk");
await page.goto("https://groceries.asda.com/search?q=milk", { waitUntil: "domcontentloaded", timeout: 60000 });
await new Promise(r => setTimeout(r, 10000));
log(`title: ${await page.title().catch(() => "?")}`);
// click first product
try {
  const prod = page.locator('a[href*="/p/"]').first();
  if (await prod.count()) { await prod.click({ timeout: 8000 }); await new Promise(r => setTimeout(r, 8000)); log("clicked product: " + await page.title().catch(()=>"?")); }
  else log("no /p/ product links");
} catch (e) { log("product click failed: " + e.message.split("\n")[0]); }
// cookies for the record
const cookies = await ctx.cookies("https://www.asda.com");
await writeFile("/tmp/asda_recon2.json", JSON.stringify({ keep, cookies: cookies.map(c => ({name: c.name, domain: c.domain, value: c.value.slice(0,60) + (c.value.length>60?"…":"")})) }, null, 2));
log(`saved ${keep.length} api responses -> /tmp/asda_recon2.json`);
await ctx.close();
