"""Sainsbury's integration via the open-supermarkets library (MIT).

The JS provider is imported directly (node -e) rather than driven through
the CLI: it exposes a typed API (search/getProduct/basket/...) and its
session handling is a plain file at ~/.sainsburys/session.json.

Capability notes (verified 2026-08-29):
  * Catalogue search + basket READ work with no sign-in at all.
  * Basket WRITES need a Sainsbury's account (401 otherwise).
  * Delivery slots / checkout are browser-driven in the library and are not
    wired into the app; checkout hands off to the website instead
    (same pattern as Tesco).
"""
import json
import os
import subprocess
import threading
from datetime import datetime, timezone

import datadir
from providers import Grocer, GrocerError
from providers.tesco import _display_env, _no_window

BASE_DIR = datadir.resource_dir()
NODE = datadir.node_executable() or 'node'
LOGIN_SCRIPT = os.path.join(BASE_DIR, 'scripts', 'sainsburys_login.js')
SESSION_FILE = os.path.expanduser('~/.sainsburys/session.json')
CHECKOUT_URL = 'https://www.sainsburys.co.uk/gol-ui/checkout'

_login_state = {'running': False}


class SainsburysError(GrocerError):
    pass


def _run_js(js, timeout=90):
    """Execute a JS snippet in node with the project's node_modules on the
    require path. Returns stdout; raises SainsburysError on failure."""
    if NODE is None or not os.path.exists(NODE):
        raise SainsburysError('the bundled Node runtime is missing - reinstall the app')
    try:
        proc = subprocess.run(
            [NODE, '-e', js],
            capture_output=True, text=True, timeout=timeout, cwd=BASE_DIR,
            env=_display_env(), creationflags=_no_window(),
        )
    except subprocess.TimeoutExpired:
        raise SainsburysError('Sainsbury\'s API timed out')
    except Exception as exc:
        raise SainsburysError(str(exc))
    if proc.returncode != 0:
        raise SainsburysError((proc.stderr or proc.stdout or 'no output').strip()[:300])
    return proc.stdout


def _api(action, payload=None):
    """One call into the open-supermarkets Sainsbury's provider.

    `action` is a JS expression evaluated with `provider` bound; its value
    is resolved (if a Promise), stringified and returned as stdout.
    """
    js = (
        "const {SainsburysProvider} = require('open-supermarkets/dist/providers/sainsburys');"
        "const provider = new SainsburysProvider();"
        f"const out = {action};"
        "Promise.resolve(out).then(v => {process.stdout.write(JSON.stringify(v));"
        " process.exit(0);}).catch(e => {process.stderr.write(String(e && e.message || e));"
        " process.exit(1);});"
    )
    stdout = _run_js(js, timeout=120)
    try:
        return json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        raise SainsburysError('Could not parse Sainsbury\'s API output')


def _product(p):
    """Map a library product onto the shared product-dict shape."""
    price = p.get('retail_price') or {}
    unit = p.get('unit_price') or {}
    uid = p.get('product_uid')
    return {
        'sku': str(uid) if uid is not None else '',
        'title': p.get('name') or '',
        'brand': '',  # the library exposes no separate brand field
        'price': price.get('price'),
        'unit_price': unit.get('price'),
        'unit_of_measure': unit.get('measure') or '',
        'image_url': p.get('image_url') or '',
        'on_offer': False,
    }


def search(query, limit=5):
    """Search the Sainsbury's catalogue. Returns shared-shape product dicts."""
    products = _api(f"provider.search({json.dumps(query)})") or []
    return [_product(p) for p in products[:limit]]


def get_product(sku):
    """Look up one product by SKU (product_uid)."""
    product = _api(f"provider.getProduct({json.dumps(str(sku).strip())})")
    if not product:
        raise SainsburysError('Sainsbury\'s product not found')
    return _product(product)


def auth_status():
    """Signed in when the session file exists, is unexpired, and carries the
    WC_AUTHENTICATION_* cookie. Cheap/safe - templates call this."""
    if not os.path.exists(SESSION_FILE):
        return {'signed_in': False}
    try:
        with open(SESSION_FILE) as fh:
            session = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {'signed_in': False}
    # expiresAt is an ISO-8601 UTC timestamp like 2026-08-29T23:20:00.000Z
    expires = session.get('expiresAt')
    if expires:
        try:
            parsed = datetime.fromisoformat(expires.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > parsed:
                return {'signed_in': False}
        except ValueError:
            return {'signed_in': False}
    cookies = session.get('cookies') or []
    if isinstance(cookies, str):
        return {'signed_in': 'WC_AUTHENTICATION_' in cookies}
    return {'signed_in': any(str(c.get('name', '')).startswith('WC_AUTHENTICATION_')
                             for c in cookies)}


def login():
    """Start an interactive sign-in in a background thread.

    Opens a real Chromium window on this machine; a human completes the
    Sainsbury's sign-in (including any MFA code). The script polls for the
    authentication cookie and writes ~/.sainsburys/session.json. Call
    login_status() to poll progress.
    """
    if _login_state['running']:
        return False
    _login_state.update({'running': True, 'done': False, 'ok': False, 'output': ''})

    def _worker():
        if not os.path.exists(LOGIN_SCRIPT):
            _login_state.update({
                'ok': False, 'done': True,
                'output': 'scripts/sainsburys_login.js is missing - reinstall the app',
            })
            return
        if not datadir.find_chrome():
            _login_state.update({
                'ok': False, 'done': True,
                'output': 'Google Chrome was not found on this computer - install it from google.com/chrome to sign in to Sainsbury\'s',
            })
            return
        try:
            proc = subprocess.run(
                [NODE, LOGIN_SCRIPT],
                capture_output=True, text=True, timeout=620, cwd=BASE_DIR,
                env=_display_env(), creationflags=_no_window(),
            )
            _login_state['ok'] = proc.returncode == 0 and os.path.exists(SESSION_FILE)
            _login_state['output'] = (proc.stdout or proc.stderr or '').strip()[-500:]
        except subprocess.TimeoutExpired:
            _login_state['ok'] = False
            _login_state['output'] = 'Sign-in timed out (10 minutes) - no Sainsbury\'s sign-in was detected in the browser window'
        except Exception as exc:
            _login_state['ok'] = False
            _login_state['output'] = str(exc)
        finally:
            _login_state.update({'running': False, 'done': True})

    threading.Thread(target=_worker, daemon=True).start()
    return True


def login_status():
    return dict(_login_state)


def basket():
    """Return the remote basket contents:
    {'items': [{item_id, sku, title, qty, unit_price, total}],
     'total_qty', 'total_cost'}
    """
    data = _api('provider.getBasket()') or {}
    def _uid(i, key):
        v = i.get(key)
        return str(v) if v is not None else ''

    items = [{
        'item_id': _uid(i, 'item_id'),
        'sku': _uid(i, 'product_uid'),
        'title': i.get('name') or '',
        'qty': i.get('quantity') or 0,
        'unit_price': i.get('unit_price'),
        'total': i.get('total_price'),
    } for i in data.get('items') or []]
    return {
        'items': items,
        'total_qty': data.get('total_quantity') or 0,
        'total_cost': data.get('total_cost') or 0,
    }


def basket_set(sku, qty):
    """Set a basket line to an exact quantity (0 removes it).

    The library's basket API adds or replaces a line but can only decrease
    by item_uid, so this does one GET (for the current line) plus the
    minimal POST/PUT to reach `qty` - all within a single node process.
    """
    js = (
        "const {SainsburysProvider} = require('open-supermarkets/dist/providers/sainsburys');"
        "const provider = new SainsburysProvider();"
        "const sku = " + json.dumps(str(sku)) + ";"
        "const target = " + str(int(qty)) + ";"
        "const pickTime = new Date(Date.now() + 86400000).toISOString();"
        "const params = {pick_time: pickTime, store_number: "
        "JSON.stringify(process.env.SAINSBURYS_STORE_NUMBER || '0560'), slot_booked: 'false'};"
        "(async () => {"
        "  let item = null;"
        "  try {"
        "    const current = await provider.client.get('/basket/v2/basket', {params});"
        "    item = (current.data.items || []).find(i => String(i.product && i.product.sku) === String(sku));"
        "  } catch (e) { /* basket unreadable - treat as empty */ }"
        "  const current = item ? item.quantity : 0;"
        "  if (target > current) {"
        "    await provider.client.post('/basket/v2/basket/item',"
        "      {product_uid: sku, quantity: target - current, uom: 'ea', selected_catchweight: ''}, {params});"
        "  } else if (target < current) {"
        "    await provider.client.put('/basket/v2/basket',"
        "      {items: [{product_uid: sku, quantity: target, uom: 'ea', selected_catchweight: '',"
        "        item_uid: item.item_uid, decreasing_quantity: target < current}]}, {params});"
        "  }"
        "  process.exit(0);"
        "})().catch(e => {process.stderr.write(String(e && e.message || e)); process.exit(1);});"
    )
    _run_js(js, timeout=120)
    return None


def checkout_url():
    """Hand the user off to the website for slots + payment."""
    return CHECKOUT_URL


class SainsburysGrocer(Grocer):
    """Registry adapter exposing the open-supermarkets backend on the Grocer
    interface. Methods do a call-time lookup into this module's globals so
    tests (and anything else) can monkeypatch the module-level functions."""
    key = 'sainsburys'
    name = "Sainsbury's"

    def _fn(self, name):
        return globals()[name]

    def search(self, query, limit=5):
        return self._fn('search')(query, limit=limit)

    def get_product(self, sku):
        return self._fn('get_product')(sku)

    def auth_status(self):
        return self._fn('auth_status')()

    def login(self):
        return self._fn('login')()

    def login_status(self):
        return self._fn('login_status')()

    def basket(self):
        return self._fn('basket')()

    def basket_set(self, sku, qty):
        return self._fn('basket_set')(sku, qty)

    def checkout_url(self):
        return self._fn('checkout_url')()
