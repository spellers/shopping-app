import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: true,
  viewport: { width: 1360, height: 900 }, locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"], ignoreDefaultArgs: ["--enable-automation"],
});
await ctx.addInitScript(() => { Object.defineProperty(navigator, "webdriver", { get: () => undefined }); });
const page = ctx.pages()[0] ?? (await ctx.newPage());
await page.goto("https://www.asda.com/groceries/search/milk", { waitUntil: "domcontentloaded", timeout: 90000 }).catch(() => {});
const d = Date.now() + 90000;
while (Date.now() < d) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await page.waitForTimeout(4000);
}
await page.waitForTimeout(6000);
const info = await page.evaluate(() => {
  const tiles = document.querySelectorAll('[data-testid^="product-name-btn-"]');
  const allLinks = [...document.querySelectorAll("a")].map(a => a.getAttribute("href")).filter(h => h && /product|\/p\//i.test(h)).slice(0, 10);
  return { tileCount: tiles.length, firstTile: tiles[0] ? tiles[0].outerHTML.slice(0, 500) : null, allLinks, title: document.title };
});
console.log(JSON.stringify(info, null, 1));
await writeFile("/tmp/asda_dom2.html", await page.content());
await ctx.close();
