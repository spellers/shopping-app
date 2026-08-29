import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon9] ${m}`);
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: process.env.HEADLESS === "1",
  viewport: { width: 1360, height: 900 }, locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"], ignoreDefaultArgs: ["--enable-automation"],
});
const page = ctx.pages()[0] ?? (await ctx.newPage());
await page.goto("https://www.asda.com/groceries/search/milk", { waitUntil: "domcontentloaded", timeout: 60000 });
const d = Date.now() + 120000;
while (Date.now() < d) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await page.waitForTimeout(4000);
}
await page.waitForTimeout(8000);
const html = await page.content();
await writeFile("/tmp/asda_search.html", html);
log(`html saved, ${html.length} bytes`);
// product links of any shape
const links = await page.evaluate(() => {
  const as = [...document.querySelectorAll("a")].map(a => a.href).filter(h => /asda\.com\/groceries\/[a-z0-9-]+\/\d+/i.test(h) || /\/p\//i.test(h));
  return [...new Set(as)].slice(0, 15);
});
log("product-ish links: " + JSON.stringify(links, null, 1));
await ctx.close();
