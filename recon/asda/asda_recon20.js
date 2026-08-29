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
const html = await page.content();
const m = html.match(/"siteId"\s*:\s*"[^"]*"/g);
console.log("siteId in html:", m);
const m2 = html.match(/sfccStoreOcapi[^}]*}/g);
console.log("sfccStoreOcapi:", m2 && m2[0]);
const m3 = html.match(/"siteRedirection"\s*:\s*\{[^]*?\}\}/);
console.log("siteRedirection:", m3 && m3[0].slice(0, 1500));
const m4 = html.match(/"id"\s*:\s*"[^"]{1,40}"\s*,\s*"name"\s*:\s*"[^"]*"/g);
console.log("id+name:", m4 && m4.slice(0, 5));
await ctx.close();
