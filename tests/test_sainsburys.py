"""Tests for the Sainsbury's provider (providers/sainsburys.py)."""
import json
import time
from datetime import datetime, timezone, timedelta

import pytest

import app as app_module
from providers import sainsburys
from providers.sainsburys import SainsburysError


def test_registry_has_sainsburys():
    grocer = app_module.providers.get_grocer('sainsburys')
    assert grocer is not None
    assert grocer.name == "Sainsbury's"
    keys = [g.key for g in app_module.providers.list_grocers()]
    assert keys == ['sainsburys', 'tesco']


def test_product_mapping():
    p = sainsburys._product({
        'product_uid': 357937,
        'name': "Sainsbury's British Semi Skimmed Milk 2.27L (4 pint)",
        'retail_price': {'price': 1.75, 'measure': ''},
        'unit_price': {'price': 0.77, 'measure': 'ltr'},
        'image_url': 'https://example.com/milk.jpg',
    })
    assert p['sku'] == '357937'
    assert p['title'].startswith("Sainsbury's British")
    assert p['price'] == 1.75
    assert p['unit_price'] == 0.77
    assert p['unit_of_measure'] == 'ltr'
    assert p['image_url'] == 'https://example.com/milk.jpg'
    assert p['on_offer'] is False
    assert p['brand'] == ''


def test_product_mapping_missing_fields():
    p = sainsburys._product({'product_uid': None, 'name': None})
    assert p['sku'] == ''
    assert p['title'] == ''
    assert p['price'] is None


def test_search_maps_and_limits(monkeypatch):
    library_products = [
        {'product_uid': i, 'name': f'milk {i}', 'retail_price': {'price': i}}
        for i in range(7)
    ]
    monkeypatch.setattr(sainsburys, '_api', lambda action: library_products)
    results = sainsburys.search('milk', limit=5)
    assert len(results) == 5
    assert results[0]['sku'] == '0'
    assert results[0]['title'] == 'milk 0'
    assert results[4]['price'] == 4


def test_search_passes_query_to_api(monkeypatch):
    seen = {}

    def fake_api(action):
        seen['action'] = action
        return []

    monkeypatch.setattr(sainsburys, '_api', fake_api)
    sainsburys.search('olive oil')
    assert 'provider.search("olive oil")' in seen['action']


def test_get_product_maps(monkeypatch):
    monkeypatch.setattr(
        sainsburys, '_api',
        lambda action: {'product_uid': 1, 'name': 'x', 'retail_price': {'price': 2}})
    p = sainsburys.get_product('1')
    assert p['sku'] == '1' and p['price'] == 2


def test_get_product_empty_raises(monkeypatch):
    monkeypatch.setattr(sainsburys, '_api', lambda action: None)
    with pytest.raises(SainsburysError):
        sainsburys.get_product('999')


def test_basket_mapping(monkeypatch):
    monkeypatch.setattr(sainsburys, '_api', lambda action: {
        'items': [
            {'item_id': 'a1', 'product_uid': '357937', 'name': 'milk',
             'quantity': 2, 'unit_price': 0.88, 'total_price': 1.75},
        ],
        'total_quantity': 2,
        'total_cost': 1.75,
    })
    b = sainsburys.basket()
    assert b['total_qty'] == 2
    assert b['total_cost'] == 1.75
    assert b['items'][0] == {'item_id': 'a1', 'sku': '357937', 'title': 'milk',
                             'qty': 2, 'unit_price': 0.88, 'total': 1.75}


def test_basket_empty(monkeypatch):
    monkeypatch.setattr(sainsburys, '_api', lambda action: {})
    b = sainsburys.basket()
    assert b == {'items': [], 'total_qty': 0, 'total_cost': 0}


def test_checkout_url():
    assert sainsburys.checkout_url().startswith('https://www.sainsburys.co.uk')


def test_parse_qty_defaults_to_one():
    assert sainsburys.SainsburysGrocer().parse_qty('anything') == 1


def test_auth_status_no_session(monkeypatch, tmp_path):
    monkeypatch.setattr(sainsburys, 'SESSION_FILE', str(tmp_path / 'missing.json'))
    assert sainsburys.auth_status() == {'signed_in': False}


def test_auth_status_signed_in(monkeypatch, tmp_path):
    path = tmp_path / 'session.json'
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    path.write_text(json.dumps({
        'cookies': [{'name': 'WC_AUTHENTICATION_Token', 'value': 'abc'}],
        'expiresAt': future,
    }))
    monkeypatch.setattr(sainsburys, 'SESSION_FILE', str(path))
    assert sainsburys.auth_status() == {'signed_in': True}


def test_auth_status_expired(monkeypatch, tmp_path):
    path = tmp_path / 'session.json'
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    path.write_text(json.dumps({
        'cookies': [{'name': 'WC_AUTHENTICATION_Token', 'value': 'abc'}],
        'expiresAt': past,
    }))
    monkeypatch.setattr(sainsburys, 'SESSION_FILE', str(path))
    assert sainsburys.auth_status() == {'signed_in': False}


def test_auth_status_no_auth_cookie(monkeypatch, tmp_path):
    path = tmp_path / 'session.json'
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    path.write_text(json.dumps({
        'cookies': [{'name': 'other', 'value': 'abc'}],
        'expiresAt': future,
    }))
    monkeypatch.setattr(sainsburys, 'SESSION_FILE', str(path))
    assert sainsburys.auth_status() == {'signed_in': False}


def test_auth_status_legacy_string_cookies(monkeypatch, tmp_path):
    path = tmp_path / 'session.json'
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    path.write_text(json.dumps({
        'cookies': 'a=1; WC_AUTHENTICATION_Token=abc',
        'expiresAt': future,
    }))
    monkeypatch.setattr(sainsburys, 'SESSION_FILE', str(path))
    assert sainsburys.auth_status() == {'signed_in': True}


def test_auth_status_corrupt(monkeypatch, tmp_path):
    path = tmp_path / 'session.json'
    path.write_text('not json')
    monkeypatch.setattr(sainsburys, 'SESSION_FILE', str(path))
    assert sainsburys.auth_status() == {'signed_in': False}


def test_run_js_failure_raises(monkeypatch):
    import subprocess

    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = 'boom'

    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: FakeProc())
    with pytest.raises(SainsburysError, match='boom'):
        sainsburys._run_js('console.log(1)')


def test_run_js_timeout_raises(monkeypatch):
    import subprocess

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired('node', 1)

    monkeypatch.setattr(subprocess, 'run', _timeout)
    with pytest.raises(SainsburysError, match='timed out'):
        sainsburys._run_js('console.log(1)')


def test_adapter_uses_module_functions(monkeypatch):
    """The registry adapter must resolve through module globals so
    monkeypatching providers.sainsburys.search also affects the adapter."""
    grocer = app_module.providers.get_grocer('sainsburys')
    monkeypatch.setattr(
        sainsburys, 'search',
        lambda q, limit=5: [{'sku': 'x', 'title': q, 'price': 1, 'brand': '',
                             'unit_price': None, 'unit_of_measure': '',
                             'image_url': '', 'on_offer': False}])
    assert grocer.search('cheese')[0]['sku'] == 'x'


def test_login_refuses_double_start(monkeypatch):
    monkeypatch.setattr(sainsburys, '_login_state',
                        {'running': True, 'done': False, 'ok': False, 'output': ''})
    assert sainsburys.login() is False


def test_login_reports_missing_script(monkeypatch, tmp_path):
    sainsburys._login_state.update({'running': False, 'done': False,
                                    'ok': False, 'output': ''})
    monkeypatch.setattr(sainsburys, 'LOGIN_SCRIPT', str(tmp_path / 'nope.js'))
    assert sainsburys.login() is True
    # the worker runs in a thread; wait for it to finish
    for _ in range(100):
        if not sainsburys.login_status()['running']:
            break
        time.sleep(0.05)
    status = sainsburys.login_status()
    assert status['ok'] is False
    assert 'missing' in status['output']
