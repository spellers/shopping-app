import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module


def test_index_redirects_to_meal_tracker(client):
    response = client.get('/')
    assert response.status_code == 302
    assert '/meal_tracker' in response.headers['Location']


def test_meal_tracker_page(client):
    response = client.get('/meal_tracker')
    assert response.status_code == 200
    assert b'Meal Planner' in response.data


def test_add_meal_page(client):
    response = client.get('/add_meal')
    assert response.status_code == 200
    assert b'Add New Meal' in response.data


def test_add_meal_post(client):
    response = client.post('/add_meal', data={
        'name': 'Test Meal',
        'description': 'a test meal',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test Meal' in response.data


def test_meal_detail(client, sample_meal):
    response = client.get(f'/meal_tracker/{sample_meal}')
    assert response.status_code == 200
    assert b'Test Meal' in response.data


def test_meal_detail_not_found(client):
    response = client.get('/meal_tracker/99999')
    assert response.status_code == 404


def test_edit_meal_page(client, sample_meal):
    response = client.get(f'/edit_meal/{sample_meal}')
    assert response.status_code == 200


def test_edit_meal_post(client, sample_meal):
    response = client.post(f'/edit_meal/{sample_meal}', data={
        'name': 'Updated Meal',
        'description': 'updated',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Updated Meal' in response.data


def test_delete_meal(client, sample_meal):
    response = client.post(f'/delete_meal/{sample_meal}', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    row = db.execute('SELECT * FROM meals WHERE id=?', (sample_meal,)).fetchone()
    db.close()
    assert row is None


def test_add_ingredient(client, sample_meal):
    response = client.post(f'/add_ingredient/{sample_meal}', data={
        'name': 'new_ingredient',
        'quantity': '2',
        'unit': 'cups',
    }, follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    row = db.execute(
        'SELECT * FROM ingredients WHERE meal_id=? AND name=?',
        (sample_meal, 'new_ingredient')
    ).fetchone()
    db.close()
    assert row is not None


def test_delete_ingredient(client, sample_meal):
    db = app_module.get_db()
    row = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()
    ingredient_id = row['id']
    db.close()

    response = client.post(f'/delete_ingredient/{ingredient_id}', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    remaining = db.execute('SELECT * FROM ingredients WHERE id=?', (ingredient_id,)).fetchone()
    db.close()
    assert remaining is None


def test_persistent_ingredients_page(client):
    response = client.get('/persistent_ingredients')
    assert response.status_code == 200
    assert b'Persistent Ingredients' in response.data


def test_add_persistent_ingredient(client):
    response = client.post('/persistent_ingredients', data={
        'name': 'Salt',
        'category': 'pantry',
    }, follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    row = db.execute("SELECT * FROM persistent_ingredients WHERE name='Salt'").fetchone()
    db.close()
    assert row is not None


def test_add_persistent_to_meal(client, sample_meal):
    db = app_module.get_db()
    db.execute("INSERT INTO persistent_ingredients (name, category) VALUES (?, ?)", ('Oil', 'pantry'))
    db.commit()
    pid = db.execute("SELECT id FROM persistent_ingredients WHERE name='Oil'").fetchone()['id']
    db.close()

    response = client.post(f'/meal_tracker/{sample_meal}/add_persistent', data={
        'persistent_id': pid,
        'quantity': '1 tbsp',
    }, follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    link = db.execute(
        'SELECT * FROM persistent_ingredient_meals WHERE meal_id=? AND persistent_ingredient_id=?',
        (sample_meal, pid)
    ).fetchone()
    db.close()
    assert link is not None


def test_remove_persistent_from_meal(client, sample_meal):
    db = app_module.get_db()
    db.execute("INSERT INTO persistent_ingredients (name, category) VALUES (?, ?)", ('Oil', 'pantry'))
    db.commit()
    pid = db.execute("SELECT id FROM persistent_ingredients WHERE name='Oil'").fetchone()['id']
    db.execute('INSERT INTO persistent_ingredient_meals (meal_id, persistent_ingredient_id, quantity) VALUES (?, ?, ?)',
               (sample_meal, pid, '1 tbsp'))
    db.commit()
    link_id = db.execute(
        'SELECT id FROM persistent_ingredient_meals WHERE meal_id=? AND persistent_ingredient_id=?',
        (sample_meal, pid)
    ).fetchone()['id']
    db.close()

    response = client.post(f'/meal_tracker/{sample_meal}/remove_persistent/{link_id}', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    remaining = db.execute('SELECT * FROM persistent_ingredient_meals WHERE id=?', (link_id,)).fetchone()
    db.close()
    assert remaining is None


def test_votes_page(client):
    response = client.get('/votes')
    assert response.status_code == 200
    assert b'Voting' in response.data


def test_create_vote(client, sample_meal):
    response = client.post('/votes', data={
        'title': 'Weekend meal',
        'description': 'pick one',
        'meal_ids': [str(sample_meal)],
    }, follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    vote = db.execute("SELECT * FROM votes WHERE name='Weekend meal'").fetchone()
    db.close()
    assert vote is not None


def test_vote_detail(client, sample_meal):
    db = app_module.get_db()
    db.execute("INSERT INTO votes (name) VALUES ('Detail Vote')")
    db.commit()
    vote_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.execute("INSERT INTO vote_options (vote_id, meal_name) VALUES (?, ?)", (vote_id, 'Test Meal'))
    db.commit()
    db.close()

    response = client.get(f'/vote/{vote_id}')
    assert response.status_code == 200
    assert b'Detail Vote' in response.data


def test_vote_detail_not_found(client):
    assert client.get('/vote/99999').status_code == 404


def test_cast_vote_and_results(client, sample_meal):
    db = app_module.get_db()
    db.execute("INSERT INTO votes (name) VALUES ('Cast Vote')")
    db.commit()
    vote_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.execute("INSERT INTO vote_options (vote_id, meal_name) VALUES (?, ?)", (vote_id, 'Test Meal'))
    db.commit()
    opt_id = db.execute('SELECT id FROM vote_options WHERE vote_id=?', (vote_id,)).fetchone()['id']
    db.close()

    response = client.post(f'/vote/{vote_id}/cast', data={'option_ids': [str(opt_id)]}, follow_redirects=True)
    assert response.status_code == 200

    db = app_module.get_db()
    cast = db.execute('SELECT * FROM vote_votes WHERE vote_id=?', (vote_id,)).fetchone()
    db.close()
    assert cast is not None

    response = client.get(f'/vote/{vote_id}/results')
    assert response.status_code == 200
    assert b'Results' in response.data


def test_shopping_list_page(client):
    response = client.get('/shopping_list')
    assert response.status_code == 200
    assert b'Shopping List' in response.data


def test_create_shopping_list(client, sample_meal):
    response = client.post('/create_shopping_list', data={
        'meal_ids': ['Test Meal'],
    }, follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    items = db.execute('SELECT * FROM shopping_list_items').fetchall()
    db.close()
    names = {i['name'] for i in items}
    assert 'Ingredient1' in names

    # Selected meals are recorded and shown on the shopping list page
    db2 = app_module.get_db()
    recorded = db2.execute('SELECT meal_id FROM shopping_list_meals').fetchall()
    db2.close()
    assert len(recorded) == 1

    response = client.get('/shopping_list')
    assert response.status_code == 200
    assert b'Selected meals' in response.data
    assert b'Test Meal' in response.data


def test_shareable_ingredient_one_unit_across_meals(client):
    """A shared ingredient (rice) used by two meals appears once, with no xN."""
    db = app_module.get_db()
    for i in (1, 2):
        db.execute('INSERT INTO meals (name, description) VALUES (?, ?)',
                   (f'Rice Meal {i}', ''))
        meal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.execute('INSERT INTO ingredients (meal_id, name, quantity, unit, shareable) '
                   'VALUES (?, ?, ?, ?, 1)', (meal_id, 'rice', '', '',))
    db.commit()
    db.close()

    client.post('/create_shopping_list', data={
        'meal_ids': ['Rice Meal 1', 'Rice Meal 2'],
    }, follow_redirects=True)

    db = app_module.get_db()
    items = db.execute('SELECT * FROM shopping_list_items WHERE name=?', ('Rice',)).fetchall()
    db.close()
    assert len(items) == 1
    assert items[0]['quantity'] in ('', None)


def test_per_meal_ingredient_multiplies_by_meals(client):
    """A non-shared ingredient (chicken) in two meals becomes x2 on the list."""
    db = app_module.get_db()
    for i in (1, 2):
        db.execute('INSERT INTO meals (name, description) VALUES (?, ?)',
                   (f'Chicken Meal {i}', ''))
        meal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.execute('INSERT INTO ingredients (meal_id, name, quantity, unit, shareable) '
                   'VALUES (?, ?, ?, ?, 0)', (meal_id, 'chicken', '', '',))
    db.commit()
    db.close()

    client.post('/create_shopping_list', data={
        'meal_ids': ['Chicken Meal 1', 'Chicken Meal 2'],
    }, follow_redirects=True)

    db = app_module.get_db()
    items = db.execute('SELECT * FROM shopping_list_items WHERE name=?', ('Chicken',)).fetchall()
    db.close()
    assert len(items) == 1
    assert items[0]['quantity'] == 'x2'


def test_per_meal_ingredient_single_meal_no_multiplier(client, sample_meal):
    """Non-shared ingredient in just one meal keeps its plain quantity."""
    db = app_module.get_db()
    db.execute('UPDATE ingredients SET shareable=0 WHERE meal_id=?', (sample_meal,))
    db.commit()
    db.close()

    client.post('/create_shopping_list', data={'meal_ids': ['Test Meal']},
                follow_redirects=True)

    db = app_module.get_db()
    items = db.execute('SELECT * FROM shopping_list_items').fetchall()
    db.close()
    assert len(items) == 1
    assert items[0]['quantity'] == '1'


def test_sku_falls_back_to_same_named_persistent(client):
    """Unmatched regular ingredient inherits SKU of a matched same-named persistent ingredient."""
    db = app_module.get_db()
    db.execute('INSERT INTO meals (name, description) VALUES (?, ?)', ('Soy Meal', ''))
    meal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.execute('INSERT INTO ingredients (meal_id, name, quantity, unit, shareable) '
               'VALUES (?, ?, ?, ?, 1)', (meal_id, 'soy sauce', '', ''))
    db.execute('INSERT INTO persistent_ingredients (name, tesco_sku) VALUES (?, ?)',
               ('soy sauce', '294781206'))
    db.commit()
    db.close()

    client.post('/create_shopping_list', data={'meal_ids': ['Soy Meal']},
                follow_redirects=True)

    db = app_module.get_db()
    items = db.execute('SELECT * FROM shopping_list_items').fetchall()
    db.close()
    assert items[0]['name'] == 'Soy Sauce'
    assert items[0]['tesco_sku'] == '294781206'


def test_toggle_shareable_route(client, sample_meal):
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?',
                        (sample_meal,)).fetchone()['id']
    db.close()

    response = client.post(f'/toggle_shareable/{ing_id}/ing', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    val = db.execute('SELECT shareable FROM ingredients WHERE id=?',
                     (ing_id,)).fetchone()['shareable']
    db.close()
    assert val == 0  # was default 1, now flipped

    client.post(f'/toggle_shareable/{ing_id}/ing', follow_redirects=True)
    db = app_module.get_db()
    val = db.execute('SELECT shareable FROM ingredients WHERE id=?',
                     (ing_id,)).fetchone()['shareable']
    db.close()
    assert val == 1  # flipped back


def test_toggle_shareable_rejects_bad_kind(client):
    response = client.post('/toggle_shareable/1/bogus', follow_redirects=False)
    assert response.status_code == 404


def test_toggle_shopping_item(client):
    db = app_module.get_db()
    db.execute("INSERT INTO shopping_list_items (name, quantity, checked) VALUES (?, ?, 0)", ('Milk', '1L'))
    db.commit()
    item_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.close()

    response = client.post(f'/shopping_list/{item_id}/toggle', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    checked = db.execute('SELECT checked FROM shopping_list_items WHERE id=?', (item_id,)).fetchone()['checked']
    db.close()
    assert checked == 1


def test_delete_shopping_item(client):
    db = app_module.get_db()
    db.execute("INSERT INTO shopping_list_items (name, quantity, checked) VALUES (?, ?, 0)", ('Milk', '1L'))
    db.commit()
    item_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.close()

    response = client.post(f'/shopping_list/{item_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    remaining = db.execute('SELECT * FROM shopping_list_items WHERE id=?', (item_id,)).fetchone()
    db.close()
    assert remaining is None


# ---------------------------------------------------------------------------
# Tesco integration (basketeer CLI). All Tesco API calls are mocked so the
# suite never touches the network or a real session.
# ---------------------------------------------------------------------------

def _mock_search(term):
    return [{
        'sku': '999000111',
        'title': 'Mock ' + term,
        'brand': 'TESCO',
        'price': 1.99,
        'unit_price': 1.99,
        'unit_of_measure': 'each',
        'image_url': '',
        'on_offer': False,
    }]


def test_tesco_status_page(client, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'auth_status', lambda: {'signed_in': False})
    response = client.get('/tesco')
    assert response.status_code == 200
    assert b'Not signed in' in response.data


def test_tesco_status_signed_in(client, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'auth_status', lambda: {'signed_in': True})
    response = client.get('/tesco')
    assert response.status_code == 200
    assert b'Signed in' in response.data


def test_tesco_match_ingredient(client, sample_meal, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'search', lambda q, limit=5: _mock_search(q))
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    response = client.post(f'/tesco/match/{ing_id}', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    sku = db.execute('SELECT tesco_sku FROM ingredients WHERE id=?', (ing_id,)).fetchone()['tesco_sku']
    cached = db.execute('SELECT * FROM tesco_products WHERE sku=?', ('999000111',)).fetchone()
    db.close()
    assert sku == '999000111'
    assert cached is not None


def test_tesco_match_no_results(client, sample_meal, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'search', lambda q, limit=5: [])
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    response = client.post(f'/tesco/match/{ing_id}', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    sku = db.execute('SELECT tesco_sku FROM ingredients WHERE id=?', (ing_id,)).fetchone()['tesco_sku']
    db.close()
    assert sku in (None, '')


def test_tesco_match_persistent(client, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'search', lambda q, limit=5: _mock_search(q))
    db = app_module.get_db()
    db.execute("INSERT INTO persistent_ingredients (name, category) VALUES (?, ?)", ('Eggs', 'dairy'))
    pid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.commit()
    db.close()
    response = client.post(f'/tesco/match_persistent/{pid}', follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    sku = db.execute('SELECT tesco_sku FROM persistent_ingredients WHERE id=?', (pid,)).fetchone()['tesco_sku']
    db.close()
    assert sku == '999000111'


def _mock_multi_search(term):
    return [
        {'sku': '999000101', 'title': 'Option A ' + term, 'brand': 'TESCO', 'price': 0.99,
         'unit_price': None, 'unit_of_measure': None, 'image_url': '', 'on_offer': False},
        {'sku': '999000102', 'title': 'Option B ' + term, 'brand': 'TESCO', 'price': 1.49,
         'unit_price': 1.49, 'unit_of_measure': 'each', 'image_url': '', 'on_offer': True},
        {'sku': '999000103', 'title': 'Option C ' + term, 'brand': 'TESCO', 'price': 2.25,
         'unit_price': None, 'unit_of_measure': None, 'image_url': '', 'on_offer': False},
    ]


def test_tesco_suggest_ingredient_modal(client, sample_meal, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'search', lambda q, limit=5: _mock_multi_search(q))
    db = app_module.get_db()
    ing = db.execute('SELECT id, name FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()
    db.close()
    response = client.get(f'/tesco/suggest/{ing["id"]}/ing')
    assert response.status_code == 200
    assert b'Choose a product for' in response.data
    assert b'Option A ' + ing['name'].encode() in response.data
    assert b'Option C ' + ing['name'].encode() in response.data
    assert b'/tesco/select/' + str(ing['id']).encode() + b'/ing' in response.data


def test_tesco_suggest_persistent_modal(client, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'search', lambda q, limit=5: _mock_multi_search(q))
    db = app_module.get_db()
    db.execute("INSERT INTO persistent_ingredients (name, category) VALUES (?, ?)", ('Butter', 'dairy'))
    pid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.commit()
    db.close()
    response = client.get(f'/tesco/suggest/{pid}/persist')
    assert response.status_code == 200
    assert b'Option A Butter' in response.data
    assert b'/tesco/select/' + str(pid).encode() + b'/persist' in response.data


def test_tesco_suggest_error_shown(client, sample_meal, monkeypatch):
    def _boom(q, limit=5):
        raise app_module.tesco.TescoError('Tesco API timed out')
    monkeypatch.setattr(app_module.tesco, 'search', _boom)
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    response = client.get(f'/tesco/suggest/{ing_id}/ing')
    assert response.status_code == 200
    assert b'Tesco API timed out' in response.data


def test_tesco_suggest_unknown_ingredient(client):
    assert client.get('/tesco/suggest/999999/ing').status_code == 404
    assert client.get('/tesco/suggest/1/wrong').status_code == 404


def test_tesco_select_ingredient(client, sample_meal):
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    response = client.post(
        f'/tesco/select/{ing_id}/ing',
        data={'sku': '555666777', 'title': 'My Chosen Product'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'My Chosen Product' in response.data
    db = app_module.get_db()
    sku = db.execute('SELECT tesco_sku FROM ingredients WHERE id=?', (ing_id,)).fetchone()['tesco_sku']
    db.close()
    assert sku == '555666777'


def test_tesco_select_persistent_rematch(client, monkeypatch):
    # Pre-match to the "wrong" product, then re-match to another one.
    monkeypatch.setattr(app_module.tesco, 'search', lambda q, limit=5: _mock_search(q))
    db = app_module.get_db()
    db.execute("INSERT INTO persistent_ingredients (name, category) VALUES (?, ?)", ('Cheese', 'dairy'))
    pid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.commit()
    db.close()
    client.post(f'/tesco/match_persistent/{pid}')
    response = client.post(
        f'/tesco/select/{pid}/persist',
        data={'sku': '888999000', 'title': 'Chosen Cheese'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db = app_module.get_db()
    sku = db.execute('SELECT tesco_sku FROM persistent_ingredients WHERE id=?', (pid,)).fetchone()['tesco_sku']
    db.close()
    assert sku == '888999000'


def test_tesco_select_missing_sku_rejected(client, sample_meal):
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    assert client.post(f'/tesco/select/{ing_id}/ing', data={'sku': ''}).status_code == 400


def _mock_get_product(sku):
    return {
        'sku': str(sku),
        'title': 'Manual SKU Product ' + str(sku),
        'brand': 'TESCO',
        'price': 3.50,
        'unit_price': None,
        'unit_of_measure': None,
        'image_url': '',
        'on_offer': False,
    }


def test_tesco_select_sku_ingredient(client, sample_meal, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'get_product', _mock_get_product)
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    response = client.post(
        f'/tesco/select_sku/{ing_id}/ing',
        data={'sku': '123456789'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'Manual SKU Product 123456789' in response.data
    db = app_module.get_db()
    sku = db.execute('SELECT tesco_sku FROM ingredients WHERE id=?', (ing_id,)).fetchone()['tesco_sku']
    db.close()
    assert sku == '123456789'


def test_tesco_select_sku_persistent(client, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'get_product', _mock_get_product)
    db = app_module.get_db()
    db.execute("INSERT INTO persistent_ingredients (name, category) VALUES (?, ?)", ('Basil', 'herbs'))
    pid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.commit()
    db.close()
    response = client.post(
        f'/tesco/select_sku/{pid}/persist',
        data={'sku': '987654321'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db = app_module.get_db()
    sku = db.execute('SELECT tesco_sku FROM persistent_ingredients WHERE id=?', (pid,)).fetchone()['tesco_sku']
    db.close()
    assert sku == '987654321'


def test_tesco_select_sku_unknown_lookup_still_saves(client, sample_meal, monkeypatch):
    def _boom(sku):
        raise app_module.tesco.TescoError('unknown product')
    monkeypatch.setattr(app_module.tesco, 'get_product', _boom)
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    response = client.post(
        f'/tesco/select_sku/{ing_id}/ing',
        data={'sku': '424242424'},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'saved it anyway' in response.data
    db = app_module.get_db()
    sku = db.execute('SELECT tesco_sku FROM ingredients WHERE id=?', (ing_id,)).fetchone()['tesco_sku']
    db.close()
    assert sku == '424242424'


def test_tesco_select_sku_rejects_non_numeric(client, sample_meal):
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    assert client.post(f'/tesco/select_sku/{ing_id}/ing', data={'sku': 'abc'}).status_code == 400
    assert client.post(f'/tesco/select_sku/{ing_id}/ing', data={'sku': ''}).status_code == 400


def test_tesco_select_sku_unknown_ingredient(client):
    assert client.post('/tesco/select_sku/999999/ing', data={'sku': '123'}).status_code == 404
    assert client.post('/tesco/select_sku/1/wrong', data={'sku': '123'}).status_code == 404


def test_tesco_suggest_modal_shows_manual_sku_field(client, sample_meal, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'search', lambda q, limit=5: _mock_search(q))
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.close()
    response = client.get(f'/tesco/suggest/{ing_id}/ing')
    assert response.status_code == 200
    assert b'/tesco/select_sku/' + str(ing_id).encode() + b'/ing' in response.data
    assert b'Enter a Tesco product number (SKU)' in response.data


def test_create_shopping_list_carries_tesco_sku(client, sample_meal, monkeypatch):
    # Pre-match the regular ingredient to a Tesco SKU, then build the list.
    db = app_module.get_db()
    ing_id = db.execute('SELECT id FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()['id']
    db.execute('UPDATE ingredients SET tesco_sku=? WHERE id=?', ('777888999', ing_id))
    db.commit()
    db.close()
    response = client.post('/create_shopping_list', data={'meal_ids': ['Test Meal']}, follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    item = db.execute('SELECT * FROM shopping_list_items').fetchone()
    db.close()
    assert item['tesco_sku'] == '777888999'


def test_tesco_add_to_basket_unsigned(client, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'auth_status', lambda: {'signed_in': False})
    db = app_module.get_db()
    db.execute("INSERT INTO shopping_list_items (name, quantity, checked, tesco_sku) VALUES (?, ?, 0, ?)", ('Milk', '2', '777888999'))
    db.commit()
    db.close()
    response = client.post('/tesco/add_to_basket', follow_redirects=True)
    assert response.status_code == 200
    assert b'Sign in to Tesco first' in response.data


def test_tesco_add_to_basket(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.tesco, 'auth_status', lambda: {'signed_in': True})
    monkeypatch.setattr(app_module.tesco, 'basket_set', lambda sku, qty: calls.append((sku, qty)))
    db = app_module.get_db()
    db.execute("INSERT INTO shopping_list_items (name, quantity, checked, tesco_sku) VALUES (?, ?, 0, ?)", ('Milk', '2', '777888999'))
    db.execute("INSERT INTO shopping_list_items (name, quantity, checked, tesco_sku) VALUES (?, ?, 0, '')", ('Butter', '1'))
    db.commit()
    db.close()
    response = client.post('/tesco/add_to_basket', follow_redirects=True)
    assert response.status_code == 200
    # Only the matched item is pushed, with its parsed quantity.
    assert calls == [('777888999', 2)]
    assert b'Added 1 item(s)' in response.data


def test_tesco_add_to_basket_no_matches(client, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'auth_status', lambda: {'signed_in': True})
    db = app_module.get_db()
    db.execute("INSERT INTO shopping_list_items (name, quantity, checked, tesco_sku) VALUES (?, ?, 0, '')", ('Butter', '1'))
    db.commit()
    db.close()
    response = client.post('/tesco/add_to_basket', follow_redirects=True)
    assert response.status_code == 200
    assert b'No shopping list items have Tesco products matched' in response.data


def test_shopping_list_shows_tesco_product(client, monkeypatch):
    monkeypatch.setattr(app_module.tesco, 'auth_status', lambda: {'signed_in': True})
    db = app_module.get_db()
    db.execute(
        'INSERT INTO tesco_products (sku, title, brand, price, unit_price, unit_of_measure, image_url, matched_term, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        ('777888999', 'Tesco Semi Skimmed Milk 2L', 'TESCO', 1.45, 1.45, 'each', '', 'milk', 'now')
    )
    db.execute("INSERT INTO shopping_list_items (name, quantity, checked, tesco_sku) VALUES (?, ?, 0, ?)", ('Milk', '1', '777888999'))
    db.execute("INSERT INTO shopping_list_items (name, quantity, checked, tesco_sku) VALUES (?, ?, 0, '')", ('Butter', '1'))
    db.commit()
    db.close()
    response = client.get('/shopping_list')
    assert response.status_code == 200
    assert b'Tesco Semi Skimmed Milk 2L' in response.data
    assert b'Add 1 matched item(s) to Tesco basket' in response.data


def test_tesco_select_caches_product(client, sample_meal, monkeypatch):
    """Picking a product in the modal must write a tesco_products cache row,
    so the shopping list can later resolve title/price for that SKU."""
    monkeypatch.setattr(app_module.tesco, 'auth_status', lambda: {'signed_in': False})
    db = app_module.get_db()
    ing = db.execute('SELECT id, name FROM ingredients WHERE meal_id=?', (sample_meal,)).fetchone()
    db.close()
    response = client.post(f'/tesco/select/{ing["id"]}/ing', data={
        'sku': '999000102',
        'title': 'Option B ' + ing['name'],
        'brand': 'TESCO',
        'price': '1.49',
        'unit_price': '1.49',
        'unit_of_measure': 'each',
        'image_url': '',
        'name': ing['name'],
    }, follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    row = db.execute('SELECT * FROM tesco_products WHERE sku=?', ('999000102',)).fetchone()
    db.close()
    assert row is not None
    assert row['title'] == 'Option B ' + ing['name']
    assert row['price'] == 1.49
    assert row['matched_term'] == ing['name']


def test_shopping_list_live_fallback_fills_cache(client, monkeypatch):
    """An item with a SKU but no cache row (pre-fix data) should get a live
    lookup, cache it, and show the product title instead of Not connected."""
    monkeypatch.setattr(app_module.tesco, 'auth_status', lambda: {'signed_in': False})
    monkeypatch.setattr(
        app_module.tesco, 'get_product',
        lambda sku: {'sku': sku, 'title': 'Tesco Live Lookup Item 500g', 'brand': 'TESCO',
                     'price': 0.75, 'unit_price': 1.5, 'unit_of_measure': 'kg',
                     'image_url': '', 'on_offer': False},
    )
    db = app_module.get_db()
    db.execute(
        "INSERT INTO shopping_list_items (name, quantity, checked, tesco_sku) VALUES (?, ?, 0, ?)",
        ('Mystery', '1', '555666777')
    )
    db.commit()
    db.close()
    response = client.get('/shopping_list')
    assert response.status_code == 200
    assert b'Tesco Live Lookup Item 500g' in response.data
    assert b'Not connected' not in response.data
    db = app_module.get_db()
    row = db.execute('SELECT * FROM tesco_products WHERE sku=?', ('555666777',)).fetchone()
    db.close()
    assert row is not None
    assert row['title'] == 'Tesco Live Lookup Item 500g'


# ---------------------------------------------------------------------------
# tesco.parse_qty - free-text quantity -> basket count
# ---------------------------------------------------------------------------

import tesco as tesco_module


def test_parse_qty_weight_volume_means_one():
    assert tesco_module.parse_qty('200g') == 1
    assert tesco_module.parse_qty('1kg') == 1
    assert tesco_module.parse_qty('500ml') == 1
    assert tesco_module.parse_qty('100ml') == 1
    assert tesco_module.parse_qty('400 g') == 1


def test_parse_qty_plain_counts():
    assert tesco_module.parse_qty('2') == 2
    assert tesco_module.parse_qty('2 loaves') == 2
    assert tesco_module.parse_qty('3 pack') == 3
    assert tesco_module.parse_qty('6 x 200ml') == 6


def test_parse_qty_kitchen_measures_mean_one():
    assert tesco_module.parse_qty('2 cups') == 1
    assert tesco_module.parse_qty('2 tsp') == 1
    assert tesco_module.parse_qty('1.5 tbsp') == 1


def test_parse_qty_x_prefix_counts():
    assert tesco_module.parse_qty('x4') == 4
    assert tesco_module.parse_qty('x 4') == 4
    assert tesco_module.parse_qty('x2 pack') == 2
    assert tesco_module.parse_qty('x2 cups') == 1


def test_parse_qty_empty_defaults_to_one():
    assert tesco_module.parse_qty('') == 1
    assert tesco_module.parse_qty(None) == 1


# --- v1.2.0 ---------------------------------------------------------------

def test_seed_starts_empty_db_with_starter_meals(client):
    db = app_module.get_db()
    meals = db.execute('SELECT id, name FROM meals').fetchall()
    counts = {
        m['id']: db.execute(
            'SELECT '
            '(SELECT COUNT(*) FROM ingredients WHERE meal_id=?) + '
            '(SELECT COUNT(*) FROM persistent_ingredient_meals WHERE meal_id=?) AS n',
            (m['id'], m['id'])).fetchone()['n']
        for m in meals
    }
    pis = db.execute('SELECT name FROM persistent_ingredients').fetchall()
    db.close()
    names = {m['name'] for m in meals}
    assert 'Chicken Fried Rice' in names
    assert 'Thai Red Curry' in names
    assert len(meals) == 6
    # every starter meal uses 4-5 ingredients total
    for m in meals:
        assert 4 <= counts[m['id']] <= 5, f'{m["name"]} has {counts[m["id"]]} ingredients'
    pi_names = {p['name'] for p in pis}
    assert {'Rice', 'Soy Sauce', 'Butter', 'Cheddar Cheese', 'Pasta'} <= pi_names


def test_seed_does_not_run_twice(client):
    client.post('/add_meal', data={'name': 'Extra Meal', 'description': ''},
                follow_redirects=True)
    response = client.get('/meal_tracker', follow_redirects=True)
    db = app_module.get_db()
    n = db.execute("SELECT COUNT(*) FROM meals WHERE name='Extra Meal'").fetchone()[0]
    db.close()
    assert n == 1  # seeded once, not re-seeded on every init


def test_help_page_shows_version(client):
    import updates
    response = client.get('/help')
    assert response.status_code == 200
    assert updates.VERSION.encode() in response.data
    assert b'Help' in response.data


def test_meal_tile_has_no_delete_button(client):
    response = client.get('/meal_tracker')
    assert b'/delete_meal/' not in response.data


def test_meal_detail_keeps_delete_button(client, sample_meal):
    response = client.get(f'/meal_tracker/{sample_meal}')
    assert response.status_code == 200
    assert f'/delete_meal/{sample_meal}'.encode() in response.data


def test_delete_persistent_ingredient(client):
    response = client.get('/persistent_ingredients')
    assert response.status_code == 200
    db = app_module.get_db()
    pi = db.execute('SELECT id FROM persistent_ingredients LIMIT 1').fetchone()
    # link it to a meal so the cleanup path is exercised
    db.execute('INSERT INTO meals (name) VALUES (? )', ('PI Link Meal',))
    meal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.execute('INSERT INTO persistent_ingredient_meals (meal_id, persistent_ingredient_id) '
               'VALUES (?, ?)', (meal_id, pi['id']))
    db.commit()
    db.close()

    response = client.post(f'/delete_persistent_ingredient/{pi["id"]}',
                           follow_redirects=True)
    assert response.status_code == 200
    db = app_module.get_db()
    assert db.execute('SELECT COUNT(*) FROM persistent_ingredients WHERE id=?',
                      (pi['id'],)).fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM persistent_ingredient_meals WHERE '
                      'persistent_ingredient_id=?', (pi['id'],)).fetchone()[0] == 0
    db.close()


def test_shopping_list_back_to_results(client, sample_meal):
    db = app_module.get_db()
    db.execute("INSERT INTO votes (name) VALUES ('Back Vote')")
    db.commit()
    vote_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.execute("INSERT INTO vote_options (vote_id, meal_name) VALUES (?, ?)",
               (vote_id, 'Test Meal'))
    db.commit()
    db.close()

    response = client.post('/create_shopping_list',
                           data={'meal_ids': ['Test Meal'], 'vote_id': str(vote_id)},
                           follow_redirects=True)
    assert response.status_code == 200
    assert b'Back to Results' in response.data
    assert f'/vote/{vote_id}/results'.encode() in response.data

    # without a vote the list falls back to the votes page
    client.post('/shopping_list/1/delete', follow_redirects=True)
    db = app_module.get_db()
    for row in db.execute('SELECT id FROM shopping_list_items').fetchall():
        db.execute('DELETE FROM shopping_list_items WHERE id=?', (row['id'],))
    db.execute('DELETE FROM shopping_list_meals')
    db.commit()
    db.close()
    response = client.get('/shopping_list')
    assert b'Back to Voting' in response.data
    assert b'vote_id' not in response.data
