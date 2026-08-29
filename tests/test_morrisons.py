"""Tests for the Morrisons provider (providers/morrisons.py)."""
import pytest

import app as app_module
from providers import morrisons
from providers.morrisons import MorrisonsError


def test_registry_has_morrisons():
    grocer = app_module.providers.get_grocer('morrisons')
    assert grocer is not None
    assert grocer.name == 'Morrisons'
    keys = [g.key for g in app_module.providers.list_grocers()]
    assert keys == ['asda', 'morrisons', 'sainsburys', 'tesco']


def _raw(name='Milk', sku='123', uuid='u-123', price=1.5, unit=4.5,
         unit_name='PER_LITRE', promo=False):
    return {
        'productId': uuid,
        'retailerProductId': sku,
        'name': name,
        'brand': 'Morrisons',
        'price': {'amount': str(price), 'currency': 'GBP'},
        'unitPrice': {
            'price': {'amount': str(unit), 'currency': 'GBP'},
            'unit': f'fop.price.per.{unit_name[4:].lower()}',
            'unitName': unit_name,
        },
        'image': {'src': f'https://img/{uuid}.jpg'},
        **({'promoPrice': {'amount': '1.0', 'currency': 'GBP'}} if promo else {}),
    }


def test_product_mapping():
    p = morrisons._product(_raw())
    assert p['sku'] == '123'
    assert p['title'] == 'Milk'
    assert p['brand'] == 'Morrisons'
    assert p['price'] == 1.5
    assert p['unit_price'] == 4.5
    assert p['unit_of_measure'] == 'per litre'
    assert p['image_url'] == 'https://img/u-123.jpg'
    assert p['on_offer'] is False


def test_product_mapping_offer():
    p = morrisons._product(_raw(promo=True))
    assert p['on_offer'] is True


def test_product_mapping_missing_fields():
    p = morrisons._product({'productId': 'abc', 'name': None})
    assert p['sku'] == 'abc'
    assert p['title'] == ''
    assert p['price'] is None
    assert p['unit_price'] is None
    assert p['unit_of_measure'] == ''
    assert p['image_url'] == ''
    assert p['on_offer'] is False


def test_unit_name_variants():
    assert morrisons._unit_name('PER_KILOGRAM') == 'per kilogram'
    assert morrisons._unit_name('fop.price.per.piece') == 'per piece'
    assert morrisons._unit_name('') == ''
    assert morrisons._unit_name(None) == ''
    assert morrisons._unit_name('SOMETHING_ELSE') == ''


def test_amount():
    assert morrisons._amount({'amount': '2.50'}) == 2.5
    assert morrisons._amount('2.50') == 2.5
    assert morrisons._amount(None) is None
    assert morrisons._amount({}) is None
    assert morrisons._amount('garbage') is None


def test_search_maps_and_limits(monkeypatch):
    products = [_raw(name=f'milk {i}', sku=str(i)) for i in range(7)]
    monkeypatch.setattr(morrisons, '_search_products', lambda q: products)
    results = morrisons.search('milk', limit=5)
    assert len(results) == 5
    assert results[0]['sku'] == '0'
    assert results[4]['price'] == 1.5


def test_search_passes_query(monkeypatch):
    seen = {}

    def fake(q):
        seen['query'] = q
        return []

    monkeypatch.setattr(morrisons, '_search_products', fake)
    morrisons.search('olive oil', limit=3)
    assert seen['query'] == 'olive oil'


def test_get_product_numeric_id(monkeypatch):
    monkeypatch.setattr(
        morrisons, '_search_products',
        lambda q: [_raw(sku='103142642'), _raw(sku='999')])
    p = morrisons.get_product('103142642')
    assert p['sku'] == '103142642'


def test_get_product_name_fallback(monkeypatch):
    monkeypatch.setattr(
        morrisons, '_search_products',
        lambda q: [_raw(name='British Semi Skimmed Milk')])
    p = morrisons.get_product('British Semi Skimmed Milk')
    assert p['title'] == 'British Semi Skimmed Milk'


def test_get_product_not_found(monkeypatch):
    monkeypatch.setattr(morrisons, '_search_products', lambda q: [])
    with pytest.raises(MorrisonsError, match='not found'):
        morrisons.get_product('999999')


def test_get_product_numeric_mismatch(monkeypatch):
    # a numeric SKU must actually match the returned product's id
    monkeypatch.setattr(morrisons, '_search_products',
                        lambda q: [_raw(sku='111')])
    with pytest.raises(MorrisonsError, match='not found'):
        morrisons.get_product('222')


def test_basket_mapping(monkeypatch):
    monkeypatch.setattr(morrisons, '_cart_items', lambda session=None: [
        {'productId': 'u-123', 'quantity': 2,
         'finalPrice': {'amount': '1.35', 'currency': 'GBP'},
         'totalPrices': {'finalPrice': {'amount': '2.70'}}},
        {'productId': 'u-124', 'quantity': 1,
         'finalPrice': {'amount': '2.00', 'currency': 'GBP'}},
    ])
    b = morrisons.basket()
    assert b['total_qty'] == 3
    assert b['total_cost'] == 4.7
    assert b['items'][0]['sku'] == 'u-123'
    assert b['items'][0]['quantity'] == 2
    assert b['items'][0]['price'] == 1.35


def test_basket_empty(monkeypatch):
    monkeypatch.setattr(morrisons, '_cart_items', lambda session=None: [])
    assert morrisons.basket() == {'items': [], 'total_qty': 0,
                                  'total_cost': 0}


UUID = '9d8d308c-6347-4f98-a80a-6d33818da230'


def test_uuid_for_passes_uuids_through(monkeypatch):
    # must NOT trigger a search for a well-formed UUID
    monkeypatch.setattr(
        morrisons, '_search_products',
        lambda q: pytest.fail('unexpected search'))
    assert morrisons._uuid_for(UUID) == UUID


def test_uuid_for_resolves_numeric(monkeypatch):
    monkeypatch.setattr(
        morrisons, '_search_products',
        lambda q: [_raw(sku='103142642', uuid=UUID)])
    assert morrisons._uuid_for('103142642') == UUID


def test_uuid_for_not_found(monkeypatch):
    monkeypatch.setattr(morrisons, '_search_products', lambda q: [])
    with pytest.raises(MorrisonsError, match='not found'):
        morrisons._uuid_for('42')


def _stub_basket_write(monkeypatch, cart, posted):
    """Patch the read/uuid seams so basket_set only drives session.request."""
    monkeypatch.setattr(morrisons, '_cart_items',
                        lambda session=None: cart)
    monkeypatch.setattr(morrisons, '_search_products',
                        lambda q: [_raw(sku='103142642', uuid=UUID)])
    monkeypatch.setattr(morrisons._SESSION, 'csrf', lambda: 'tok-1')
    monkeypatch.setattr(
        morrisons._SESSION, 'request',
        lambda url, method='GET', body=None, extra=None:
        posted.update(url=url, method=method, body=body, extra=extra) or b'{}')


def test_basket_set_adds(monkeypatch):
    """Empty cart: set 2 -> single POST with delta +2 and basket headers."""
    posted = {}
    _stub_basket_write(monkeypatch, [], posted)
    morrisons.basket_set('103142642', 2)
    assert posted['method'] == 'POST'
    assert posted['url'].endswith('/apply-quantity')
    assert posted['body'] == [{'productId': UUID, 'quantity': 2}]
    assert posted['extra']['x-csrf-token'] == 'tok-1'


def test_basket_set_updates_existing(monkeypatch):
    """Cart already has 2: set 1 -> delta -1."""
    posted = {}
    _stub_basket_write(
        monkeypatch, [{'productId': UUID, 'quantity': 2}], posted)
    morrisons.basket_set('103142642', 1)
    assert posted['body'] == [{'productId': UUID, 'quantity': -1}]


def test_basket_set_noop_when_equal(monkeypatch):
    """Same quantity as already in the cart -> no write call at all."""
    calls = []
    monkeypatch.setattr(
        morrisons, '_cart_items',
        lambda session=None: [{'productId': UUID, 'quantity': 2}])
    monkeypatch.setattr(morrisons, '_search_products',
                        lambda q: [_raw(sku='103142642', uuid=UUID)])
    monkeypatch.setattr(morrisons._SESSION, 'request',
                        lambda url, method='GET', body=None, extra=None:
                        calls.append(url) or b'{}')
    morrisons.basket_set('103142642', 2)
    assert calls == []


def test_basket_set_zero_removes(monkeypatch):
    """Cart has 3: set 0 -> delta -3."""
    posted = {}
    _stub_basket_write(
        monkeypatch, [{'productId': UUID, 'quantity': 3}], posted)
    morrisons.basket_set('103142642', 0)
    assert posted['body'] == [{'productId': UUID, 'quantity': -3}]


def test_basket_set_with_uuid_sku(monkeypatch):
    """A UUID SKU skips the search entirely."""
    posted = {}
    _stub_basket_write(monkeypatch, [], posted)
    morrisons.basket_set(UUID, 1)
    assert posted['body'] == [{'productId': UUID, 'quantity': 1}]


def test_basket_call_http_error_raises(monkeypatch):
    import urllib.error

    def fake_request(*a, **k):
        raise urllib.error.HTTPError(
            'url', 403, 'Forbidden', {},
            __import__('io').BytesIO(
                b'{"code":"ecom-csrf-failure"}'))

    monkeypatch.setattr(morrisons._SESSION, 'request', fake_request)
    with pytest.raises(MorrisonsError, match='HTTP 403'):
        morrisons.basket()


def test_basket_bad_json_raises(monkeypatch):
    monkeypatch.setattr(
        morrisons._SESSION, 'request',
        lambda *a, **k: b'not json')
    with pytest.raises(MorrisonsError, match='parse'):
        morrisons.basket()


def test_search_bad_json_raises(monkeypatch):
    monkeypatch.setattr(
        morrisons._SESSION, 'request',
        lambda *a, **k: b'not json')
    with pytest.raises(MorrisonsError, match='parse'):
        morrisons.search('milk')


def test_csrf_extraction(monkeypatch, tmp_path):
    fresh = morrisons._Session(state_file=str(tmp_path / 'cookies.json'))
    monkeypatch.setattr(
        fresh, 'request',
        lambda *a, **k: b'... "csrf":{"token":"abc-123"} ...')
    assert fresh.csrf() == 'abc-123'
    # cached on second call
    assert fresh.csrf() == 'abc-123'


def test_csrf_missing_raises(monkeypatch, tmp_path):
    fresh = morrisons._Session(state_file=str(tmp_path / 'cookies.json'))
    monkeypatch.setattr(fresh, 'request', lambda *a, **k: b'<html>nope</html>')
    with pytest.raises(MorrisonsError, match='CSRF'):
        fresh.csrf()


def test_cookie_persistence_roundtrip(tmp_path):
    """Guest-cart cookies survive a 'process restart' (session rebuild)."""
    state = str(tmp_path / 'cookies.json')
    s1 = morrisons._Session(state_file=state)
    s1.cookies = {'VISITORID': 'abc', 'global_sid': 's-1'}
    s1._save_state()

    s2 = morrisons._Session(state_file=state)
    assert s2.cookies == {'VISITORID': 'abc', 'global_sid': 's-1'}


def test_cookie_load_missing_file_is_fine(tmp_path):
    s = morrisons._Session(state_file=str(tmp_path / 'nope.json'))
    assert s.cookies == {}


def test_checkout_url():
    assert morrisons.checkout_url().startswith('https://groceries.morrisons.com')


def test_parse_qty():
    assert morrisons.parse_qty('2 cartons') == 2
    assert morrisons.parse_qty('a bit of stuff') == 1
    assert morrisons.parse_qty(None) == 1


def test_auth_status_guest():
    status = morrisons.auth_status()
    assert status['signed_in'] is True
    assert 'guest' in status['note'].lower()


def test_adapter_uses_module_functions(monkeypatch):
    """The registry adapter must resolve through module globals so
    monkeypatching providers.morrisons.search also affects the adapter."""
    grocer = app_module.providers.get_grocer('morrisons')
    monkeypatch.setattr(
        morrisons, 'search',
        lambda q, limit=5: [{'sku': 'x', 'title': q, 'price': 1, 'brand': '',
                             'unit_price': None, 'unit_of_measure': '',
                             'image_url': '', 'on_offer': False}])
    assert grocer.search('cheese')[0]['sku'] == 'x'
