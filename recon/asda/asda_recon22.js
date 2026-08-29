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
await page.waitForTimeout(3000);
const out = await page.evaluate(async () => {
  const res = {};
  let token = null;
  for (const c of document.cookie.split("; ")) {
    if (c.startsWith("SLAS.AUTH_TOKEN=")) token = decodeURIComponent(c.slice("SLAS.AUTH_TOKEN=".length));
  }
  const S = "siteId=ASDA_GROCERIES";
  async function call(method, path, body) {
    try {
      const r = await fetch("/mobify/proxy/ghs-api/checkout/shopper-baskets/v1/organizations/f_ecom_bjgs_prd" + path, {
        method,
        headers: { "content-type": "application/json", authorization: token },
        body: body ? JSON.stringify(body) : undefined,
        credentials: "include",
      });
      return { status: r.status, body: await r.text().then(t => t.slice(0, 6000)) };
    } catch (e) { return { status: "ERR", body: String(e) }; }
  }
  const bodies = [
    { listName: "Groceries", listType: "Groceries", type: "Groceries", currency: "GBP", language: "en-GB" },
    { listName: "Groceries", currency: "GBP" },
    {},
  ];
  for (let i = 0; i < bodies.length; i++) {
    res["b" + i] = await call("POST", `/baskets?${S}`, bodies[i]);
    if (res["b" + i].status === 200) { res.created = i; break; }
  }
  const body = JSON.parse((res.created !== undefined ? res["b" + res.created] : res.b0).body || "{}");
  res.basketId = body.basketId;
  if (body.basketId) {
    res.get = await call("GET", `/baskets/${body.basketId}?${S}`);
  }
  return res;
});
console.log(JSON.stringify(out, null, 1).slice(0, 5000));
await ctx.close();
