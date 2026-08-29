"""Waitrose integration (multi-grocer plan, step 6) - in-house backend.

Everything runs over plain HTTP (stdlib urllib) - no browser, no node.
API map reverse-engineered from the official Android app (same source as
the maintained jingkaihe/waitrose Go client, cloned under
recon/waitrose/lib for reference; its GraphQL operations are the
canonical shapes below).

Endpoints (all www.waitrose.com):
* GraphQL:    POST /api/graphql-prod/graph/live
  - login:    mutation NewSession($input: SessionInput) with
              {username, password, clientId: "ANDROID_APP"} ->
              accessToken / refreshToken / customerId / customerOrderId /
              defaultBranchId / expiresIn. No MFA.
  - trolley:  query GetTrolley($orderId: ID!) and
              mutation UpdateTrolleyItems($trolleyItemsInput, $orderId)
              - items are ABSOLUTE quantities (0 removes a line)
* Search:     POST /api/content-prod/v2/cms/publish/productcontent/search/
              {customerId}?clientType=WEB_APP
              body {"customerSearchRequest": {"queryParams": {
                    "searchTerm": q, "start": 0, "branchId": <default>}}}
              results: componentsAndProducts[].searchProduct
              (id = "lineNumber-xxx-xxx", lineNumber, name, displayPrice,
               size, brand)
* Guest requests use "Authorization: Bearer unauthenticated", but search
  and the trolley both require a real session (customerId /
  customerOrderId), so sign-in is mandatory.

Auth model: the app's login flow (browser + polling) doesn't fit a
pure email/password API, so credentials are stored once in
~/.waitrose/credentials.json ({"email": ..., "password": ...}) and
login() exchanges them in a background thread; login_status() reports
progress. Sessions are persisted to ~/.waitrose/session.json with an
expiry; expired sessions are refreshed with the refresh token.

Checkout hands off to the website (same pattern as Tesco/Asda/Morrisons).
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from providers import Grocer, GrocerError

BASE = 'https://www.waitrose.com'
GQL_URL = BASE + '/api/graphql-prod/graph/live'
SEARCH_URL = BASE + ('/api/content-prod/v2/cms/publish/productcontent/search/'
                     '{customer_id}?clientType=WEB_APP')
CHECKOUT_URL = BASE + '/'

_STATE_DIR = os.path.expanduser('~/.waitrose')
_SESSION_FILE = os.path.join(_STATE_DIR, 'session.json')
_CREDENTIALS_FILE = os.path.join(_STATE_DIR, 'credentials.json')

HEADERS = {
    'user-agent': 'okhttp/4.12.0',
    'accept': 'application/json',
    'client-correlation-id': 'shopping-app',
    'breadcrumb': 'shopping-app',
}

NEW_SESSION = '''mutation NewSession($input: SessionInput) {
  generateSession(session: $input) {
    accessToken refreshToken customerId customerOrderId
    customerOrderState defaultBranchId expiresIn
    failures { type message }
  }
}'''

REFRESH_SESSION = '''mutation RefreshSession($input: SessionInput) {
  generateSession(session: $input) {
    accessToken refreshToken customerId customerOrderId
    customerOrderState defaultBranchId expiresIn
    failures { type message }
  }
}'''

GET_TROLLEY = '''query GetTrolley($orderId: ID!) {
  getTrolley(orderId: $orderId) {
    products { id lineNumber name displayPrice }
    trolley {
      orderId
      trolleyItems {
        lineNumber
        quantity { amount uom }
        totalPrice { amount currencyCode }
      }
      trolleyTotals { totalEstimatedCost { amount currencyCode } }
    }
    failures { type message }
  }
}'''

UPDATE_TROLLEY = '''mutation UpdateTrolleyItems($trolleyItemsInput: [TrolleyItemInput!], $orderId: ID!) {
  updateTrolleyItems(trolleyItems: $trolleyItemsInput, orderId: $orderId) {
    products { id lineNumber name displayPrice }
    trolley {
      orderId
      trolleyItems {
        lineNumber
        quantity { amount uom }
        totalPrice { amount currencyCode }
      }
      trolleyTotals { totalEstimatedCost { amount currencyCode } }
    }
    failures { type message }
  }
}'''


class WaitroseError(GrocerError):
    pass


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f)
        os.chmod(path, 0o600)
    except OSError:
        pass  # persistence is best-effort; the session still works in memory


class _Session:
    """Holds the Waitrose auth session (tokens + ids) with expiry and
    refresh, persisted to ~/.waitrose/session.json."""

    def __init__(self, session_file=_SESSION_FILE, timeout=25):
        self.timeout = timeout
        self._session_file = session_file
        self.data = _read_json(session_file) or {}
        if not self.data.get('accessToken'):
            self.data = {}

    @property
    def access_token(self):
        return self.data.get('accessToken') or ''

    @property
    def customer_id(self):
        return self.data.get('customerId') or ''

    @property
    def order_id(self):
        return self.data.get('customerOrderId') or ''

    @property
    def branch_id(self):
        return self.data.get('defaultBranchId') or ''

    @property
    def signed_in(self):
        return bool(self.data.get('accessToken'))

    @property
    def expired(self):
        return bool(self.data) and time.time() > float(self.data.get('expiresAt') or 0)

    def store(self, payload):
        """payload: the GraphQL generateSession object."""
        failures = payload.get('failures') or []
        if failures:
            raise WaitroseError(
                'Waitrose sign-in failed: '
                + ' - '.join(f.get('message') or f.get('type') or ''
                             for f in failures).strip())
        expires_in = payload.get('expiresIn')
        self.data = {
            'accessToken': payload.get('accessToken') or '',
            'refreshToken': payload.get('refreshToken') or '',
            'customerId': payload.get('customerId') or '',
            'customerOrderId': payload.get('customerOrderId') or '',
            'customerOrderState': payload.get('customerOrderState') or '',
            'defaultBranchId': payload.get('defaultBranchId') or '',
            'expiresAt': time.time() + (int(expires_in) if expires_in else 3600),
        }
        _write_json(self._session_file, self.data)
        return self.data

    def refresh(self):
        """Re-issue the session using the refresh token. Raises on failure."""
        variables = {'input': {'clientId': 'ANDROID_APP',
                               'customerId': self.customer_id}}
        result = _graphql(REFRESH_SESSION, variables,
                          auth_token=self.data.get('refreshToken') or '')
        return self.store(result)

    def require(self):
        """Ensure a usable session, refreshing once if expired.
        Raises WaitroseError when no session exists at all."""
        if not self.signed_in:
            raise WaitroseError('Not signed in to Waitrose')
        if self.expired:
            try:
                self.refresh()
            except WaitroseError as exc:
                raise WaitroseError(
                    f'Waitrose session expired and the refresh failed '
                    f'({exc}) - sign in again')
        return self


def _graphql(query, variables, auth_token='unauthenticated', timeout=25):
    """One GraphQL call. Returns the top-level mutation/query object."""
    body = json.dumps({'query': query, 'variables': variables}).encode()
    headers = dict(HEADERS)
    headers['content-type'] = 'application/json'
    headers['authorization'] = 'Bearer ' + auth_token
    req = urllib.request.Request(GQL_URL, data=body, headers=headers,
                                 method='POST')
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = _http_detail(exc)
        raise WaitroseError(
            f'Waitrose returned HTTP {exc.code} ({detail})')
    except Exception as exc:
        raise WaitroseError(f'Waitrose request failed: {exc}')
    raw = resp.read()
    try:
        data = json.loads(raw)
    except ValueError:
        raise WaitroseError('Could not parse the Waitrose response')
    errors = data.get('errors') or []
    if errors and not data.get('data'):
        raise WaitroseError(
            'Waitrose error: ' + '; '.join(e.get('message') or ''
                                            for e in errors).strip())
    node = (data.get('data') or {}).get('generateSession')
    if node is not None:
        return node
    # trolley queries: return the whole data object
    return data.get('data') or {}


def _http_detail(exc):
    try:
        text = exc.read().decode(errors='replace')
        try:
            parsed = json.loads(text)
            errors = parsed.get('errors') or []
            if errors:
                return '; '.join(e.get('message') or '' for e in errors)
        except ValueError:
            pass
        return ' '.join(text.split())[:200]
    except Exception:
        return ''


_SESSION = _Session()


# ---------------------------------------------------------------- search

def _search_raw(term, start=0):
    """One catalogue search. Returns the componentsAndProducts list."""
    session = _SESSION.require()
    url = SEARCH_URL.format(customer_id=session.customer_id)
    body = {'customerSearchRequest': {'queryParams': {
        'searchTerm': term,
        'start': start,
        **({'branchId': session.branch_id} if session.branch_id else {}),
        **({'orderId': int(session.order_id)} if session.order_id
           and session.order_id.isdigit() else {}),
    }}}
    headers = dict(HEADERS)
    headers['content-type'] = 'application/json'
    headers['authorization'] = 'Bearer ' + session.access_token
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=headers, method='POST')
    try:
        resp = urllib.request.urlopen(req, timeout=_SESSION.timeout)
    except urllib.error.HTTPError as exc:
        raise WaitroseError(
            f'Waitrose returned HTTP {exc.code} ({_http_detail(exc)})')
    except Exception as exc:
        raise WaitroseError(f'Waitrose request failed: {exc}')
    try:
        data = json.loads(resp.read())
    except ValueError:
        raise WaitroseError('Could not parse the Waitrose search response')
    return data.get('componentsAndProducts') or []


def _product(component):
    p = component.get('searchProduct') or {}
    price = None
    raw_price = p.get('displayPrice')
    if isinstance(raw_price, (int, float)):
        price = float(raw_price)
    elif isinstance(raw_price, str):
        m = re.search(r'\d+(?:\.\d+)?', raw_price)
        price = float(m.group()) if m else None
    return {
        'sku': p.get('id') or '',
        'title': p.get('name') or '',
        'brand': p.get('brand') or '',
        'price': price,
        'unit_price': None,
        'unit_of_measure': p.get('size') or '',
        'image_url': '',
        'on_offer': False,
    }


def search(query, limit=5):
    """Search the Waitrose catalogue. Returns shared-shape product dicts."""
    components = _search_raw(query)
    products = [_product(c) for c in components if c.get('searchProduct')]
    return products[:max(limit, 1)]


def get_product(sku):
    """Look up one product by its search id ("lineNumber-xxx-xxx") or by
    exact name. The API has no by-id product endpoint - search is the
    only lookup path (same situation as Morrisons)."""
    sku = str(sku).strip()
    components = _search_raw(sku)
    for c in components:
        p = c.get('searchProduct') or {}
        if p.get('id') == sku:
            return _product(c)
    hits = [_product(c) for c in components if c.get('searchProduct')]
    if hits:
        return hits[0]
    raise WaitroseError(f'Waitrose product not found: {sku}')


# ---------------------------------------------------------------- basket

def _trolley():
    """The GetTrolley data object (products + trolley + failures)."""
    session = _SESSION.require()
    data = _graphql(GET_TROLLEY, {'orderId': session.order_id},
                    auth_token=session.access_token)
    node = data.get('getTrolley') if isinstance(data, dict) else None
    if node is None:
        raise WaitroseError('Could not read the Waitrose trolley')
    failures = node.get('failures') or []
    if failures:
        raise WaitroseError(
            'Waitrose trolley error: '
            + ' - '.join(f.get('message') or f.get('type') or ''
                         for f in failures).strip())
    return node


def basket():
    """Return the Waitrose trolley contents (shared shape)."""
    node = _trolley()
    products = {p.get('lineNumber'): p for p in node.get('products') or []}
    trolley = node.get('trolley') or {}
    items = []
    total_cost = 0.0
    for line in trolley.get('trolleyItems') or []:
        qty = (line.get('quantity') or {}).get('amount')
        qty = float(qty) if qty is not None else 0
        total = (line.get('totalPrice') or {}).get('amount')
        cost = float(total) if total is not None else 0.0
        total_cost += cost
        prod = products.get(line.get('lineNumber')) or {}
        items.append({
            'sku': prod.get('id') or line.get('lineNumber') or '',
            'title': prod.get('name') or '',
            'price': (cost / qty) if qty else None,
            'quantity': int(qty) if float(qty).is_integer() else qty,
        })
    return {'items': items, 'total_qty': sum(i['quantity'] for i in items),
            'total_cost': round(total_cost, 2)}


def basket_set(sku, qty):
    """Set a trolley line to an exact quantity (0 removes it).

    The API takes ABSOLUTE quantities. The trolley item input wants the
    lineNumber (first dash-segment) and the full product id.
    """
    qty = int(qty)
    sku = str(sku).strip()
    if '-' not in sku:
        # bare lineNumber given
        line_number, product_id = sku, sku
    else:
        line_number, product_id = sku.split('-', 1)[0], sku
    session = _SESSION.require()
    items = [{'lineNumber': line_number, 'productId': product_id,
              'quantity': {'amount': qty}}]
    data = _graphql(UPDATE_TROLLEY,
                    {'trolleyItemsInput': items,
                     'orderId': session.order_id},
                    auth_token=session.access_token)
    node = data.get('updateTrolleyItems') if isinstance(data, dict) else None
    if node is None:
        raise WaitroseError('Could not update the Waitrose trolley')
    failures = node.get('failures') or []
    if failures:
        raise WaitroseError(
            'Waitrose trolley error: '
            + ' - '.join(f.get('message') or f.get('type') or ''
                         for f in failures).strip())
    return None


# ------------------------------------------------------------------ auth

def auth_status():
    """Signed in iff a session exists (refreshed transparently on use)."""
    signed_in = _SESSION.signed_in
    note = ''
    if signed_in:
        note = f'Signed in as a Waitrose customer (order { _SESSION.order_id or "?"})'
    elif _read_json(_CREDENTIALS_FILE):
        note = 'Saved credentials found - start sign-in to refresh the session'
    else:
        note = (f'No Waitrose session - save credentials to '
                f'{_CREDENTIALS_FILE} then start sign-in')
    return {'signed_in': signed_in, 'note': note}


def save_credentials(email, password):
    """Store the customer's Waitrose email + password so sign-in is one
    click. Written with 0600 permissions (password in the clear on disk -
    same trust model as the other providers' session files)."""
    email = (email or '').strip()
    password = password or ''
    if not email or not password:
        raise WaitroseError('Enter both email and password')
    os.makedirs(_STATE_DIR, exist_ok=True)
    fd = os.open(_CREDENTIALS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as fh:
        json.dump({'email': email, 'password': password}, fh)
    return True


# background login state (polled by the app like the other providers)
_LOGIN_LOCK = threading.Lock()
_LOGIN_STATE = {'running': False, 'error': '', 'note': ''}


def _finish_login(running=False, error='', note=''):
    # mutate in place (never rebind) so login_status() always sees it
    _LOGIN_STATE.update({'running': running, 'error': error, 'note': note})


def _run_login():
    try:
        creds = _read_json(_CREDENTIALS_FILE)
        if not (creds or {}).get('email') or not (creds or {}).get('password'):
            raise WaitroseError(
                f'No credentials found - create {_CREDENTIALS_FILE} with '
                f'{{"email": "...", "password": "..."}} and try again')
        payload = _graphql(
            NEW_SESSION,
            {'input': {'username': creds['email'],
                       'password': creds['password'],
                       'clientId': 'ANDROID_APP'}})
        _SESSION.store(payload)
        _finish_login(note='Signed in to Waitrose')
    except WaitroseError as exc:
        _finish_login(error=str(exc))
    except Exception as exc:
        _finish_login(error=f'Waitrose sign-in failed: {exc}')


def login():
    """Exchange the saved credentials for a session (background thread)."""
    with _LOGIN_LOCK:
        if _LOGIN_STATE.get('running'):
            return False
        _finish_login(running=True, note='Signing in to Waitrose...')
        threading.Thread(target=_run_login, daemon=True).start()
        return True


def login_status():
    return dict(_LOGIN_STATE)


def checkout_url():
    """Hand the user off to the Waitrose website for slots + payment."""
    return CHECKOUT_URL


def parse_qty(quantity_text):
    """Extract an integer count from free-text recipe quantities."""
    m = re.search(r'\d+', str(quantity_text or ''))
    return int(m.group()) if m else 1


class WaitroseGrocer(Grocer):
    """Registry adapter for the Waitrose backend. Methods do a call-time
    lookup into this module's globals so tests can monkeypatch the
    module-level functions (same pattern as the other providers)."""
    key = 'waitrose'
    name = 'Waitrose'

    supports_auth = True

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

    def save_credentials(self, email, password):
        return self._fn('save_credentials')(email, password)

    def basket(self):
        return self._fn('basket')()

    def basket_set(self, sku, qty):
        return self._fn('basket_set')(sku, qty)

    def checkout_url(self):
        return self._fn('checkout_url')()

    def parse_qty(self, quantity_text):
        return self._fn('parse_qty')(quantity_text)
