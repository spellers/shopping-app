import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { homedir } from "node:os";
const log = (m) => console.log(`[recon15] ${m}`);
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
  async function call(method, path, body, siteId) {
    try {
      const r = await fetch("/mobify/proxy/ghs-api/checkout/shopper-baskets/v1/organizations/f_ecom_bjgs_prd" + path, {
        method,
        headers: { "content-type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      return { status: r.status, body: await r.text().then(t => t.slice(0, 6000)) };
    } catch (e) { return { status: "ERR", body: String(e) }; }
  }
  const S = "?siteId=uk";
  res.create = await call("POST", "/baskets" + S, { customerName: { firstName: "Test", lastName: "Recon" }, currency: "GBP", listName: "Groceries", listType: "Groceries", type: "Groceries", language: "en-GB" });
  const bid = JSON.parse(res.create.body || "{}").basketId;
  res.basketId = bid;
  if (bid) {
    res.get = await call("GET", `/baskets/${bid}${S}`);
    let cin = null;
    const a = document.querySelector('a[href*="/p/"]');
    if (a) { const m = a.getAttribute("href").match(/\/p\/([0-9]+)/); cin = m && m[1]; }
    res.cin = cin;
    if (cin) {
      res.add = await call("PUT", `/baskets/${bid}/items/${cin}${S}`, [
        { productCode: cin, quantity: 1, quantityAvailable: null, quantityBackOrdered: null, itemIndex: 1, lineItemNumber: 1, type: "Product" }
      ]);
      res.get2 = await call("GET", `/baskets/${bid}${S}`);
    }
  }
  return res;
});
await writeFile("/tmp/asda_recon15.json", JSON.stringify(out, null, 2));
console.log(JSON.stringify(out, null, 1).slice(0, 4500));
await ctx.close();
