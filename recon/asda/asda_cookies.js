import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: false, viewport: { width: 1360, height: 900 },
  locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"], ignoreDefaultArgs: ["--enable-automation"],
});
const page = ctx.pages()[0] ?? (await ctx.newPage());
await page.goto("https://groceries.asda.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
// wait out any challenge
const dl = Date.now() + 90000;
while (Date.now() < dl) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await new Promise(r => setTimeout(r, 4000));
}
console.log("title:", await page.title().catch(() => "?"));
await new Promise(r => setTimeout(r, 5000));
const cookies = await ctx.cookies("https://www.asda.com");
await writeFile("/tmp/asda_full_cookies.json", JSON.stringify(cookies, null, 2));
console.log("saved", cookies.length, "cookies");
await ctx.close();
