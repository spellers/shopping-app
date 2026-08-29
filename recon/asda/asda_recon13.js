// Phase 13: download JS bundles, find basket/cart API call shapes.
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon13] ${m}`);
const { chromium } = await import("playwright");
const ctx = await chromium.launchPersistentContext(join(homedir(), ".asda", "recon-profile"), {
  channel: "chrome", headless: true,
  viewport: { width: 1360, height: 900 }, locale: "en-GB", timezoneId: "Europe/London",
  userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"], ignoreDefaultArgs: ["--enable-automation"],
});
const page = ctx.pages()[0] ?? (await ctx.newPage());
const jsUrls = [];
page.on("request", (req) => {
  if (/\.js(\?|$)/.test(req.url()) && /asda\.com|mobify/i.test(req.url())) jsUrls.push(req.url());
});
await page.goto("https://www.asda.com/groceries/search/milk", { waitUntil: "domcontentloaded", timeout: 90000 }).catch(() => {});
const d = Date.now() + 90000;
while (Date.now() < d) {
  const t = await page.title().catch(() => "");
  if (!/just a moment|attention/i.test(t)) break;
  await page.waitForTimeout(4000);
}
await page.waitForTimeout(10000);
log(`js urls: ${jsUrls.length}`);
const files = {};
for (const u of [...new Set(jsUrls)]) {
  const name = "js_" + u.replace(/[^A-Za-z0-9._-]/g, "_").slice(-80);
  try {
    const r = await page.request.get(u);
    if (r.ok()) { const b = await r.text(); files[name] = b; }
  } catch {}
}
await writeFile("/tmp/asda_js_bundles.json", JSON.stringify(files, null, 1));
log(`downloaded ${Object.keys(files).length} bundles, total ${Object.values(files).join("").length} bytes`);
await ctx.close();
