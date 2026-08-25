import pytest
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module
from app import app, init_db


@pytest.fixture
def client(tmp_path):
    """Test client backed by a throwaway database (never touches the real one).

    Routes call the module-level get_db() in app.py, so swapping that
    attribute redirects every DB access for the test. Use app_module.get_db()
    in test code for direct DB access.
    """
    test_db = str(tmp_path / 'shopping_app.db')
    app.config['TESTING'] = True

    original_get_db = app_module.get_db

    def _connect():
        db = sqlite3.connect(test_db)
        db.row_factory = sqlite3.Row
        return db

    app_module.get_db = _connect
    init_db()
    try:
        with app.test_client() as c:
            yield c
    finally:
        app_module.get_db = original_get_db
        if os.path.exists(test_db):
            os.remove(test_db)


@pytest.fixture
def sample_meal(client):
    """Create a meal with one regular ingredient; return its id."""
    db = app_module.get_db()
    db.execute('INSERT INTO meals (name, description) VALUES (?, ?)',
               ('Test Meal', 'a test meal'))
    meal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
    db.execute('INSERT INTO ingredients (meal_id, name, quantity, unit) VALUES (?, ?, ?, ?)',
               (meal_id, 'ingredient1', '1', ''))
    db.commit()
    db.close()
    return meal_id
