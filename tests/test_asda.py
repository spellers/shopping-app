"""Tests for the Asda provider (providers/asda.py)."""
import subprocess

import pytest

import app as app_module
from providers import asda
from providers.asda import AsdaError


def test_registry_has_asda():
    grocer = app_module.providers.get_grocer('asda')
    assert grocer is not None
    assert grocer.name == 'Asda'
    keys = [g.key for g in app_module.providers.list_grocers()]
    assert keys == ['asda', 'morrisons', 'sainsburys', 'tesco', 'waitrose']


def test_product_mapping():
    p = asda._product({
        'ID': 165468,
        'CIN': 165468,
        'NAME': "Sainsbury's British Semi Skimmed Milk 2L",
        'BRAND': "Sainsbury's",
        'IMAGE_ID': 'abcd1234',
        'PRICES': {'EN': {
            'PRICE': 1.75,
            'PRICEPERUOM': 0.77,
            'PRICEPERUOMFORMATTED': '77.0p/LT',
            'OFFER': 'List',
        }},
    })
    assert p['sku'] == '165468'
    assert p['title'].endswith('Milk 2L')
    assert p['brand'] == "Sainsbury's"
    assert p['price'] == 1.75
    assert p['unit_price'] == 0.77
    assert p['unit_of_measure'] == 'per lt'
    assert p['image_url'] == 'https://ui.assets-asda.com/dm/abcd1234'
    assert p['on_offer'] is False


def test_product_mapping_offer():
    p = asda._product({
        'CIN': 5,
        'NAME': 'x',
        'PRICES': {'EN': {'PRICE': 0.5, 'OFFER': 'Special'}},
    })
    assert p['on_offer'] is True
    assert p['unit_of_measure'] == ''


def test_product_mapping_missing_fields():
    p = asda._product({'CIN': None, 'ID': 12, 'NAME': None})
    assert p['sku'] == '12'
    assert p['title'] == ''
    assert p['price'] is None
    assert p['image_url'] == ''


def test_search_maps_and_limits(monkeypatch):
    hits = [{'CIN': i, 'NAME': f'milk {i}',
             'PRICES': {'EN': {'PRICE': i}}} for i in range(7)]
    monkeypatch.setattr(asda, '_algolia_search', lambda q, n: hits)
    results = asda.search('milk', limit=5)
    assert len(results) == 5
    assert results[0]['sku'] == '0'
    assert results[4]['price'] == 4


def test_search_passes_query(monkeypatch):
    seen = {}

    def fake(q, n):
        seen['query'] = q
        seen['page_size'] = n
        return []

    monkeypatch.setattr(asda, '_algolia_search', fake)
    asda.search('olive oil', limit=3)
    assert seen['query'] == 'olive oil'
    assert seen['page_size'] == 3


def test_get_product_maps(monkeypatch):
    monkeypatch.setattr(
        asda, '_algolia_search',
        lambda *a, **k: [{'CIN': 165468, 'NAME': 'milk',
                       'PRICES': {'EN': {'PRICE': 1.75}}}])
    p = asda.get_product('165468')
    assert p['sku'] == '165468' and p['price'] == 1.75


def test_get_product_not_found(monkeypatch):
    monkeypatch.setattr(asda, '_algolia_search', lambda *a, **k: [])
    with pytest.raises(AsdaError, match='not found'):
        asda.get_product('999999')


def test_get_product_cin_mismatch(monkeypatch):
    # a numeric SKU must actually match the returned product's CIN/ID
    monkeypatch.setattr(
        asda, '_algolia_search',
        lambda *a, **k: [{'CIN': 111, 'NAME': 'wrong product',
                       'PRICES': {'EN': {'PRICE': 1}}}])
    with pytest.raises(AsdaError, match='not found'):
        asda.get_product('222')


def test_basket_mapping(monkeypatch):
    monkeypatch.setattr(asda, '_basket_call', lambda obj: {
        'items': [
            {'item_id': 'i1', 'sku': '165468', 'title': 'milk',
             'qty': 2, 'unit_price': 0.88, 'total': 1.75},
        ],
        'total_qty': 2,
        'total_cost': 1.75,
    })
    b = asda.basket()
    assert b['total_qty'] == 2
    assert b['total_cost'] == 1.75
    assert b['items'][0]['sku'] == '165468'


def test_basket_empty(monkeypatch):
    monkeypatch.setattr(asda, '_basket_call', lambda obj: {})
    b = asda.basket()
    assert b == {'items': [], 'total_qty': 0, 'total_cost': 0}


def test_basket_set_passes_cmd(monkeypatch):
    seen = {}
    monkeypatch.setattr(asda, '_basket_call', lambda obj: seen.update(obj))
    asda.basket_set('165468', 3)
    assert seen == {'cmd': 'set', 'cin': '165468', 'qty': 3}
    asda.basket_set('165468', 0)
    assert seen == {'cmd': 'set', 'cin': '165468', 'qty': 0}


def test_checkout_url():
    assert asda.checkout_url().startswith('https://www.asda.com')


def test_parse_qty():
    assert asda.parse_qty('2 cartons') == 2
    assert asda.parse_qty('a bit of stuff') == 1
    assert asda.parse_qty(None) == 1


def test_auth_status_guest():
    status = asda.auth_status()
    assert status['signed_in'] is True
    assert 'guest' in status['note'].lower()


def test_basket_call_failure_raises(monkeypatch):
    class FakeProc:
        returncode = 1
        stdout = ''
        stderr = 'boom'

    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: FakeProc())
    with pytest.raises(AsdaError, match='boom'):
        asda._basket_call({'cmd': 'get'})


def test_basket_call_timeout_raises(monkeypatch):
    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired('node', 1)

    monkeypatch.setattr(subprocess, 'run', _timeout)
    with pytest.raises(AsdaError, match='timed out'):
        asda._basket_call({'cmd': 'get'})


def test_basket_call_bad_json(monkeypatch):
    class FakeProc:
        returncode = 0
        stdout = 'not json'
        stderr = ''

    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: FakeProc())
    with pytest.raises(AsdaError, match='parse'):
        asda._basket_call({'cmd': 'get'})


def test_adapter_uses_module_functions(monkeypatch):
    """The registry adapter must resolve through module globals so
    monkeypatching providers.asda.search also affects the adapter."""
    grocer = app_module.providers.get_grocer('asda')
    monkeypatch.setattr(
        asda, 'search',
        lambda q, limit=5: [{'sku': 'x', 'title': q, 'price': 1, 'brand': '',
                             'unit_price': None, 'unit_of_measure': '',
                             'image_url': '', 'on_offer': False}])
    assert grocer.search('cheese')[0]['sku'] == 'x'
