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
await page.waitForTimeout(5000);
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
  const create = await call("POST", `/baskets?${S}`, {});
  const bid = JSON.parse(create.body || "{}").basketId;
  res.basketId = bid;
  // grab first product CIN from DOM
  const links = [...document.querySelectorAll('a[href*="/p/"]')].map(a => a.getAttribute("href")).slice(0, 5);
  res.links = links;
  const cin = (links[0] || "").match(/\/p\/([0-9]+)/)?.[1];
  res.cin = cin;
  if (cin) {
    const bodies = [
      [ { productCode: cin, quantity: 1, quantityAvailable: null, quantityBackOrdered: null, itemIndex: 1, lineItemNumber: 1, type: "Product" } ],
      [ { productCode: cin, quantity: 1, itemIndex: 1, lineItemNumber: 1 } ],
      { productCode: cin, quantity: 1, itemIndex: 1, lineItemNumber: 1 },
    ];
    for (let i = 0; i < bodies.length; i++) {
      res["add" + i] = await call("PUT", `/baskets/${bid}/items/${cin}?${S}`, bodies[i]);
      if (res["add" + i].status === 200) { res.addOk = i; break; }
    }
    if (res.addOk !== undefined) {
      const g = await call("GET", `/baskets/${bid}?${S}`);
      const gb = JSON.parse(g.body || "{}");
      const items = (gb.shipments || []).flatMap(s => s.productItems || []);
      res.items = items.map(i => ({ code: i.productCode, name: i.productName, qty: i.quantity, price: i.priceValue }));
      res.totals = { productTotal: gb.productTotal, orderTotal: gb.orderTotal };
      // cleanup: delete basket
      res.del = await call("DELETE", `/baskets/${bid}?${S}`, null);
    }
  }
  return res;
});
await writeFile("/tmp/asda_recon23.json", JSON.stringify(out, null, 2));
console.log(JSON.stringify(out, null, 1).slice(0, 6000));
await ctx.close();
