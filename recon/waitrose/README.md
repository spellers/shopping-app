# Waitrose API recon (step 6)

Reverse-engineered from the web/Android API surface, cross-checked against the
maintained Go reference client `jingkaihe/waitrose` (cloned into `lib/`).
`probe*.mjs` / `probe.py` are the original reachability probes.

## Key facts

- All traffic: `https://www.waitrose.com` (Akamai origin behind CloudFront).
  The Go client's `okhttp/4.12.0` User-Agent + `client-correlation-id` +
  `breadcrumb` headers are what the API expects.
- **Login is plain email/password, no MFA** — `generateSession` GraphQL
  mutation on `/api/graphql-prod/graph/live` with
  `{"input": {"username", "password", "clientId": "ANDROID_APP"}}`.
- A session carries `customerId`, `customerOrderId`, `defaultBranchId` —
  **all search and trolley calls are keyed on the customer/order ids**, so
  Waitrose has no meaningful guest mode (unlike Asda/Morrisons). Sign-in is
  required before anything works.
- Search: `POST /api/content-prod/v2/cms/publish/productcontent/search/<customerId>?clientType=WEB_APP`
  with `{"customerSearchRequest": {"queryParams": {"searchTerm", "start", "branchId", "orderId"}}}`.
- Trolley read/update: GraphQL `getTrolley(orderId)` /
  `updateTrolleyItems(trolleyItems, orderId)`. Updates take **absolute**
  quantities (`quantity: {amount: n}`); `0` removes the line.
- Product id is the full search `id` (`<lineNumber>-...`); the trolley input
  wants both the bare `lineNumber` (first dash segment) and the full
  `productId`.
- Slots/order/checkout are deliberately **not** implemented — the provider
  hands off to the website (same stop-at-payment design as the others).
  Per the Q3 decision, delivery is the default when the site forces a choice.

## Blocker at time of writing (2026-08-29)

This machine's IP was hard-blocked by Akamai (TLS completes, then the
connection is dropped/reset — curl and real Chrome alike, `www.waitrose.com`
and the API host). Other sites (incl. other Akamai properties) were fine.
Likely rate-based from the recon volume; Asda's equivalent block cleared
after ~an hour of cooldown. **Live verification of search + trolley is
outstanding** — retry when the block clears (expect a working `search` and
full basket cycle like Asda/Morrisons got).

## Provider design notes

- `providers/waitrose.py` uses stdlib `urllib` only (no requests, no node,
  no browser) — same footprint as Morrisons.
- Credentials live in `~/.waitrose/credentials.json`
  (`{"email": ..., "password": ...}`); the session (tokens + ids, expiry,
  refresh) in `~/.waitrose/session.json`, refreshed transparently via the
  refresh token on expiry.
- Login runs a background thread + `login_status()` polling, matching the
  other providers so the app's login UI works unchanged.
