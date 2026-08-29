// Phase 4: find the search box on the home page (dump search-related elements + click it), then capture the search API.
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon4] ${m}`);
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
  if (!/search|graphql|api|mobify\/proxy|products/i.test(url)) return;
  try {
    const body = (await res.text()).slice(0, 60000);
    keep.push({ url: url.replace(/^https?:\/\/[^/]+/, "H"), status: res.status(), body });
    log(`CAP ${res.status()} ${url.slice(0, 140)}`);
  } catch {}
});
await page.goto("https://groceries.asda.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
const dl = Date.now() + 120000;
while (Date.now() < dl) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  log("challenge..."); await new Promise(r => setTimeout(r, 4000));
}
await new Promise(r => setTimeout(r, 8000));
// dump anything search-related
const info = await page.evaluate(() => {
  const els = [...document.querySelectorAll('[aria-label*="earch" i], [class*="earch" i], a[href*="search"], button')]
    .slice(0, 40)
    .map(el => ({ tag: el.tagName, text: (el.innerText || "").slice(0, 40), aria: el.getAttribute("aria-label"), href: el.href || null, cls: (el.className || "").toString().slice(0, 60), vis: el.offsetParent !== null }));
  return els.filter(e => e.vis);
});
console.log("search-related elements:");
for (const e of info) console.log(" ", JSON.stringify(e));
// click the first plausible search trigger
for (const cand of info.filter(e => /search/i.test(e.aria || "") || /search/i.test(e.cls) || /search/i.test(e.href || ""))) {
  log(`clicking: ${JSON.stringify(cand).slice(0, 150)}`);
  try {
    await page.evaluate((c) => {
      const el = [...document.querySelectorAll('a,button,[role=button],[aria-label]')].find(el =>
        (el.getAttribute("aria-label") || "").toLowerCase().includes((c.aria || "").toLowerCase()) ||
        (el.className || "").toString().includes((c.cls || "").split(" ").find(Boolean) || "___never") && false ||
        (c.href && el.href === c.href)
      ) ?? [...document.querySelectorAll('[class*="earch" i]')].find(el => el.offsetParent !== null);
      el?.click();
    }, cand);
    await new Promise(r => setTimeout(r, 3000));
    // now look for an input that appeared
    const inp = await page.evaluate(() => {
      const i = [...document.querySelectorAll("input")].find(i => i.offsetParent !== null);
      return i ? { ph: i.placeholder, aria: i.getAttribute("aria-label"), type: i.type } : null;
    });
    log("input after click: " + JSON.stringify(inp));
    if (inp) {
      await page.keyboard.type("milk", { delay: 50 });
      await new Promise(r => setTimeout(r, 2500));
      await page.keyboard.press("Enter");
      await new Promise(r => setTimeout(r, 10000));
      log(`post-search title: ${await page.title().catch(() => "?")}, url: ${page.url()}`);
      break;
    }
  } catch (e) { log("click fail: " + e.message.split("\n")[0]); }
}
await writeFile("/tmp/asda_recon4.json", JSON.stringify({ keep }, null, 2));
log(`saved ${keep.length}`);
await ctx.close();
