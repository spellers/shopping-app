import json
import os
import sys
import time
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import updates


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Never let a background check thread hit the real GitHub API.

    Individual tests that want to simulate a fetch monkeypatch
    updates._fetch_latest with their own fake (which wins, applied later).
    """
    monkeypatch.setattr(updates, '_fetch_latest', lambda: None)

    def _wait_idle():
        deadline = time.time() + 5
        while time.time() < deadline:
            with updates._inflight_lock:
                busy = [e for e in updates._inflight.values() if e.is_set()]
            if not busy:
                return
            time.sleep(0.02)

    _wait_idle()
    with updates._inflight_lock:
        updates._inflight.clear()
    yield
    _wait_idle()
    with updates._inflight_lock:
        updates._inflight.clear()


def _write_cache(data_dir, tag="v9.9.9", asset_name=None, page="https://github.com/spellers/shopping-app/releases/tag/v9.9.9", stale=False):
    assets = []
    if asset_name:
        assets.append({'name': asset_name,
                       'browser_download_url': 'https://github.com/spellers/shopping-app/releases/download/%s/%s' % (tag, asset_name)})
    payload = {
        'tag': tag,
        'name': tag,
        'page': page,
        'assets': assets,
        # fresh by default so ensure_check stays a no-op; tests that want a
        # background refresh mark it stale.
        'checked_at': (datetime.now() - timedelta(hours=5)).isoformat() if stale
                      else datetime.now().isoformat(),
    }
    with open(os.path.join(data_dir, 'update_check.json'), 'w') as fh:
        json.dump(payload, fh)


def test_parse_version():
    assert updates.parse_version('v1.2.3') == (1, 2, 3)
    assert updates.parse_version('1.2.3') == (1, 2, 3)
    assert updates.parse_version('v2.0') is None
    assert updates.parse_version(None) is None
    assert updates.parse_version('') is None


def test_newer():
    assert updates.newer('v1.0.1', '1.0.0')
    assert updates.newer('v2.0.0', '1.0.0')
    assert not updates.newer('v1.0.0', '1.0.0')
    assert not updates.newer('v0.9.0', '1.0.0')
    assert not updates.newer('v1.0', '1.0.0')  # unparseable


def test_asset_for_platform():
    assets = [
        {'name': 'ShoppingApp-Setup-1.0.0.exe', 'browser_download_url': 'https://x/exe'},
        {'name': 'ShoppingApp-x86_64.AppImage', 'browser_download_url': 'https://x/appimage'},
    ]
    if sys.platform == 'win32':
        assert updates.asset_for_platform(assets) == ('ShoppingApp-Setup-1.0.0.exe', 'https://x/exe')
    else:
        assert updates.asset_for_platform(assets) == ('ShoppingApp-x86_64.AppImage', 'https://x/appimage')
    assert updates.asset_for_platform([]) is None
    assert updates.asset_for_platform(None) is None


def test_status_with_no_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    st = updates.status()
    assert st['current_version'] == updates.VERSION
    assert st['latest_version'] is None
    assert st['update_available'] is False
    assert st['dismissed'] is False


def test_status_current_when_same_version(tmp_path, monkeypatch):
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    _write_cache(str(tmp_path), tag='v1.0.0')
    st = updates.status()
    assert st['latest_version'] == 'v1.0.0'
    assert st['update_available'] is False


def test_status_update_available(tmp_path, monkeypatch):
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    asset = 'ShoppingApp-x86_64.AppImage' if sys.platform != 'win32' else 'ShoppingApp-Setup-1.0.0.exe'
    _write_cache(str(tmp_path), asset_name=asset)
    st = updates.status()
    assert st['update_available'] is True
    assert st['latest_version'] == 'v9.9.9'
    assert st['download_name'] == asset
    assert st['download_url'].endswith(asset)
    assert st['dismissed'] is False


def test_dismiss_hides_banner(tmp_path, monkeypatch):
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    _write_cache(str(tmp_path), asset_name='x.exe')
    assert updates.status()['update_available'] is True
    updates.dismiss('v9.9.9')
    assert updates.dismissed_tag() == 'v9.9.9'
    assert updates.status()['dismissed'] is True
    # Dismissing a different tag does not hide this one.
    updates.dismiss('v8.8.8')
    assert updates.status()['dismissed'] is False


def test_dismiss_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    with open(os.path.join(str(tmp_path), 'update_dismissed.json'), 'w') as fh:
        json.dump({'tag': 'v9.9.9', 'until': '2000-01-01T00:00:00'}, fh)
    assert updates.dismissed_tag() is None


def test_check_now_offline_keeps_old_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    _write_cache(str(tmp_path), tag='v5.5.5')
    monkeypatch.setattr(updates, '_fetch_latest', lambda: None)
    payload = updates.check_now()
    assert payload['tag'] == 'v5.5.5'
    cached = json.load(open(os.path.join(str(tmp_path), 'update_check.json')))
    assert cached['tag'] == 'v5.5.5'
    assert 'checked_at' in cached


def test_check_now_offline_no_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    monkeypatch.setattr(updates, '_fetch_latest', lambda: None)
    payload = updates.check_now()
    assert payload.get('error') == 'offline'
    st = updates.status()
    assert st['update_available'] is False


def test_ensure_check_schedules_background_refresh(client, tmp_path, monkeypatch):
    import threading
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    _write_cache(str(tmp_path), tag='v4.4.4', stale=True)
    results = []
    gate = threading.Event()

    def fake_fetch():
        results.append(1)
        gate.wait(2)  # hold the refresh open so the dedup check is testable
        return {'tag': 'v6.6.6', 'name': 'v6.6.6', 'page': 'https://example', 'assets': []}

    monkeypatch.setattr(updates, '_fetch_latest', fake_fetch)
    updates.ensure_check()
    # Wait until the background thread is inside the (gated) fetch.
    deadline = time.time() + 5
    while not results and time.time() < deadline:
        time.sleep(0.01)
    assert results  # thread started
    updates.ensure_check()  # must not schedule a second refresh
    time.sleep(0.2)  # any rogue second thread would have called fetch by now
    gate.set()
    deadline = time.time() + 5
    while time.time() < deadline:
        with updates._inflight_lock:
            if not any(e.is_set() for e in updates._inflight.values()):
                break
        time.sleep(0.02)
    assert results == [1]  # exactly one refresh happened
    assert updates.status()['latest_version'] == 'v6.6.6'


def test_update_routes(client, tmp_path, monkeypatch):
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path))
    # Block real network: any refresh keeps the stale cache we just wrote.
    monkeypatch.setattr(updates, '_fetch_latest', lambda: None)
    asset = 'ShoppingApp-x86_64.AppImage' if sys.platform != 'win32' else 'ShoppingApp-Setup-1.0.0.exe'
    url = 'https://github.com/spellers/shopping-app/releases/download/v9.9.9/%s' % asset
    _write_cache(str(tmp_path), asset_name=asset)

    # JSON status endpoint
    st = client.get('/updates/status').get_json()
    assert st['update_available'] is True
    assert st['latest_version'] == 'v9.9.9'

    # Banner shows on a normal page
    page = client.get('/meal_tracker').get_data(as_text=True)
    assert 'Update available: v9.9.9' in page

    # Download redirects to the asset
    resp = client.get('/updates/download')
    assert resp.status_code == 302
    assert resp.headers['Location'] == url

    # Dismiss hides the banner
    client.post('/updates/dismiss', data={'tag': 'v9.9.9'})
    page = client.get('/meal_tracker').get_data(as_text=True)
    assert 'Update available' not in page

    # No banner at all when no update is known
    monkeypatch.setenv('SHOPPING_APP_DATA', str(tmp_path / 'empty'))
    os.makedirs(tmp_path / 'empty', exist_ok=True)
    page = client.get('/meal_tracker').get_data(as_text=True)
    assert 'Update available' not in page
