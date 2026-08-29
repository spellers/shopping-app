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
      return { status: r.status, body: await r.text().then(t => t.slice(0, 8000)) };
    } catch (e) { return { status: "ERR", body: String(e) }; }
  }
  const create = await call("POST", `/baskets?${S}`, {});
  let gb = JSON.parse(create.body || "{}");
  res.create = { status: create.status, basketId: gb.basketId, keys: Object.keys(gb) };
  const bid = gb.basketId;
  const link = document.querySelector('a[href*="/groceries/product/"]')?.getAttribute("href");
  const cin = (link || "").match(/(\d+)$/)?.[1];
  res.cin = cin;
  // App code: PATCH baskets/{id}/items/{itemId} with {productId, quantity, c_allowSubstitutes}
  res.patchNew = await call("PATCH", `/baskets/${bid}/items/1?${S}`, { productId: cin, quantity: 1, c_allowSubstitutes: true });
  let pb = JSON.parse(res.patchNew.body || "{}");
  const items1 = (pb.shipments || []).flatMap(s => s.productItems || []);
  res.afterPatch = items1.map(i => ({ code: i.productCode, name: i.productName, qty: i.quantity, price: i.priceValue, itemId: i.itemId }));
  if (items1.length) {
    const it = items1[0];
    // update qty to 2
    res.patch2 = await call("PATCH", `/baskets/${bid}/items/${it.itemId}?${S}`, { productId: it.productCode, quantity: 2, c_allowSubstitutes: true });
    const pb2 = JSON.parse(res.patch2.body || "{}");
    const items2 = (pb2.shipments || []).flatMap(s => s.productItems || []);
    res.afterPatch2 = items2.map(i => ({ code: i.productCode, qty: i.quantity, itemId: i.itemId }));
    res.totals = { productTotal: pb2.productTotal, orderTotal: pb2.orderTotal };
    // remove item
    res.delItem = await call("DELETE", `/baskets/${bid}/items/${it.itemId}?${S}`, null);
  }
  res.delBasket = await call("DELETE", `/baskets/${bid}?${S}`, null);
  return res;
});
await writeFile("/tmp/asda_recon27.json", JSON.stringify(out, null, 2));
console.log(JSON.stringify(out, null, 1).slice(0, 6500));
await ctx.close();
