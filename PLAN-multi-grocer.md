# Multi-grocer tooling plan

Goal: shopping app supports **Tesco, Sainsbury's, Asda, Morrisons, Waitrose** (UK online shopping/delivery).

## Decision (no fork of basketeer)

- Tesco: **keep basketeer CLI** as the backend (Q1 resolved — no fallback backend).
- Sainsbury's: adopt **open-supermarkets** as a second vendored CLI (has Tesco + Sainsbury's + Ocado).
- Asda / Morrisons / Waitrose: in-house provider modules (no existing tooling; each ~1–2 weeks reverse-engineering + ongoing bot-wall maintenance).
- Q2 resolved: **one retailer per app session** — the user selects a supermarket; item lookup and basket are always scoped to that retailer. Basket items do not carry over when switching retailers.
- Q3 resolved: **never force a delivery-type choice** if avoidable; if one is unavoidable to populate a basket, default to **Delivery**.

## Checklist

- [x] **1. DB migration** — retailer dimension in schema (`grocer_products(retailer, sku, …)`; `sku`/`retailer` on ingredients, persistent_ingredients, shopping_list_items). Done 2026-08-28: `tesco_sku`→`sku` renames, `retailer` columns default `'tesco'`, `tesco_products` cache folded into `grocer_products`, tests updated (97 passing).
- [x] **2. Grocer interface** — Done 2026-08-29: `providers/` package with `Grocer` base class + registry (`get_grocer`/`list_grocers`); basketeer backend moved to `providers/tesco.py` with a `TescoGrocer` adapter; top-level `tesco.py` is now a compat shim; app.py match/refresh/routes go through the registry (routes keep their `/tesco/*` URLs — generalising them is step 7). 97/97 tests pass; adding a retailer = one module + one registry line.
- [x] **3. Sainsbury's** — Done 2026-08-29: open-supermarkets (MIT, v3) added to `package.json`/`node_modules`; backend calls the JS provider library directly (`node -e` with `SainsburysProvider`), not the CLI. `providers/sainsburys.py` implements the full Grocer interface (search, get_product, basket read, basket_set, auth via `~/.sainsburys/session.json` + WC_AUTHENTICATION_ cookie, checkout hand-off URL) and registers as `'sainsburys'`. Sign-in: `scripts/sainsburys_login.js` (headed Chromium, human completes MFA, writes session file) driven by the same background-thread pattern as Tesco. Live-verified anonymous: search/get_product/basket-read all work; basket writes correctly 401 signed-out. 119 tests pass. Build bundles it for free (`build/build.py` copies whole `node_modules` + `scripts/`). App routes for it land in step 7 (UI).
- [ ] **4. Asda provider** — reverse-engineer gateway, in-house module.
- [ ] **5. Morrisons provider** — reverse-engineer gateway, in-house module.
- [ ] **6. Waitrose provider** — reverse-engineer gateway, in-house module (Q3: default Delivery if forced to choose).
- [ ] **7. UI** — app-wide retailer selector; lookup + basket scoped to selected retailer (Q2).
- [ ] **8. Packaging** — bundle additional CLI/Node deps into PyInstaller build (see PACKAGING.md).

## Facts

- open-supermarkets registry: UK coverage = Tesco / Sainsbury's / Ocado **only** (no Asda/Morrisons/Waitrose).
- Ocado not in target list but ~free via open-supermarkets (read/basket/slots; no checkout — AWS WAF). Optional add later.
- Pre-migration DB backup: `shopping_app.db.pre-migration.bak` (repo root).
