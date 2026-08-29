// Asda basket operations for the shopping app (multi-grocer plan, step 4).
//
// Asda (Mobify/SFCC) blocks plain HTTP clients with Cloudflare, so basket
// calls must run inside a real Chrome session. This script opens Asda in
// headless Chrome (persistent profile keeps the Cloudflare clearance),
// reads the guest auth token from cookies, and executes one basket command
// passed as JSON on argv[2] against the site's own API proxy:
//
//   node asda_basket.js '{"cmd": "get"}'
//   node asda_basket.js '{"cmd": "set", "cin": "165468", "qty": 2}'
//
// The guest basket id is persisted in ~/.asda/basket.json so calls between
// app requests keep operating on the same basket. Guest baskets are capped
// per session, so the script cleans up stale ones when creation fails (the
// same recovery the Asda site itself does).
//
// Verified API shapes (2026-08-29, from the site's own bundles):
//   POST   /baskets?siteId=ASDA_GROCERIES
//   GET    /baskets/{id}?siteId=ASDA_GROCERIES   (items at basket.productItems)
//   POST   /baskets/{id}/items?siteId=ASDA_GROCERIES   body: [{productId, quantity, c_allowSubstitutes}]
//   PATCH  /baskets/{id}/items/{itemId}?siteId=ASDA_GROCERIES  body: {productId, quantity, c_allowSubstitutes}
//   DELETE /baskets/{id}/items/{itemId}?siteId=ASDA_GROCERIES
//   DELETE /baskets/{id}?siteId=ASDA_GROCERIES
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { chromium } from "playwright";

const HOME = join(homedir(), ".asda");
const PROFILE = join(HOME, "recon-profile");
const STATE_FILE = join(HOME, "basket.json");
const BASE = "/mobify/proxy/ghs-api/checkout/shopper-baskets/v1/organizations/f_ecom_bjgs_prd";
const SITE = "siteId=ASDA_GROCERIES";

let cmd;
try {
  cmd = JSON.parse(process.argv[2] || "{}");
} catch {
  console.error("bad command JSON");
  process.exit(2);
}

let state = { basketId: null };
try {
  if (existsSync(STATE_FILE)) state = JSON.parse(readFileSync(STATE_FILE, "utf8"));
} catch {}

const ctx = await chromium.launchPersistentContext(PROFILE, {
  channel: "chrome",
  headless: true,
  viewport: { width: 1360, height: 900 },
  locale: "en-GB",
  timezoneId: "Europe/London",
  userAgent:
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
  args: ["--disable-blink-features=AutomationControlled"],
  ignoreDefaultArgs: ["--enable-automation"],
});

let failed = false;
try {
  await ctx.addInitScript(() => {
    Object.defineProperty(navigator, "webdriver", { get: () => undefined });
  });
  const page = ctx.pages()[0] ?? (await ctx.newPage());
  // Any groceries page gives the proxy + cookies; the search page is cheap.
  await page.goto("https://www.asda.com/groceries/search/milk", {
    waitUntil: "domcontentloaded",
    timeout: 90000,
  }).catch(() => {});
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    const title = await page.title().catch(() => "");
    if (!/just a moment|attention/i.test(title)) break;
    await page.waitForTimeout(4000);
  }
  const title = await page.title().catch(() => "");
  if (/just a moment|attention/i.test(title)) {
    throw new Error("Asda's bot check (Cloudflare) is not clearing - try again in a minute");
  }
  await page.waitForTimeout(3000);

  const out = await page.evaluate(async (args) => {
    const cmd = args.cmd;
    const state = args.state;
    const SITE = args.site;
    const BASE = args.base;
    let token = null;
    for (const c of document.cookie.split("; ")) {
      if (c.startsWith("SLAS.AUTH_TOKEN=")) token = decodeURIComponent(c.slice("SLAS.AUTH_TOKEN=".length));
    }
    async function call(method, path, body) {
      const r = await fetch(BASE + path, {
        method,
        headers: { "content-type": "application/json", authorization: token },
        body: body ? JSON.stringify(body) : undefined,
        credentials: "include",
      });
      let data = null;
      try { data = await r.json(); } catch {}
      return { status: r.status, data };
    }
    function itemsOf(basket) {
      // items live at basket.productItems (shipments[] only carry totals)
      return basket.productItems || [];
    }
    async function ensureBasket() {
      let r = await call("POST", `/baskets?${SITE}`, {});
      if (r.status === 400 && r.data && r.data.basketIds) {
        // guest basket cap hit - the site's own recovery: delete then retry
        for (const id of String(r.data.basketIds).split(",").filter(Boolean))
          await call("DELETE", `/baskets/${id}?${SITE}`, null);
        r = await call("POST", `/baskets?${SITE}`, {});
      }
      if (r.status !== 200 || !r.data || !r.data.basketId)
        throw new Error(`Asda basket creation failed (HTTP ${r.status})`);
      state.basketId = r.data.basketId;
      return r.data;
    }

    function reply(result) {
      // state must come back to Node for persistence (page args are by-value)
      return { state, result };
    }

    if (cmd.cmd === "get") {
      if (!state.basketId)
        return reply({ items: [], total_qty: 0, total_cost: 0 });
      const r = await call("GET", `/baskets/${state.basketId}?${SITE}`, null);
      if (r.status === 404) {
        // basket gone (session rotated) - start a fresh empty one
        await ensureBasket();
        return reply({ items: [], total_qty: 0, total_cost: 0 });
      }
      if (r.status !== 200)
        throw new Error(`Asda basket read failed (HTTP ${r.status})`);
      const basket = r.data;
      const items = itemsOf(basket).map((i) => ({
        item_id: i.itemId,
        sku: i.productId,
        title: i.productName || i.itemText || "",
        qty: i.quantity || 0,
        unit_price: i.basePrice != null ? i.basePrice : null,
        total: i.price != null ? i.price : null,
      }));
      return reply({
        items,
        total_qty: basket.c_totalQty || items.reduce((n, i) => n + i.qty, 0),
        total_cost: basket.productTotal || 0,
      });
    }

    if (cmd.cmd === "set") {
      const cin = String(cmd.cin);
      const target = Math.max(0, Math.trunc(Number(cmd.qty) || 0));
      const basket = await ensureBasket();
      const line = itemsOf(basket).find((i) => String(i.productId) === cin);
      if (target === 0) {
        if (line) {
          const r = await call("DELETE", `/baskets/${state.basketId}/items/${line.itemId}?${SITE}`, null);
          if (r.status !== 204)
            throw new Error(`Asda failed to remove item (HTTP ${r.status})`);
        }
      } else if (line) {
        const r = await call(
          "PATCH",
          `/baskets/${state.basketId}/items/${line.itemId}?${SITE}`,
          { productId: cin, quantity: target, c_allowSubstitutes: true },
        );
        if (r.status !== 200)
          throw new Error(`Asda failed to update item (HTTP ${r.status})`);
      } else {
        const r = await call("POST", `/baskets/${state.basketId}/items?${SITE}`, [
          { productId: cin, quantity: target, c_allowSubstitutes: true },
        ]);
        if (r.status !== 200)
          throw new Error(`Asda failed to add item (HTTP ${r.status})`);
      }
      // confirm the line landed
      const r = await call("GET", `/baskets/${state.basketId}?${SITE}`, null);
      if (r.status === 200) {
        const after = itemsOf(r.data).find((i) => String(i.productId) === cin);
        if (target > 0 && (!after || after.quantity !== target))
          throw new Error("Asda accepted the change but the basket quantity does not match");
      }
      return reply(null);
    }

    throw new Error(`unknown command: ${cmd.cmd}`);
  }, { cmd, state, site: SITE, base: BASE });

  if (out && out.state) state = out.state;
  mkdirSync(HOME, { recursive: true });
  writeFileSync(STATE_FILE, JSON.stringify(state));
  console.log(JSON.stringify(out && out.result !== undefined ? out.result : null));
} catch (e) {
  failed = true;
  console.error(String((e && e.message) || e));
} finally {
  await ctx.close().catch(() => {});
}
process.exit(failed ? 1 : 0);
