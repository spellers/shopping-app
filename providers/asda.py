"""Asda integration (multi-grocer plan, step 4) - in-house backend.

Two separate systems, both verified 2026-08-29:

* Catalogue search/product data - Asda's public Algolia index
  (appId/key are embedded in every page). Works from plain Python
  requests, no browser, no sign-in.
* Basket - Asda's Mobify/SFCC "shopper-baskets" API, which sits behind
  Cloudflare bot protection. Plain HTTP clients get 403, so basket calls
  run inside a headless Chrome session via scripts/asda_basket.js
  (persistent profile keeps the Cloudflare clearance). Baskets are GUEST
  baskets - no Asda account is needed; the guest session id and basket id
  are persisted by the script in ~/.asda/.

Checkout hands off to the website (same pattern as Tesco).
"""
import json
import os
import re
import subprocess
import urllib.request

import datadir
from providers import Grocer, GrocerError
from providers.tesco import _display_env, _no_window

BASE_DIR = datadir.resource_dir()
NODE = datadir.node_executable() or 'node'
BASKET_SCRIPT = os.path.join(BASE_DIR, 'scripts', 'asda_basket.js')
CHECKOUT_URL = 'https://www.asda.com/checkout'

# Public search-only Algolia credentials embedded in Asda's page config.
# If Asda rotates them, scrape the new ones from the "algolia" JSON blob on
# any https://www.asda.com page (see asda_recon notes).
ALGOLIA_APP_ID = '8I6WSKCCNV'
ALGOLIA_SEARCH_KEY = '03e4272048dd17f771da37b57ff8a75e'
ALGOLIA_INDEX = 'ASDA_PRODUCTS'
ALGOLIA_URL = f'https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query'

class AsdaError(GrocerError):
    pass


def _algolia_search(query, page_size, facet_filters=None, label='search'):
    """One Algolia query (stdlib urllib - no extra dependency).
    Returns the list of raw hit dicts."""
    body = {
        'query': query,
        'hitsPerPage': page_size,
        'facets': [],
        'attributesToRetrieve': [
            'ID', 'CIN', 'NAME', 'BRAND', 'IMAGE_ID', 'PACK_SIZE',
            'PRICES', 'PRIMARY_TAXONOMY',
        ],
    }
    if facet_filters:
        body['facetFilters'] = facet_filters
    req = urllib.request.Request(
        ALGOLIA_URL,
        data=json.dumps(body).encode(),
        headers={
            'x-algolia-application-id': ALGOLIA_APP_ID,
            'x-algolia-api-key': ALGOLIA_SEARCH_KEY,
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) shopping-app',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.getcode()
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        raise AsdaError(f'Asda {label} returned HTTP {exc.code}')
    except Exception as exc:
        raise AsdaError(f'Asda {label} request failed: {exc}')
    if status != 200:
        raise AsdaError(f'Asda {label} returned HTTP {status}')
    try:
        return json.loads(payload).get('hits') or []
    except ValueError:
        raise AsdaError(f'Could not parse Asda {label} output')


def _image_url(image_id):
    if not image_id:
        return ''
    return f'https://asdagroceries.scene7.com/is/image/asdagroceries/{image_id}'


def _product(hit):
    """Map an Algolia hit onto the shared product-dict shape."""
    prices = hit.get('PRICES') or {}
    en = prices.get('EN') or {}
    price = en.get('PRICE')
    unit_raw = en.get('PRICEPERUOM')
    unit_formatted = en.get('PRICEPERUOMFORMATTED') or ''
    # unit_of_measure: strip the leading price from the formatted string,
    # e.g. '77.0p/LT' -> '/LT' -> 'per LT'
    uom = ''
    if unit_formatted:
        m = re.search(r'/\s*([A-Za-z0-9]+)$', unit_formatted)
        if m:
            uom = f'per {m.group(1).lower()}'
    cin = hit.get('CIN')
    if cin is None:
        cin = hit.get('ID')
    return {
        'sku': str(cin) if cin is not None else '',
        'title': hit.get('NAME') or '',
        'brand': hit.get('BRAND') or '',
        'price': price,
        'unit_price': unit_raw,
        'unit_of_measure': uom,
        'image_url': _image_url(hit.get('IMAGE_ID')),
        'on_offer': str(en.get('OFFER') or 'List').lower() not in ('list', ''),
    }


def search(query, limit=5):
    """Search the Asda catalogue via Algolia. Returns shared-shape product dicts."""
    hits = _algolia_search(query, max(limit, 1))
    return [_product(h) for h in hits[:limit]]


def get_product(sku):
    """Look up one product by CIN (or by name as fallback)."""
    sku = str(sku).strip()
    if sku.isdigit():
        hits = _algolia_search('', 1, facet_filters=[[f'CIN:{sku}']],
                               label='product lookup')
    else:
        hits = _algolia_search(sku, 1, label='product lookup')
    if not hits:
        raise AsdaError('Asda product not found')
    hit = hits[0]
    if sku.isdigit() and str(hit.get('CIN')) != sku and str(hit.get('ID')) != sku:
        raise AsdaError('Asda product not found')
    return _product(hit)


def _basket_call(cmd_obj, timeout=240):
    """Run one basket command in the headless Chrome session.

    Slow by design: each call starts Chrome and gets through Asda's
    Cloudflare check (tens of seconds). The script persists the guest
    session/basket state in ~/.asda/ so repeated calls stay consistent.
    """
    if not os.path.exists(BASKET_SCRIPT):
        raise AsdaError('scripts/asda_basket.js is missing - reinstall the app')
    if NODE is None or not os.path.exists(NODE):
        raise AsdaError('the bundled Node runtime is missing - reinstall the app')
    try:
        proc = subprocess.run(
            [NODE, BASKET_SCRIPT, json.dumps(cmd_obj)],
            capture_output=True, text=True, timeout=timeout, cwd=BASE_DIR,
            env=_display_env(), creationflags=_no_window(),
        )
    except subprocess.TimeoutExpired:
        raise AsdaError('Asda basket operation timed out - the site may be busy')
    except Exception as exc:
        raise AsdaError(str(exc))
    if proc.returncode != 0:
        raise AsdaError((proc.stderr or proc.stdout or 'no output').strip()[:300])
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        raise AsdaError('Could not parse Asda basket output')


def basket():
    """Return the remote Asda guest basket contents (shared shape)."""
    data = _basket_call({'cmd': 'get'}) or {}
    return {
        'items': data.get('items') or [],
        'total_qty': data.get('total_qty') or 0,
        'total_cost': data.get('total_cost') or 0,
    }


def basket_set(sku, qty):
    """Set a basket line to an exact quantity (0 removes it)."""
    _basket_call({'cmd': 'set', 'cin': str(sku), 'qty': int(qty)})
    return None


def auth_status():
    """Asda uses guest baskets - there is no sign-in to track. The guest
    session is valid as long as the persisted profile exists; basket calls
    recover automatically if the session has rotated."""
    return {'signed_in': True, 'note': 'Asda shopping uses a guest session - no sign-in needed'}


def checkout_url():
    """Hand the user off to the Asda website for slots + payment."""
    return CHECKOUT_URL


def parse_qty(quantity_text):
    """Extract an integer count from free-text recipe quantities."""
    m = re.search(r'\d+', str(quantity_text or ''))
    return int(m.group()) if m else 1


class AsdaGrocer(Grocer):
    """Registry adapter for the Asda backend. Methods do a call-time lookup
    into this module's globals so tests can monkeypatch the module-level
    functions (same pattern as the Tesco/Sainsbury's adapters)."""
    key = 'asda'
    name = 'Asda'

    # No sign-in flow: guest baskets only.
    supports_auth = False

    def _fn(self, name):
        return globals()[name]

    def search(self, query, limit=5):
        return self._fn('search')(query, limit=limit)

    def get_product(self, sku):
        return self._fn('get_product')(sku)

    def auth_status(self):
        return self._fn('auth_status')()

    def basket(self):
        return self._fn('basket')()

    def basket_set(self, sku, qty):
        return self._fn('basket_set')(sku, qty)

    def checkout_url(self):
        return self._fn('checkout_url')()

    def parse_qty(self, quantity_text):
        return self._fn('parse_qty')(quantity_text)
