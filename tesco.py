"""Tesco integration via the basketeer CLI (node_modules/.bin/basketeer).

All Tesco API access goes through this module so the rest of the app never
touches the CLI directly. Every function raises TescoError on failure.
"""
import json
import os
import re
import subprocess
import threading
import time

import datadir

BASE_DIR = datadir.resource_dir()
CLI = os.path.join(BASE_DIR, 'node_modules', '.bin', 'basketeer')
LOGIN_SCRIPT = os.path.join(BASE_DIR, 'scripts', 'tesco_login.js')
NODE = datadir.node_executable() or 'node'
# The basketeer CLI hard-codes this path (no env override), so the session
# and Chrome profile must live in the standard location for the CLI and the
# login script to agree.
SESSION_FILE = os.path.expanduser('~/.basketeer/session.json')

_login_state = {'running': False}


class TescoError(Exception):
    pass


def _run(args, timeout=90):
    if not os.path.exists(CLI):
        raise TescoError('basketeer CLI not found - run: npm install (in project dir)')
    try:
        # Auth refreshes launch a headed Chrome inside the CLI; without DISPLAY
        # (e.g. app started from systemd after a reboot) that launch dies with
        # 'Target page, context or browser has been closed'.
        proc = subprocess.run(
            [CLI] + args,
            capture_output=True, text=True, timeout=timeout, cwd=BASE_DIR,
            env=_display_env(),
        )
    except subprocess.TimeoutExpired:
        raise TescoError('Tesco API timed out')
    except Exception as exc:
        raise TescoError(str(exc))
    return proc


def _json_output(args, timeout=90):
    proc = _run(args, timeout=timeout)
    stdout = (proc.stdout or '').strip()
    # CLI may print warnings before the JSON blob
    start = stdout.find('{')
    if start == -1:
        raise TescoError(f'Tesco CLI failed: {(proc.stderr or stdout or "no output").strip()[:300]}')
    try:
        return json.loads(stdout[start:])
    except json.JSONDecodeError:
        raise TescoError('Could not parse Tesco CLI output')


def search(query, limit=5):
    """Search the Tesco catalogue. Returns a list of product dicts:
    {sku, title, brand, price, unit_price, unit_of_measure, image_url, on_offer}
    """
    data = _json_output(['search', query, '--limit', str(limit)])
    results = []
    for r in data.get('results', []):
        price = r.get('price') or {}
        results.append({
            'sku': str(r.get('sku') or ''),
            'title': r.get('title') or '',
            'brand': r.get('brand') or '',
            'price': price.get('actual'),
            'unit_price': price.get('unitPrice'),
            'unit_of_measure': price.get('unitOfMeasure'),
            'image_url': r.get('imageUrl') or '',
            'on_offer': bool(r.get('onOffer')),
        })
    # The CLI's --limit flag is soft (may return more), so enforce it here.
    return results[:limit]


def get_product(sku):
    """Look up a single product by SKU. Returns the same dict shape as
    search() results, or raises TescoError if the SKU is unknown."""
    data = _json_output(['product', str(sku).strip()])
    price = data.get('price') or {}
    return {
        'sku': str(data.get('sku') or sku),
        'title': data.get('title') or '',
        'brand': data.get('brand') or '',
        'price': price.get('actual'),
        'unit_price': price.get('unitPrice'),
        'unit_of_measure': price.get('unitOfMeasure'),
        'image_url': data.get('imageUrl') or '',
        'on_offer': bool(data.get('onOffer')),
    }


def auth_status():
    """Return {'signed_in': bool}. Cheap check - safe to call from templates.

    The file existing is not enough: after a reboot the stored access token
    may already be expired (tokens live ~1h; the CLI refreshes lazily). Report
    signed_in only when the session is present AND its access token has not
    yet expired, so the UI doesn't claim "connected" when every basket write
    is going to fail.
    """
    if not os.path.exists(SESSION_FILE):
        return {'signed_in': False}
    try:
        with open(SESSION_FILE) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {'signed_in': False}
    expiry = data.get('accessTokenExpiry')
    if expiry is not None and time.time() * 1000 >= float(expiry):
        return {'signed_in': False}
    return {'signed_in': bool(data.get('accessToken') or data.get('cookies'))}


def _display_env():
    """Env for launching a GUI browser from a non-desktop process.

    If the app runs under systemd or a TTY-less shell, DISPLAY/XAUTHORITY
    are missing and Chrome dies with 'The platform failed to initialize'.
    Detect them from the user's live desktop session instead.
    """
    env = dict(os.environ)
    if env.get('DISPLAY'):
        return env
    my_uid = str(os.getuid())
    for entry in os.listdir('/proc'):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        try:
            with open(f'/proc/{entry}/status') as fh:
                if not any(l.startswith('Uid:') and my_uid in l.split() for l in fh):
                    continue
            with open(f'/proc/{entry}/environ') as fh:
                proc_env = dict(
                    kv.split('=', 1) for kv in fh.read().split('\0') if '=' in kv
                )
        except (OSError, UnicodeDecodeError):
            continue
        if proc_env.get('DISPLAY'):
            for key in ('DISPLAY', 'XAUTHORITY', 'XDG_RUNTIME_DIR'):
                if proc_env.get(key):
                    env[key] = proc_env[key]
            return env
    return env


def login():
    """Start an interactive sign-in in a background thread.

    Opens a real Chrome window on this machine; a human completes the Tesco
    sign-in. Returns immediately. Call login_status() to poll progress.
    """
    if _login_state['running']:
        return False
    _login_state.update({'running': True, 'done': False, 'ok': False, 'output': ''})

    def _worker():
        # The `basketeer login` CLI refuses to run without a TTY (and waits
        # for a manual Enter press), so we drive our own Playwright script
        # instead: it opens a real Chrome window, polls for the
        # OAuth.AccessToken cookie and harvests the session itself.
        if not os.path.exists(LOGIN_SCRIPT):
            _login_state.update({
                'ok': False, 'done': True,
                'output': 'scripts/tesco_login.js is missing - reinstall the app',
            })
            return
        if not datadir.find_chrome():
            _login_state.update({
                'ok': False, 'done': True,
                'output': 'Google Chrome was not found on this computer - install it from google.com/chrome to sign in to Tesco',
            })
            return
        try:
            proc = subprocess.run(
                [NODE, LOGIN_SCRIPT],
                capture_output=True, text=True, timeout=620, cwd=BASE_DIR,
                env=_display_env(),
            )
            _login_state['ok'] = proc.returncode == 0 and os.path.exists(SESSION_FILE)
            _login_state['output'] = (proc.stdout or proc.stderr or '').strip()[-500:]
        except subprocess.TimeoutExpired:
            _login_state['ok'] = False
            _login_state['output'] = 'Sign-in timed out (10 minutes) - no Tesco sign-in was detected in the Chrome window'
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
    return _json_output(['basket', 'get'])


def basket_set(sku, qty):
    """Set a basket line to an exact quantity (0 removes it)."""
    return _json_output(['basket', 'set', str(sku), str(qty)])


_WEIGHT_VOLUME_RE = re.compile(
    r'\s*\d+(?:\.\d+)?\s*(?:g|kg|mg|ml|l|lb|oz|c|tbsp|tsp|cl|pint|pints|fluid)\b', re.IGNORECASE
)


def parse_qty(quantity_text):
    """Extract an integer count for the Tesco basket from free-text quantities.

    Weight/volume amounts ('200g', '1kg', '500ml') mean the item itself, so
    they map to 1. Plain counts ('2', '2 cups', '3 pack', 'x4') map to the
    number.
    """
    if not quantity_text:
        return 1
    text = quantity_text.strip()
    if _WEIGHT_VOLUME_RE.fullmatch(text):
        return 1
    m = re.match(r'[x×]?\s*(\d+(?:\.\d+)?)\s*(.*)', text)
    if not m:
        return 1
    val = float(m.group(1))
    suffix = m.group(2).strip().lower()
    # Small kitchen measures mean "a bit of one product", not a count of units.
    if suffix in {'cup', 'cups', 'tsp', 'teaspoon', 'teaspoons', 'tbsp',
                  'tablespoon', 'tablespoons', 'pinch', 'pinches', 'slice',
                  'slices', 'piece', 'pieces', 'sprig', 'sprigs', 'bunch'}:
        return 1
    return max(1, int(val))
