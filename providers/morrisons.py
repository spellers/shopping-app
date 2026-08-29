"""Morrisons integration (multi-grocer plan, step 5) - in-house backend.

Everything runs over plain HTTP (stdlib urllib) - no browser, no node,
no sign-in.
Verified 2026-08-29 against groceries.morrisons.com:

* Catalogue search -
  GET /api/webproductpagews/v6/product-pages/search?q=...&maxPageSize=300&maxProductsToDecorate=200
  Results are nested: productGroups[].decoratedProducts[].
* Product lookup - no by-id endpoint exists (all guesses 404), but
  searching for the numeric retailerProductId returns exactly that
  product, so the numeric id is used as the SKU.
* Basket - guest cart tied to the VISITORID cookie (no account needed):
  - read:  GET  /api/cart/v1/carts/active
  - write: POST /api/cart/v1/carts/active/apply-quantity with a raw array
           body [{"productId": <uuid>, "quantity": <delta>}] plus an
           x-csrf-token header. The token is embedded in the homepage
           HTML JSON: "csrf":{"token":"..."}. Missing/incorrect token
           returns 403 with error code ecom-csrf-failure (that was the
           403 seen with bare curl during recon - it was CSRF, not a WAF).
  - apply-quantity is ADDITIVE (it applies a delta), so basket_set must
    read the cart first and compute the delta; a negative delta clears.

Checkout hands off to the website (same pattern as Tesco/Asda).
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from providers import Grocer, GrocerError

BASE = 'https://groceries.morrisons.com'
SEARCH_URL = BASE + '/api/webproductpagews/v6/product-pages/search'
CART_URL = BASE + '/api/cart/v1/carts/active'
CHECKOUT_URL = BASE + '/checkout'

# The guest cart is tied to the VISITORID cookie, which is only held in
# memory by the session object - without persisting it, an app restart
# would start a fresh (empty) cart.
_STATE_FILE = os.path.expanduser('~/.morrisons/cookies.json')

HEADERS = {
    'user-agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'),
    'accept': 'application/json',
}


class MorrisonsError(GrocerError):
    pass


class _Session:
    """One HTTP session: guest cart cookies + a cached CSRF token."""

    def __init__(self, timeout=25, state_file=_STATE_FILE):
        self.cookies = {}
        self.timeout = timeout
        self._csrf = None
        self._state_file = state_file
        self._load_state()

    def _load_state(self):
        try:
            with open(self._state_file) as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                self.cookies = {str(k): str(v) for k, v in saved.items()}
        except (OSError, ValueError):
            pass

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
            with open(self._state_file, 'w') as f:
                json.dump(self.cookies, f)
        except OSError:
            pass  # persistence is best-effort; the session still works

    def _headers(self):
        h = dict(HEADERS)
        if self.cookies:
            h['cookie'] = '; '.join(f'{k}={v}' for k, v in self.cookies.items())
        return h

    def _absorb_cookies(self, resp):
        for pair in resp.headers.get_all('Set-Cookie') or []:
            key, _, rest = pair.partition('=')
            value = rest.split(';')[0].strip()
            if key:
                self.cookies[key] = value
        if self.cookies:
            self._save_state()

    def request(self, url, method='GET', body=None, extra=None):
        h = self._headers()
        if extra:
            h.update(extra)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        if data is not None:
            req.add_header('content-type', 'application/json')
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = ''
            try:
                detail = exc.read().decode(errors='replace')[:200]
            except Exception:
                pass
            raise MorrisonsError(
                f'Morrisons returned HTTP {exc.code} '
                f'({" ".join(detail.split())})')
        except Exception as exc:
            raise MorrisonsError(f'Morrisons request failed: {exc}')
        self._absorb_cookies(resp)
        return resp.read()

    def csrf(self):
        """Fetch (or reuse) the CSRF token from the homepage."""
        if self._csrf:
            return self._csrf
        html = self.request(BASE + '/', extra={'accept': 'text/html'})
        m = re.search(rb'"csrf"\s*:\s*\{"token"\s*:\s*"([^"]+)"', html)
        if not m:
            raise MorrisonsError(
                'Could not find the CSRF token in the Morrisons homepage')
        self._csrf = m.group(1).decode()
        return self._csrf

    def basket_headers(self):
        return {
            'origin': BASE,
            'referer': BASE + '/',
            'x-csrf-token': self.csrf(),
        }


_SESSION = _Session()


def _amount(value):
    """Morrisons price objects {"currency","amount"} -> float or None."""
    if isinstance(value, dict):
        value = value.get('amount')
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unit_name(unit):
    """'PER_LITRE' / 'fop.price.per.litre' -> 'per litre' (or '')."""
    if not unit:
        return ''
    m = re.search(r'per[_\.]([A-Za-z0-9]+)$', str(unit), re.I)
    return f'per {m.group(1).lower()}' if m else ''


def _product(p):
    """Map a decoratedProducts entry onto the shared product-dict shape."""
    unit = (p.get('unitPrice') or {})
    return {
        'sku': str(p.get('retailerProductId') or p.get('productId') or ''),
        'title': p.get('name') or '',
        'brand': p.get('brand') or '',
        'price': _amount(p.get('price')),
        'unit_price': _amount(unit.get('price')),
        'unit_of_measure': _unit_name(unit.get('unitName') or unit.get('unit')),
        'image_url': ((p.get('image') or {}).get('src') or ''),
        'on_offer': bool(p.get('promoPrice')),
    }


def _search_products(query):
    """One catalogue search. Returns the flattened decoratedProducts list."""
    params = urllib.parse.urlencode({
        'q': query, 'maxPageSize': 300, 'maxProductsToDecorate': 200,
    })
    payload = _SESSION.request(f'{SEARCH_URL}?{params}')
    try:
        data = json.loads(payload)
    except ValueError:
        raise MorrisonsError('Could not parse the Morrisons search response')
    products = []
    for group in data.get('productGroups') or []:
        products.extend(group.get('decoratedProducts') or [])
    return products


def _uuid_for(sku, session=None):
    """Resolve a SKU to the UUID productId the cart API wants.

    UUIDs pass through; anything else (numeric retailerProductId) is
    resolved with a single search call - that is the only by-id lookup
    the site exposes."""
    session = session or _SESSION
    sku = str(sku).strip()
    if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', sku):
        return sku
    hits = _search_products(sku)
    for p in hits:
        if str(p.get('retailerProductId')) == sku:
            return p.get('productId')
    raise MorrisonsError(f'Morrisons product not found: {sku}')


def search(query, limit=5):
    """Search the Morrisons catalogue. Returns shared-shape product dicts."""
    products = _search_products(query)
    return [_product(p) for p in products[:max(limit, 1)]]


def get_product(sku):
    """Look up one product by its numeric id (or exact name as fallback)."""
    sku = str(sku).strip()
    hits = _search_products(sku)
    if sku.isdigit():
        for p in hits:
            if str(p.get('retailerProductId')) == sku:
                return _product(p)
        raise MorrisonsError(f'Morrisons product not found: {sku}')
    if hits:
        return _product(hits[0])
    raise MorrisonsError(f'Morrisons product not found: {sku}')


def _http_error(exc, detail=''):
    raise MorrisonsError(
        f'Morrisons returned HTTP {exc.code} '
        f'({" ".join(detail.split())})')


def _cart_items(session=None):
    session = session or _SESSION
    try:
        payload = session.request(CART_URL)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode(errors='replace')[:200]
        except Exception:
            detail = ''
        _http_error(exc, detail)
    try:
        data = json.loads(payload)
    except ValueError:
        raise MorrisonsError('Could not parse the Morrisons cart response')
    return data.get('items') or []


def basket():
    """Return the remote Morrisons guest cart contents (shared shape)."""
    items = []
    total_qty = 0
    total_cost = 0.0
    for item in _cart_items():
        qty = item.get('quantity') or 0
        price = _amount(item.get('finalPrice'))
        total_qty += qty
        total_cost += (price or 0) * qty
        items.append({
            'sku': str(item.get('productId') or ''),
            'title': '',
            'price': price,
            'quantity': qty,
        })
    return {'items': items, 'total_qty': total_qty,
            'total_cost': round(total_cost, 2)}


def basket_set(sku, qty):
    """Set a basket line to an exact quantity (0 removes it).

    apply-quantity is additive, so: read the cart, compute the delta
    against the current line, POST the delta.
    """
    qty = int(qty)
    uuid = _uuid_for(sku)
    current = 0
    for item in _cart_items():
        if item.get('productId') == uuid:
            current = item.get('quantity') or 0
            break
    delta = qty - current
    if delta:
        try:
            _SESSION.request(
                CART_URL + '/apply-quantity',
                method='POST',
                body=[{'productId': uuid, 'quantity': delta}],
                extra=_SESSION.basket_headers(),
            )
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode(errors='replace')[:200]
            except Exception:
                detail = ''
            _http_error(exc, detail)
    return None


def auth_status():
    """Guest cart, no sign-in flow (same as Asda)."""
    return {'signed_in': True,
            'note': 'Morrisons shopping uses a guest session - no sign-in needed'}


def checkout_url():
    """Hand the user off to the Morrisons website for slots + payment."""
    return CHECKOUT_URL


def parse_qty(quantity_text):
    """Extract an integer count from free-text recipe quantities."""
    m = re.search(r'\d+', str(quantity_text or ''))
    return int(m.group()) if m else 1


class MorrisonsGrocer(Grocer):
    """Registry adapter for the Morrisons backend. Methods do a call-time
    lookup into this module's globals so tests can monkeypatch the
    module-level functions (same pattern as the other providers)."""
    key = 'morrisons'
    name = 'Morrisons'

    # No sign-in flow: guest cart only.
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
