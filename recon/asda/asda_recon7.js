import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon7] ${m}`);
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: process.env.HEADLESS === "1",
  viewport: { width: 1360, height: 900 }, locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"], ignoreDefaultArgs: ["--enable-automation"],
});
await ctx.addInitScript(() => { Object.defineProperty(navigator, "webdriver", { get: () => undefined }); });
const page = ctx.pages()[0] ?? (await ctx.newPage());
await page.goto("https://groceries.asda.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
const dl = Date.now() + 120000;
while (Date.now() < dl) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await new Promise(r => setTimeout(r, 4000));
}
await page.waitForTimeout(8000);
await page.screenshot({ path: "/tmp/asda_home.png", fullPage: false });
const inputs = await page.evaluate(() => [...document.querySelectorAll("input")].map(i => ({ ph: i.placeholder, type: i.type, vis: i.offsetParent !== null })));
log("inputs: " + JSON.stringify(inputs));
// try programmatic click on skip link
await page.evaluate(() => document.querySelector('a[href="#search"]')?.click());
await page.waitForTimeout(2500);
const inputs2 = await page.evaluate(() => [...document.querySelectorAll("input")].map(i => ({ ph: i.placeholder, type: i.type, vis: i.offsetParent !== null })));
log("inputs after skip: " + JSON.stringify(inputs2));
await page.screenshot({ path: "/tmp/asda_search.png" });
// focus and type
const done = await page.evaluate(() => {
  const i = [...document.querySelectorAll("input")].find(i => i.placeholder === "Search for...");
  if (!i) return false;
  i.focus();
  return true;
});
log("focused: " + done);
if (done) {
  await page.keyboard.type("milk", { delay: 80 });
  await page.waitForTimeout(2000);
  await page.keyboard.press("Enter");
}
await page.waitForTimeout(12000);
log(`url=${page.url()} title=${await page.title().catch(() => "?")}`);
await page.screenshot({ path: "/tmp/asda_after.png" });
await ctx.close();
