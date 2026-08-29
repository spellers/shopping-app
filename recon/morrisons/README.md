# Morrisons API recon (2026-08-29)

Reference material for `providers/morrisons.py`. If the provider breaks,
re-run this recon to diff against the captured responses.

## API map (all plain HTTP via stdlib urllib — no browser, no node needed)

Base: `https://groceries.morrisons.com`

| What | Call |
|---|---|
| Catalogue search | `GET /api/webproductpagews/v6/product-pages/search?q=<query>&maxPageSize=300&maxProductsToDecorate=200` — products under `productGroups[].decoratedProducts` (both page-size params are required or `decoratedProducts` comes back empty) |
| Product lookup | no by-id endpoint; search by the numeric `retailerProductId` (SKU) and match |
| Basket read | `GET /api/cart/v1/carts/active` — guest cart, tied to the `VISITORID` cookie (session must keep the cookie jar alive) |
| Basket write | `POST /api/cart/v1/carts/active/apply-quantity` — body is a raw array of `{"productId": <uuid>, "quantity": <delta>}`. **Additive** deltas (negative removes). Requires the `x-csrf-token` header |
| CSRF token | embedded in the homepage HTML JSON: `"csrf":{"token":"..."` |
| Checkout | `https://groceries.morrisons.com/checkout` (browser hand-off) |

## Gotchas

- The 403 seen with bare curl on the first POST was `{"code":"ecom-csrf-failure"}` —
  missing `x-csrf-token` header, **not** a bot wall. With the token + `Origin`/
  `Referer` headers everything works over plain HTTP.
- `decoratedProducts` needs `maxPageSize` AND `maxProductsToDecorate`; without them
  the search response has `productGroups` present but empty.
- Cart items only carry the UUID `productId` + quantity + `finalPrice` — no name.
  The cart's UUID is the `productId` field on search results, distinct from the
  stable numeric `retailerProductId` (SKU) this provider exposes.
- The 500 on first `apply-quantity` attempts was the missing-`Origin`-header /
  malformed-body phase; the working body is the raw items array, not `{"items": […]}`.

## Files

- `search.json` — full search response (`q=milk`, 200 products)
- `home.html` / `home2.html` / `home3.html` — homepage HTML (CSRF token source)
- `cart*.json` — cart responses through the add/update/delete cycle
- `add*.json` / `upd.json` / `del*.json` — write-call bodies
- `index.js` — bundle fragment with the cart call sites
- `cj*.txt` — captured cookie jars
