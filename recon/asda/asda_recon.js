#!/usr/bin/env node
/**
 * Temporary recon script (step 4 - Asda): drive real headed Chrome (on Xvfb)
 * through Cloudflare, capture groceries.asda.com's API traffic for
 * reverse-engineering. Output: /tmp/asda_recon.json + log on stdout.
 *
 * Run: DISPLAY=:99 node asda_recon.js  (HEADLESS=1 forces headless)
 * The persistent profile at ~/.asda/recon-profile keeps cf_clearance, so
 * a second run may get through more easily than the first.
 */
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";

const log = (m) => console.log(`[asda-recon] ${m}`);

const { chromium } = await import("playwright");

const ctx = await chromium.launchPersistentContext(
  join(homedir(), ".asda", "recon-profile"),
  {
    channel: "chrome",
    headless: process.env.HEADLESS === "1",
    viewport: { width: 1360, height: 900 },
    locale: "en-GB",
    timezoneId: "Europe/London",
    userAgent:
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    args: [
      "--disable-blink-features=AutomationControlled",
      "--no-first-run",
      "--no-default-browser-check",
    ],
    ignoreDefaultArgs: ["--enable-automation"],
  },
);

// De-automation: remove navigator.webdriver, etc.
await ctx.addInitScript(() => {
  Object.defineProperty(navigator, "webdriver", { get: () => undefined });
  window.chrome = window.chrome || { runtime: {} };
  Object.defineProperty(navigator, "languages", { get: () => ["en-GB", "en"] });
  Object.defineProperty(navigator, "plugins", { get: () => [1, 2, 3, 4, 5] });
});

const SKIP = /\.(js|css|mjs|map|png|jpe?g|gif|webp|svg|woff2?|ico|mp4|avif)(\?|$)/i;
const KEEP_HOSTS = /asda\.com/;
const captured = [];
let phase = "home";

const page = ctx.pages()[0] ?? (await ctx.newPage());
page.on("request", (req) => {
  const url = req.url();
  if (SKIP.test(url) || !KEEP_HOSTS.test(url)) return;
  const h = req.headers();
  captured.push({
    phase,
    method: req.method(),
    url,
    resourceType: req.resourceType(),
    headers: {
      authorization: h["authorization"] ?? null,
      "content-type": h["content-type"] ?? null,
      "x-api-key": h["x-api-key"] ?? null,
      "x-csrf-token": h["x-csrf-token"] ?? null,
      "x-xsrf-token": h["x-xsrf-token"] ?? null,
      "x-request-id": h["x-request-id"] ?? null,
      origin: h["origin"] ?? null,
    },
    postData: req.postData()?.slice(0, 6000) ?? null,
  });
});
// keep responses too, for the interesting API calls
page.on("response", async (res) => {
  const url = res.url();
  if (!KEEP_HOSTS.test(url) || SKIP.test(url)) return;
  const ct = res.headers()["content-type"] ?? "";
  if (!ct.includes("json") && !url.includes("graphql") && !url.includes("api")) return;
  try {
    const body = (await res.text()).slice(0, 30000);
    const entry = captured.find((e) => e.url === url && e.method === res.request().method() && e.phase === phase);
    if (entry) entry.responseBody = body;
    else captured.push({ phase, method: res.request().method(), url, status: res.status(), responseBody: body });
  } catch {}
});

const goto = async (url) => {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60_000 });
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const title = await page.title().catch(() => "");
    if (!/just a moment|attention required/i.test(title)) break;
    log(`challenge page ("${title}"), waiting...`);
    await new Promise((r) => setTimeout(r, 4000));
  }
  log(`title: ${await page.title().catch(() => "?")}`);
  await new Promise((r) => setTimeout(r, 6000));
};

log("navigating to groceries.asda.com...");
phase = "home";
await goto("https://groceries.asda.com/");

phase = "search";
let searched = false;
for (const sel of ["input[type=search]", "input[placeholder*='earch' i]", "header input[type=text]", "input[aria-label*='search' i]"]) {
  const input = page.locator(sel).first();
  if (await input.count()) {
    try {
      await input.click({ timeout: 4000 });
      await input.type("milk", { delay: 60 });
      await page.keyboard.press("Enter");
      searched = true;
      log(`searched for "milk" via ${sel}`);
      break;
    } catch (e) {
      log(`search via ${sel} failed: ${e.message.split("\n")[0]}`);
    }
  }
}
if (!searched) log("no search box found");
await new Promise((r) => setTimeout(r, 8000));

// If search worked, click into the first product to capture product-page API calls
phase = "product";
try {
  const prod = page.locator('a[href*="/p/"], a[href*="/product"]').first();
  if (await prod.count()) {
    log(`clicking first product link...`);
    await prod.click({ timeout: 5000 });
    await new Promise((r) => setTimeout(r, 8000));
    log(`product page title: ${await page.title().catch(() => "?")}`);
  } else log("no product links found");
} catch (e) {
  log(`product click failed: ${e.message.split("\n")[0]}`);
}

await writeFile("/tmp/asda_recon.json", JSON.stringify(captured, null, 2));
log(`captured ${captured.length} requests -> /tmp/asda_recon.json`);
await ctx.close();
