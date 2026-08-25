"""Update checking against GitHub Releases.

The app polls the GitHub Releases API for the newest release of
spellers/shopping-app, picks the installer asset for the current platform,
and lets the UI show a "new version available" banner. Results are cached
on disk for CHECK_INTERVAL so page loads never hit the network, and the
refresh runs in a background thread. Everything degrades silently when
offline — the app is fully usable without any update awareness.
"""
import json
import os
import re
import sys
import threading
import urllib.request
from datetime import datetime, timedelta

import datadir

VERSION = "1.0.1"

REPO = "spellers/shopping-app"
RELEASE_API = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASE_PAGE = "https://github.com/%s/releases" % REPO

CHECK_INTERVAL = timedelta(hours=4)
DISMISS_UNTIL = timedelta(days=7)
HTTP_TIMEOUT = 5

_cache_lock = threading.Lock()
_check_inflight = threading.Event()


def _cache_file():
    return os.path.join(_data_dir(), "update_check.json")


def _dismiss_file():
    return os.path.join(_data_dir(), "update_dismissed.json")


def _data_dir():
    """Resolve the data dir per-call so env changes (tests) are honoured."""
    return datadir.data_dir()


def _read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_json(path, payload):
    try:
        with open(path, "w") as fh:
            json.dump(payload, fh)
    except OSError:
        pass


def parse_version(text):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3). None if not a simple semver-ish tag."""
    if not text:
        return None
    m = re.match(r'^v?(\d+)\.(\d+)\.(\d+)$', str(text).strip())
    return tuple(int(g) for g in m.groups()) if m else None


def newer(latest_tag, current=VERSION):
    """True if latest_tag is a version newer than current."""
    a, b = parse_version(latest_tag), parse_version(current)
    return bool(a and b and a > b)


def asset_for_platform(assets):
    """Pick the download asset for the current platform from a release's asset list.

    Expects the GitHub API asset shape ({'name': ..., 'browser_download_url': ...}).
    Returns (name, url) or None.
    """
    if not assets:
        return None
    if sys.platform == 'win32':
        want = (lambda n: n.lower().endswith('.exe'))
    else:
        want = (lambda n: n.lower().endswith('.appimage'))
    for asset in assets:
        name = asset.get('name', '')
        if want(name):
            url = asset.get('browser_download_url') or asset.get('url')
            if url:
                return name, url
    return None


def _fetch_latest():
    """GET the latest release. Returns a normalized dict or None (offline/404)."""
    req = urllib.request.Request(RELEASE_API, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'ShoppingApp-updater',
    })
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.load(resp)
    except Exception:
        return None
    tag = data.get('tag_name')
    if not tag:
        return None
    return {
        'tag': tag,
        'name': data.get('name') or tag,
        'page': data.get('html_url') or RELEASE_PAGE,
        'assets': data.get('assets') or [],
    }


def _load_cached():
    """Return (cache_dict, fresh_bool)."""
    data = _read_json(_cache_file())
    if not data:
        return None, False
    try:
        checked_at = datetime.fromisoformat(data['checked_at'])
    except (KeyError, ValueError):
        return data, False
    return data, datetime.now() - checked_at < CHECK_INTERVAL


def check_now():
    """Synchronously refresh the cache (used at startup and by tests)."""
    with _cache_lock:
        release = _fetch_latest()
        checked_at = datetime.now()
        if release is not None:
            payload = dict(release)
        else:
            # Offline: keep serving a previously known release, if any.
            old, _ = _load_cached()
            payload = dict(old) if old else {'error': 'offline'}
        payload['checked_at'] = checked_at.isoformat()
        _write_json(_cache_file(), payload)
        return payload


def ensure_check():
    """Make sure a check is scheduled; never blocks a request.

    If the cache is fresh (or an inflight refresh exists) this returns
    immediately. Otherwise a background thread refreshes the cache.
    """
    _data, fresh = _load_cached()
    if fresh or _check_inflight.is_set():
        return
    _check_inflight.set()
    def _work():
        try:
            check_now()
        finally:
            _check_inflight.clear()
    threading.Thread(target=_work, daemon=True).start()


def dismiss(tag):
    """Hide the banner for this release tag for a week."""
    if not tag:
        return
    _write_json(_dismiss_file(), {
        'tag': tag,
        'until': (datetime.now() + DISMISS_UNTIL).isoformat(),
    })


def dismissed_tag():
    """The tag the user dismissed, if the dismissal is still in effect."""
    data = _read_json(_dismiss_file())
    if not data:
        return None
    try:
        until = datetime.fromisoformat(data['until'])
    except (KeyError, ValueError):
        return None
    return data.get('tag') if datetime.now() < until else None


def status():
    """Update status for the UI.

    Returns a dict: current_version, latest_version (or None), update_available,
    download_url, download_name, release_page, dismissed.
    """
    result = {
        'current_version': VERSION,
        'latest_version': None,
        'update_available': False,
        'download_url': None,
        'download_name': None,
        'release_page': RELEASE_PAGE,
        'dismissed': False,
    }
    data, _ = _load_cached()
    if not data or 'tag' not in data:
        return result
    tag = data.get('tag')
    result['latest_version'] = tag
    result['release_page'] = data.get('page') or RELEASE_PAGE
    if not newer(tag, VERSION):
        return result
    asset = asset_for_platform(data.get('assets'))
    if asset:
        result['download_name'], result['download_url'] = asset
    result['update_available'] = True
    result['dismissed'] = (dismissed_tag() == tag)
    return result
