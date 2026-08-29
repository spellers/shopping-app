# Asda reverse-engineering recon artifacts (2026-08-29)

Temporary Playwright/curl scripts used to map Asda's APIs. The results are
distilled in `PLAN-multi-grocer.md` (step 4) and the working code in
`providers/asda.py` + `scripts/asda_basket.js` — these scripts are kept as
reference for re-doing the recon when Asda changes something, and can be
deleted at any time.

Key findings (see plan):
- Search/product data: Algolia, appId `8I6WSKCCNV`, index `ASDA_PRODUCTS`,
  search-only key embedded in every page. Plain HTTP works.
- Basket: BCC shopper-baskets behind Cloudflare at
  `https://www.asda.com/mobify/proxy/ghs-api/checkout/shopper-baskets/v1/organizations/f_ecom_bjgs_prd?siteId=ASDA_GROCERIES`.
  Guest baskets, no account needed. Must run inside a real Chrome session.
