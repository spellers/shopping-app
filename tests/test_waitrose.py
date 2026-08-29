"""Tests for the Waitrose provider (providers/waitrose.py)."""
import pytest

import app as app_module
from providers import waitrose
from providers.waitrose import WaitroseError


def test_registry_has_waitrose():
    grocer = app_module.providers.get_grocer('waitrose')
    assert grocer is not None
    assert grocer.name == 'Waitrose'
    keys = [g.key for g in app_module.providers.list_grocers()]
    assert keys == ['asda', 'morrisons', 'sainsburys', 'tesco', 'waitrose']


def _component(name='Milk', sku='42-1-2', price='1.25', size='4 pints'):
    return {'searchProduct': {
        'id': sku, 'name': name, 'brand': 'Waitrose',
        'displayPrice': price, 'size': size,
    }}


def test_product_mapping():
    p = waitrose._product(_component())
    assert p['sku'] == '42-1-2'
    assert p['title'] == 'Milk'
    assert p['brand'] == 'Waitrose'
    assert p['price'] == 1.25
    assert p['unit_of_measure'] == '4 pints'
    assert p['on_offer'] is False


def test_product_mapping_numeric_price():
    p = waitrose._product(_component(price=1.5))
    assert p['price'] == 1.5


def test_product_mapping_garbage_price():
    p = waitrose._product(_component(price='n/a'))
    assert p['price'] is None


def test_product_mapping_missing_fields():
    p = waitrose._product({'searchProduct': {'id': None, 'name': None}})
    assert p['sku'] == ''
    assert p['title'] == ''
    assert p['price'] is None
    assert p['unit_of_measure'] == ''


def test_search_maps_and_limits(monkeypatch):
    components = [_component(sku=f'{i}-1-2', name=f'milk {i}')
                  for i in range(7)]
    monkeypatch.setattr(waitrose, '_search_raw', lambda term: components)
    results = waitrose.search('milk', limit=5)
    assert len(results) == 5
    assert results[0]['sku'] == '0-1-2'


def test_search_passes_query(monkeypatch):
    seen = {}

    def fake(term, start=0):
        seen['term'] = term
        return []

    monkeypatch.setattr(waitrose, '_search_raw', fake)
    waitrose.search('olive oil', limit=3)
    assert seen['term'] == 'olive oil'


def test_get_product_by_sku(monkeypatch):
    monkeypatch.setattr(
        waitrose, '_search_raw',
        lambda term: [_component(sku='42-1-2', name='Milk'),
                      _component(sku='43-1-2', name='Butter')])
    p = waitrose.get_product('43-1-2')
    assert p['sku'] == '43-1-2'
    assert p['title'] == 'Butter'


def test_get_product_first_hit_fallback(monkeypatch):
    monkeypatch.setattr(
        waitrose, '_search_raw',
        lambda term: [_component(sku='42-1-2', name='British Milk')])
    p = waitrose.get_product('British Milk')
    assert p['title'] == 'British Milk'


def test_get_product_not_found(monkeypatch):
    monkeypatch.setattr(waitrose, '_search_raw', lambda term: [])
    with pytest.raises(WaitroseError, match='not found'):
        waitrose.get_product('999999')


def _trolley_node(items, products=None, failures=None):
    return {
        'products': products if products is not None else [
            {'id': '42-1-2', 'lineNumber': '42', 'name': 'Milk',
             'displayPrice': 1.25},
        ],
        'trolley': {
            'orderId': 'o-1',
            'trolleyItems': items,
            'trolleyTotals': {
                'totalEstimatedCost': {
                    'amount': sum(float(
                        (i.get('totalPrice') or {}).get('amount') or 0)
                        for i in items)},
                'currencyCode': 'GBP',
            },
        },
        'failures': failures or [],
    }


def _line(line_number='42', amount=2, total='2.50'):
    return {'lineNumber': line_number,
            'quantity': {'amount': amount, 'uom': 'UNIT'},
            'totalPrice': {'amount': total, 'currencyCode': 'GBP'}}


def test_basket_mapping(monkeypatch):
    monkeypatch.setattr(waitrose, '_trolley', lambda: _trolley_node([
        _line(amount=2, total='2.50'),
        _line(line_number='43', amount=1, total='1.00'),
    ], products=[
        {'id': '42-1-2', 'lineNumber': '42', 'name': 'Milk'},
        {'id': '43-1-2', 'lineNumber': '43', 'name': 'Butter'},
    ]))
    b = waitrose.basket()
    assert b['total_qty'] == 3
    assert b['total_cost'] == 3.5
    assert b['items'][0]['sku'] == '42-1-2'
    assert b['items'][0]['title'] == 'Milk'
    assert b['items'][0]['quantity'] == 2
    assert b['items'][0]['price'] == 1.25


def test_basket_empty(monkeypatch):
    monkeypatch.setattr(waitrose, '_trolley', lambda: _trolley_node([]))
    assert waitrose.basket() == {'items': [], 'total_qty': 0,
                                 'total_cost': 0}


def test_trolley_failures_raise(monkeypatch):
    """Failures come back inside the GraphQL payload; _trolley surfaces
    them as WaitroseError."""
    _patch_session(monkeypatch)
    monkeypatch.setattr(
        waitrose, '_graphql',
        lambda *a, **k: {'getTrolley': _trolley_node(
            [], failures=[{'type': 'X', 'message': 'boom'}])})
    with pytest.raises(WaitroseError, match='boom'):
        waitrose._trolley()


class _FakeSession:
    signed_in = True
    expired = False
    access_token = 'at-1'
    customer_id = 'c-1'
    order_id = 'o-1'
    branch_id = 'b-1'
    timeout = 5

    def require(self):
        return self


def _patch_session(monkeypatch):
    """Decouple write-path tests from the user's real session file."""
    monkeypatch.setattr(waitrose, '_SESSION', _FakeSession())


def _stub_trolley(monkeypatch, posted):
    _patch_session(monkeypatch)
    monkeypatch.setattr(waitrose, '_trolley', lambda: _trolley_node([]))
    monkeypatch.setattr(
        waitrose, '_graphql',
        lambda q, v, auth_token='unauthenticated', timeout=25:
        posted.update(query=q, variables=v, token=auth_token)
        or {'updateTrolleyItems': _trolley_node([])})


def test_basket_set_absolute_quantity(monkeypatch):
    posted = {}
    _stub_trolley(monkeypatch, posted)
    waitrose.basket_set('42-1-2', 3)
    assert posted['variables']['trolleyItemsInput'] == [
        {'lineNumber': '42', 'productId': '42-1-2',
         'quantity': {'amount': 3}}]


def test_basket_set_zero_removes(monkeypatch):
    posted = {}
    _stub_trolley(monkeypatch, posted)
    waitrose.basket_set('42-1-2', 0)
    assert posted['variables']['trolleyItemsInput'][0]['quantity'] == \
        {'amount': 0}


def test_basket_set_bare_line_number(monkeypatch):
    posted = {}
    _stub_trolley(monkeypatch, posted)
    waitrose.basket_set('42', 1)
    item = posted['variables']['trolleyItemsInput'][0]
    assert item['lineNumber'] == '42'
    assert item['productId'] == '42'


def test_basket_set_missing_update_raises(monkeypatch):
    _patch_session(monkeypatch)
    monkeypatch.setattr(waitrose, '_trolley', lambda: _trolley_node([]))
    monkeypatch.setattr(waitrose, '_graphql', lambda *a, **k: {})
    with pytest.raises(WaitroseError, match='Could not update'):
        waitrose.basket_set('42-1-2', 1)


def test_basket_set_failures_raise(monkeypatch):
    _patch_session(monkeypatch)
    monkeypatch.setattr(waitrose, '_trolley', lambda: _trolley_node([]))
    monkeypatch.setattr(
        waitrose, '_graphql',
        lambda *a, **k: {'updateTrolleyItems': _trolley_node(
            [], failures=[{'message': 'nope'}])})
    with pytest.raises(WaitroseError, match='nope'):
        waitrose.basket_set('42-1-2', 1)


# ------------------------------------------------------------------ session

def _session(tmp_path):
    return waitrose._Session(
        session_file=str(tmp_path / 'session.json'))


def _payload(expires_in=3600, failures=None):
    return {
        'accessToken': 'at-1', 'refreshToken': 'rt-1',
        'customerId': 'c-1', 'customerOrderId': 'o-1',
        'defaultBranchId': 'b-1', 'expiresIn': expires_in,
        'failures': failures or [],
    }


def test_session_store_and_expiry(tmp_path, monkeypatch):
    s = _session(tmp_path)
    monkeypatch.setattr(waitrose, 'time', type('T', (), {'time':
                                                         lambda: 100.0}))
    s.store(_payload(expires_in=100))
    assert s.signed_in
    assert not s.expired
    monkeypatch.setattr(waitrose, 'time', type('T', (), {'time':
                                                         lambda: 201.0}))
    assert s.expired


def test_session_store_failures_raise(tmp_path):
    s = _session(tmp_path)
    with pytest.raises(WaitroseError, match='bad creds'):
        s.store(_payload(failures=[{'type': 'AUTH', 'message': 'bad creds'}]))


def test_session_refresh(monkeypatch, tmp_path):
    s = _session(tmp_path)
    s.data = {'accessToken': 'old', 'refreshToken': 'rt-1',
              'customerId': 'c-1', 'customerOrderId': 'o-1',
              'expiresAt': 0}
    seen = {}

    def fake(query, variables, auth_token='unauthenticated', timeout=25):
        seen['token'] = auth_token
        seen['variables'] = variables
        return _payload()

    monkeypatch.setattr(waitrose, '_graphql', fake)
    s.refresh()
    assert seen['token'] == 'rt-1'
    assert seen['variables']['input']['customerId'] == 'c-1'
    assert s.access_token == 'at-1'


def test_session_require_raises_when_not_signed_in():
    s = waitrose._Session(session_file='/nonexistent/session.json')
    with pytest.raises(WaitroseError, match='Not signed in'):
        s.require()


def test_session_require_refreshes_expired(monkeypatch, tmp_path):
    s = _session(tmp_path)
    s.data = {'accessToken': 'old', 'refreshToken': 'rt-1',
              'customerId': 'c-1', 'customerOrderId': 'o-1',
              'expiresAt': 0}
    monkeypatch.setattr(waitrose, '_graphql', lambda *a, **k: _payload())
    s.require()
    assert s.access_token == 'at-1'


def test_session_require_refresh_failure(monkeypatch, tmp_path):
    s = _session(tmp_path)
    s.data = {'accessToken': 'old', 'refreshToken': 'rt-1',
              'customerId': 'c-1', 'customerOrderId': 'o-1',
              'expiresAt': 0}

    def fail(*a, **k):
        raise WaitroseError('refresh broken')

    monkeypatch.setattr(waitrose, '_graphql', fail)
    with pytest.raises(WaitroseError, match='sign in again'):
        s.require()


def test_session_persistence_roundtrip(tmp_path):
    path = str(tmp_path / 'session.json')
    s1 = waitrose._Session(session_file=path)
    s1.store(_payload())
    s2 = waitrose._Session(session_file=path)
    assert s2.access_token == 'at-1'
    assert s2.customer_id == 'c-1'
    assert s2.order_id == 'o-1'


def test_session_load_bad_file(tmp_path):
    path = tmp_path / 'session.json'
    path.write_text('not json')
    s = waitrose._Session(session_file=str(path))
    assert not s.signed_in


# --------------------------------------------------------------------- auth

def _patch_auth(monkeypatch, tmp_path):
    monkeypatch.setattr(waitrose, '_SESSION_FILE',
                        str(tmp_path / 'session.json'))
    monkeypatch.setattr(waitrose, '_CREDENTIALS_FILE',
                        str(tmp_path / 'creds.json'))


def test_auth_status_signed_out_no_creds(monkeypatch, tmp_path):
    _patch_auth(monkeypatch, tmp_path)
    status = waitrose.auth_status()
    assert status['signed_in'] is False
    assert 'credentials' in status['note'].lower()


def test_auth_status_signed_out_with_creds(monkeypatch, tmp_path):
    _patch_auth(monkeypatch, tmp_path)
    import json
    (tmp_path / 'creds.json').write_text(
        json.dumps({'email': 'a@b.c', 'password': 'x'}))
    status = waitrose.auth_status()
    assert status['signed_in'] is False
    assert 'Saved credentials' in status['note']


def test_auth_status_signed_in(monkeypatch, tmp_path):
    _patch_auth(monkeypatch, tmp_path)
    _patch_session(monkeypatch)
    status = waitrose.auth_status()
    assert status['signed_in'] is True
    assert 'o-1' in status['note']


def _wait_idle(timeout=5.0):
    """Wait for any in-flight background login thread to finish."""
    import time
    deadline = time.time() + timeout
    while waitrose.login_status()['running'] and time.time() < deadline:
        time.sleep(0.05)


def _reset_login_state():
    """Reset the module login state so no test leaks into the next."""
    waitrose._LOGIN_STATE.clear()
    waitrose._LOGIN_STATE.update({'running': False, 'error': '', 'note': ''})


def test_login_without_credentials(monkeypatch, tmp_path):
    _patch_auth(monkeypatch, tmp_path)
    _wait_idle()
    assert waitrose.login() is True
    _wait_idle()
    status = waitrose.login_status()
    assert status['running'] is False
    assert 'credentials' in status['error'].lower()
    _reset_login_state()


def test_login_flow_success(monkeypatch, tmp_path):
    import json
    _patch_auth(monkeypatch, tmp_path)
    (tmp_path / 'creds.json').write_text(
        json.dumps({'email': 'a@b.c', 'password': 'x'}))
    monkeypatch.setattr(
        waitrose, '_graphql',
        lambda q, v, auth_token='unauthenticated', timeout=25:
        _payload())
    stored = {}
    fake_session = _FakeSession()
    fake_session.signed_in = False

    def store(payload):
        stored.update(payload)
        fake_session.signed_in = True
        return payload

    fake_session.store = store
    monkeypatch.setattr(waitrose, '_SESSION', fake_session)
    _wait_idle()
    waitrose.login()
    _wait_idle()
    status = waitrose.login_status()
    assert status['running'] is False
    assert status['error'] == ''
    assert fake_session.signed_in
    assert stored.get('accessToken') == 'at-1'
    _reset_login_state()


def test_login_rejects_double_start(monkeypatch, tmp_path):
    _patch_auth(monkeypatch, tmp_path)
    _wait_idle()
    waitrose._LOGIN_STATE.update({'running': True, 'error': '', 'note': ''})
    assert waitrose.login() is False
    _reset_login_state()


def test_checkout_url():
    assert waitrose.checkout_url().startswith('https://www.waitrose.com')


def test_parse_qty():
    assert waitrose.parse_qty('2 cartons') == 2
    assert waitrose.parse_qty('a bit of stuff') == 1
    assert waitrose.parse_qty(None) == 1


def test_adapter_uses_module_functions(monkeypatch):
    """The registry adapter must resolve through module globals so
    monkeypatching providers.waitrose.search also affects the adapter."""
    grocer = app_module.providers.get_grocer('waitrose')
    monkeypatch.setattr(
        waitrose, 'search',
        lambda q, limit=5: [{'sku': 'x', 'title': q, 'price': 1, 'brand': '',
                             'unit_price': None, 'unit_of_measure': '',
                             'image_url': '', 'on_offer': False}])
    assert grocer.search('cheese')[0]['sku'] == 'x'
