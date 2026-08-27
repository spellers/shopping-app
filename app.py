from flask import session
import os
import sqlite3
from datetime import datetime
import tesco
import datadir
import recipe_import
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g
import sys
import updates

# Frozen installs keep their templates in <install dir>/resources/templates
# (read-only, next to the executable); dev uses the project folder.
if getattr(sys, 'frozen', False):
    app = Flask(__name__, template_folder=os.path.join(datadir.resource_dir(), 'templates'))
else:
    app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or datadir.secret_key()

@app.context_processor
def inject_update_status():
    """Every page gets an 'update' dict for the new-version banner."""
    updates.ensure_check()
    return dict(update=updates.status())


@app.route('/updates/status')
def updates_status():
    """JSON endpoint: current version + latest release info."""
    return jsonify(updates.status())


@app.route('/updates/start', methods=['POST'])
def updates_start():
    """One-click update: download + install + restart, in the background."""
    if updates.start_update():
        return redirect(url_for('update_progress'))
    flash('Could not start the update — the new version may not be ready. '
          'Try again in a minute, or download it manually.', 'warning')
    return redirect(url_for('meal_tracker'))


@app.route('/updates/progress')
def update_progress():
    """Progress page for the running update (polled from JS)."""
    return render_template('update_progress.html',
                           job=updates.job_status(),
                           st=updates.status())


@app.route('/updates/progress.json')
def update_progress_json():
    """JSON poll target: {'job': ..., 'status': ...}."""
    return jsonify({'job': updates.job_status(), 'status': updates.status()})


@app.route('/updates/download')
def updates_download():
    """Fallback: download the installer manually."""
    st = updates.status()
    if st['download_url']:
        return redirect(st['download_url'])
    flash('No update available right now — try again later.', 'warning')
    return redirect(url_for('meal_tracker'))


@app.route('/updates/dismiss', methods=['POST'])
def updates_dismiss():
    """Hide the update banner for a week."""
    updates.dismiss(request.form.get('tag') or updates.status().get('latest_version'))
    return redirect(request.referrer or url_for('meal_tracker'))


def get_db():
    db = sqlite3.connect(datadir.db_path(), timeout=10)
    db.row_factory = sqlite3.Row
    # Remember the connection so teardown_appcontext can close it if a
    # request errors out before the route gets a chance to. (Startup calls
    # like init_db() run outside a request context, where g is unbound.)
    try:
        if not hasattr(g, 'db'):
            g.db = db
    except RuntimeError:
        pass
    return db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_id INTEGER,
            name TEXT NOT NULL,
            quantity TEXT,
            unit TEXT,
            FOREIGN KEY (meal_id) REFERENCES meals(id)
        );
        CREATE TABLE IF NOT EXISTS persistent_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT
        );
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS vote_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vote_id INTEGER,
            meal_name TEXT NOT NULL,
            FOREIGN KEY (vote_id) REFERENCES votes(id)
        );
        CREATE TABLE IF NOT EXISTS vote_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vote_id INTEGER,
            voter TEXT,
            meal_name TEXT,
            FOREIGN KEY (vote_id) REFERENCES votes(id)
        );

        CREATE TABLE IF NOT EXISTS persistent_ingredient_meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_id INTEGER NOT NULL,
            persistent_ingredient_id INTEGER NOT NULL,
            quantity TEXT,
            FOREIGN KEY (meal_id) REFERENCES meals(id),
            FOREIGN KEY (persistent_ingredient_id) REFERENCES persistent_ingredients(id)
        );
        CREATE TABLE IF NOT EXISTS shopping_list_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity TEXT,
            checked INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS shopping_list_meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shopping_list_id INTEGER NOT NULL,
            meal_id INTEGER NOT NULL,
            FOREIGN KEY (meal_id) REFERENCES meals(id)
        );
        CREATE TABLE IF NOT EXISTS meal_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            FOREIGN KEY (meal_id) REFERENCES meals(id)
        );
        CREATE TABLE IF NOT EXISTS tesco_products (
            sku TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            brand TEXT,
            price REAL,
            unit_price REAL,
            unit_of_measure TEXT,
            image_url TEXT,
            matched_term TEXT,
            created_at TEXT
        );
    """)
        db.commit()
    except sqlite3.OperationalError as e:
        db.rollback()
    _migrate(db)
    _seed(db)
    db.close()


def _seed(db):
    """First-run starter content: a handful of simple meals (4-5 ingredients
    each) plus shared pantry staples. Only runs on an empty database —
    existing users (or anyone who deleted the seeds) are left alone."""
    if db.execute('SELECT COUNT(*) FROM meals').fetchone()[0]:
        return

    # Shared pantry staples, linked to the meals that use them.
    pantry = {
        'Rice': 1,          # shared: one bag covers all meals
        'Soy Sauce': 1,
        'Butter': 1,
        'Cheddar Cheese': 1,
        'Pasta': 1,
    }
    pi_ids = {}
    for name, shareable in pantry.items():
        db.execute(
            'INSERT INTO persistent_ingredients (name, category, shareable) VALUES (?, ?, ?)',
            (name, 'Pantry', shareable)
        )
        pi_ids[name] = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    # name -> [ (ingredient name, quantity) ... ]  plus 'persistent' links.
    meals = [
        ('Chicken Fried Rice', 'Sizzling wok classic with egg and spring onions.',
         [('Chicken Breast', '250g'), ('Eggs', '3'), ('Spring Onions', '2')],
         ['Rice']),
        ('Thai Red Curry', 'Chicken curry in coconut milk with red curry paste.',
         [('Chicken Breast', '300g'), ('Red Curry Paste', '2 tbsp'), ('Coconut Milk', '400ml')],
         ['Rice']),
        ('Tuna Melt Toastie', 'Tuna and melted cheese on buttered bread.',
         [('Tuna in Brine', '2 cans'), ('White Bread', '4 slices'), ('Lemon', '1')],
         ['Cheddar Cheese', 'Butter']),
        ('Jacket Potatoes with Beans and Cheese', 'Big roast potatoes topped with butter, beans and cheese.',
         [('Potatoes', '4'), ('Baked Beans', '1 tin')],
         ['Butter', 'Cheddar Cheese']),
        ('Pasta Bolognese', 'Classic spag bol with beef and tomatoes.',
         [('Beef Mince', '400g'), ('Tomatoes Chopped', '1 tin'), ('Onions', '1'), ('Garlic', '2 cloves')],
         ['Pasta']),
        ('Egg Fried Rice', 'Leftover rice tossed with egg, soy sauce and spring onions.',
         [('Eggs', '3'), ('Spring Onions', '2'), ('Sesame Oil', '1 tsp')],
         ['Rice', 'Soy Sauce']),
    ]

    for meal_name, description, ingredients, persistent in meals:
        db.execute('INSERT INTO meals (name, description) VALUES (?, ?)', (meal_name, description))
        meal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.execute('INSERT INTO meal_categories (meal_id, category) VALUES (?, ?)', (meal_id, 'Demo'))
        for ing_name, quantity in ingredients:
            db.execute(
                'INSERT INTO ingredients (meal_id, name, quantity) VALUES (?, ?, ?)',
                (meal_id, ing_name, quantity)
            )
        for pi_name in persistent:
            db.execute(
                'INSERT INTO persistent_ingredient_meals (meal_id, persistent_ingredient_id) '
                'VALUES (?, ?)',
                (meal_id, pi_ids[pi_name])
            )
    db.commit()


NON_SHARED_HINTS = (
    'chicken', 'beef', 'mince', 'pork', 'lamb', 'mutton', 'bacon', 'sausage',
    'fish', 'prawn', 'shrimp', 'salmon', 'cod', 'egg', 'cheese', 'turkey',
    'steak', 'fillet', 'ham', 'game',
)

# The starter meals seeded on first run; tagged with a 'Demo' category so the
# category feature is visible out of the box (see _seed / _migrate).
DEMO_MEAL_NAMES = (
    'Chicken Fried Rice',
    'Thai Red Curry',
    'Tuna Melt Toastie',
    'Jacket Potatoes with Beans and Cheese',
    'Pasta Bolognese',
    'Egg Fried Rice',
)


def _migrate(db):
    """Add columns created after older DB versions exist."""
    wanted_cols = [
        ('ingredients', 'tesco_sku'),
        ('persistent_ingredients', 'tesco_sku'),
        ('shopping_list_items', 'tesco_sku'),
    ]
    for table, col in wanted_cols:
        existing = {row[1] for row in db.execute('PRAGMA table_info(' + table + ')').fetchall()}
        if col not in existing:
            db.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + col + ' TEXT')
    # shareable: 1 = one unit covers every meal that uses it (rice, pasta...);
    # 0 = one unit per meal (chicken, mince...).
    added_shareable = []
    for table in ('ingredients', 'persistent_ingredients'):
        existing = {row[1] for row in db.execute('PRAGMA table_info(' + table + ')').fetchall()}
        if 'shareable' not in existing:
            db.execute('ALTER TABLE ' + table + ' ADD COLUMN shareable INTEGER DEFAULT 1')
            added_shareable.append(table)
    if added_shareable:
        # One-off backfill: per-meal goods (meats, eggs, cheese) default to
        # not shareable; everything else to shareable. User can override in the UI.
        for table in added_shareable:
            for row in db.execute('SELECT id, name FROM ' + table).fetchall():
                if any(h in (row['name'] or '').lower() for h in NON_SHARED_HINTS):
                    db.execute('UPDATE ' + table + ' SET shareable=0 WHERE id=?', (row['id'],))
    # One-off: tag the starter (demo) meals with a 'Demo' category so the
    # category feature is visible on existing installs. Idempotent — only
    # adds where the meal doesn't already carry a 'Demo' category.
    # Case-insensitive match so renamed/retyped demo meals are still tagged.
    for name in DEMO_MEAL_NAMES:
        row = db.execute('SELECT id FROM meals WHERE name=? COLLATE NOCASE', (name,)).fetchone()
        if not row:
            continue
        has = db.execute(
            'SELECT 1 FROM meal_categories WHERE meal_id=? AND category=?',
            (row['id'], 'Demo')).fetchone()
        if not has:
            db.execute('INSERT INTO meal_categories (meal_id, category) VALUES (?, ?)',
                       (row['id'], 'Demo'))
    db.commit()


def match_ingredient_tesco(name):
    """Match an ingredient name to a Tesco product.

    Checks the local cache (tesco_products) first, then falls back to a live
    catalogue search, keeping the top result. Returns (product_or_None,
    results_list) so a UI layer can offer alternatives.
    """
    db = get_db()
    row = db.execute('SELECT * FROM tesco_products WHERE matched_term=?', (name,)).fetchone()
    if row:
        db.close()
        return dict(row), [dict(row)]
    try:
        results = tesco.search(name, limit=5)
    except tesco.TescoError:
        db.close()
        return None, []
    if not results:
        db.close()
        return None, []
    best = results[0]
    _cache_product(db, best, matched_term=name)
    db.commit()
    db.close()
    return best, results


def _cache_product(db, product, matched_term=None):
    """Store a product in the local tesco_products cache (by SKU).

    The shopping list page resolves product titles/prices from this cache,
    so every matching path MUST write through here.
    """
    db.execute(
        'INSERT OR REPLACE INTO tesco_products (sku, title, brand, price, unit_price, '
        'unit_of_measure, image_url, matched_term, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (str(product.get('sku') or '').strip(), product.get('title') or '',
         product.get('brand') or '', product.get('price'), product.get('unit_price'),
         product.get('unit_of_measure') or '', product.get('image_url') or '',
         matched_term, datetime.now().strftime('%Y-%m-%d %H:%M'))
    )


def _refresh_product_cache(sku, name_hint=None):
    """Fill a cache row for a known-but-uncached SKU via a live lookup.

    Returns True if a row was added, False if the lookup failed.
    """
    if not sku:
        return False
    db = get_db()
    existing = db.execute('SELECT sku FROM tesco_products WHERE sku=?', (sku,)).fetchone()
    if existing:
        db.close()
        return False
    try:
        product = tesco.get_product(sku)
    except tesco.TescoError:
        db.close()
        return False
    _cache_product(db, product, matched_term=name_hint or product.get('title'))
    db.commit()
    db.close()
    return True


@app.route('/')
def index():
    return redirect('/meal_tracker')

@app.route('/help')
def help_page():
    return render_template('help.html', version=updates.VERSION)


@app.route('/meal_tracker/<int:meal_id>/add_persistent', methods=['POST'])
def add_persistent_to_meal(meal_id):
    db = get_db()
    meal = db.execute('SELECT * FROM meals WHERE id=?', (meal_id,)).fetchone()
    if not meal:
        db.close()
        return 'Meal not found', 404
    persistent_id = request.form.get('persistent_id')
    quantity = request.form.get('quantity', '').strip()
    if persistent_id:
        db.execute('INSERT INTO persistent_ingredient_meals (meal_id, persistent_ingredient_id, quantity) VALUES (?, ?, ?)',
                   (meal_id, int(persistent_id), quantity))
        db.commit()
        db.close()
        flash('Ingredient added!', 'success')
        return redirect(url_for('meal_detail', meal_id=meal_id))
    db.close()
    return redirect(url_for('meal_detail', meal_id=meal_id))

@app.route('/meal_tracker/<int:meal_id>/remove_persistent/<int:link_id>', methods=['POST'])
def remove_persistent_from_meal(meal_id, link_id):
    db = get_db()
    db.execute('DELETE FROM persistent_ingredient_meals WHERE id=? AND meal_id=?', (link_id, meal_id))
    db.commit()
    db.close()
    flash('Ingredient removed!', 'success')
    return redirect(url_for('meal_detail', meal_id=meal_id))

@app.route('/meal_tracker')
def meal_tracker():
    db = get_db()
    meals = [dict(m) for m in db.execute('SELECT * FROM meals ORDER BY id DESC').fetchall()]
    for meal in meals:
        meal['categories'] = _meal_categories(db, meal['id'])

    category = (request.args.get('category') or '').strip()
    all_categories = [r['category'] for r in db.execute(
        'SELECT DISTINCT category FROM meal_categories ORDER BY category').fetchall()]
    if category:
        meals = [m for m in meals if category in m['categories']]
    db.close()
    return render_template('meal_tracker.html', meals=meals,
                           categories=all_categories, active_category=category)

@app.route('/meal_tracker/<int:meal_id>')
def meal_detail(meal_id):
    db = get_db()
    meal = db.execute('SELECT * FROM meals WHERE id=?', (meal_id,)).fetchone()
    if not meal:
        db.close()
        return 'Meal not found', 404
    ingredients = db.execute(
        'SELECT * FROM ingredients WHERE meal_id=? ORDER BY id', (meal_id,)
    ).fetchall()

    # Fetch persistent ingredients linked to this meal
    persistent_links = db.execute('''
        SELECT pim.id, pim.meal_id, pim.persistent_ingredient_id, pim.quantity,
               pi.name as ingredient_name, pi.category, pi.tesco_sku, pi.shareable
        FROM persistent_ingredient_meals pim
        JOIN persistent_ingredients pi ON pim.persistent_ingredient_id = pi.id
        WHERE pim.meal_id = ?
        ORDER BY pim.id
    ''', (meal_id,)).fetchall()

    # Fetch all persistent ingredients for the dropdown
    all_persistent = db.execute('SELECT id, name, category FROM persistent_ingredients ORDER BY name').fetchall()

    db.close()
    return render_template('meal_detail.html', meal=meal, ingredients=ingredients, persistent_links=persistent_links, all_persistent=all_persistent)

def _parse_categories(raw):
    """Split a comma-separated category string into clean, unique values."""
    cats = []
    for part in (raw or '').split(','):
        c = part.strip()
        if c and c not in cats:
            cats.append(c)
    return cats


def _set_meal_categories(db, meal_id, categories):
    """Replace a meal's category set (join table)."""
    db.execute('DELETE FROM meal_categories WHERE meal_id=?', (meal_id,))
    for c in categories:
        db.execute('INSERT INTO meal_categories (meal_id, category) VALUES (?, ?)', (meal_id, c))


def _meal_categories(db, meal_id):
    return [r['category'] for r in db.execute(
        'SELECT category FROM meal_categories WHERE meal_id=? ORDER BY category',
        (meal_id,)).fetchall()]


@app.route('/add_meal', methods=['GET', 'POST'])
def add_meal():
    if request.method == 'POST':
        name = request.form['name'].strip()
        description = request.form.get('description', '').strip()
        if name:
            db = get_db()
            db.execute('INSERT INTO meals (name, description) VALUES (?, ?)', (name, description))
            meal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            _set_meal_categories(db, meal_id, _parse_categories(request.form.get('categories')))
            db.commit()
            db.close()
            flash('Meal added!', 'success')
            return redirect('/meal_tracker')
    return render_template('add_meal.html')

@app.route('/edit_meal/<int:meal_id>', methods=['GET', 'POST'])
def edit_meal(meal_id):
    db = get_db()
    meal = db.execute('SELECT * FROM meals WHERE id=?', (meal_id,)).fetchone()
    if not meal:
        db.close()
        return 'Not found', 404
    if request.method == 'POST':
        db.execute('UPDATE meals SET name=?, description=? WHERE id=?',
                   (request.form['name'].strip(), request.form.get('description', '').strip(), meal_id))
        _set_meal_categories(db, meal_id, _parse_categories(request.form.get('categories')))
        db.commit()
        db.close()
        flash('Meal updated!', 'success')
        return redirect(url_for('meal_detail', meal_id=meal_id))
    categories = _meal_categories(db, meal_id)
    db.close()
    return render_template('edit_meal.html', meal=meal, categories=', '.join(categories))

@app.route('/delete_meal/<int:meal_id>', methods=['POST'])
def delete_meal(meal_id):
    db = get_db()
    db.execute('DELETE FROM ingredients WHERE meal_id=?', (meal_id,))
    db.execute('DELETE FROM meal_categories WHERE meal_id=?', (meal_id,))
    db.execute('DELETE FROM meals WHERE id=?', (meal_id,))
    db.commit()
    db.close()
    flash('Meal deleted!', 'success')
    return redirect('/meal_tracker')

@app.route('/import_meal', methods=['POST'])
def import_meal():
    """One-click recipe import: fetch a recipe page, create the meal, and
    link its ingredients - reusing persistent ingredients by name and adding
    any new ones to the persistent list."""
    url = request.form.get('url', '').strip()
    try:
        recipe = recipe_import.fetch_recipe(url)
    except recipe_import.RecipeError as e:
        flash(str(e), 'danger')
        return redirect(url_for('meal_tracker'))

    db = get_db()
    db.execute('INSERT INTO meals (name, description) VALUES (?, ?)',
               (recipe['name'], recipe['description'][:500] if recipe['description'] else None))
    meal_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    existing = {r['name'].strip().lower(): r['id']
                for r in db.execute('SELECT id, name FROM persistent_ingredients').fetchall()}

    new_count = 0
    for raw in recipe['ingredients']:
        quantity, name = recipe_import.split_ingredient(raw)
        if not name:
            continue
        key = name.strip().lower()
        if key in existing:
            pi_id = existing[key]
        else:
            shareable = 0 if any(h in key for h in NON_SHARED_HINTS) else 1
            db.execute('INSERT INTO persistent_ingredients (name, category, shareable) VALUES (?, ?, ?)',
                       (name, 'Imported', shareable))
            pi_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            existing[key] = pi_id
            new_count += 1
        db.execute('INSERT INTO persistent_ingredient_meals (meal_id, persistent_ingredient_id, quantity) '
                   'VALUES (?, ?, ?)', (meal_id, pi_id, quantity))
    db.commit()
    db.close()

    total = len(recipe['ingredients'])
    flash(f"Added “{recipe['name']}” with {total} ingredients"
          + (f" ({new_count} new)." if new_count else "."), 'success')
    return redirect(url_for('meal_detail', meal_id=meal_id))

@app.route('/add_ingredient/<int:meal_id>', methods=['GET', 'POST'])
def add_ingredient(meal_id):
    if request.method == 'POST':
        name = request.form['name'].strip()
        quantity = request.form.get('quantity', '').strip()
        unit = request.form.get('unit', '').strip()
        shareable = 1 if request.form.get('shareable') else 0
        if name:
            db = get_db()
            db.execute('INSERT INTO ingredients (meal_id, name, quantity, unit, shareable) VALUES (?, ?, ?, ?, ?)',
                       (meal_id, name, quantity, unit, shareable))
            db.commit()
            db.close()
            flash('Ingredient added!', 'success')
            return redirect(url_for('meal_detail', meal_id=meal_id))
    return render_template('add_ingredient.html', meal_id=meal_id)

@app.route('/toggle_shareable/<int:ingredient_id>/<kind>', methods=['POST'])
def toggle_shareable(ingredient_id, kind):
    """Flip shareable: 1 = one unit covers all meals; 0 = one unit per meal."""
    table = 'ingredients' if kind == 'ing' else 'persistent_ingredients'
    if kind not in ('ing', 'persist'):
        return 'Unknown ingredient kind', 404
    db = get_db()
    db.execute('UPDATE ' + table + ' SET shareable=1-COALESCE(shareable,1) WHERE id=?', (ingredient_id,))
    db.commit()
    db.close()
    flash('Updated.', 'success')
    return redirect(request.referrer or url_for('meal_tracker'))

@app.route('/delete_ingredient/<int:ingredient_id>', methods=['POST'])
def delete_ingredient(ingredient_id):
    db = get_db()
    db.execute('DELETE FROM ingredients WHERE id=?', (ingredient_id,))
    db.commit()
    db.close()
    flash('Ingredient deleted!', 'success')
    return redirect('/meal_tracker')

@app.route('/delete_persistent_ingredient/<int:ingredient_id>', methods=['POST'])
def delete_persistent_ingredient(ingredient_id):
    db = get_db()
    db.execute('DELETE FROM persistent_ingredient_meals WHERE persistent_ingredient_id=?', (ingredient_id,))
    db.execute('DELETE FROM persistent_ingredients WHERE id=?', (ingredient_id,))
    db.commit()
    db.close()
    flash('Ingredient deleted!', 'success')
    return redirect('/persistent_ingredients')

@app.route('/rename_persistent_ingredient/<int:ingredient_id>', methods=['POST'])
def rename_persistent_ingredient(ingredient_id):
    """Rename a persistent ingredient (tidying up imported names etc.)."""
    new_name = (request.form.get('name') or '').strip()
    if not new_name:
        flash('Name cannot be empty.', 'warning')
        return redirect('/persistent_ingredients')
    db = get_db()
    db.execute('UPDATE persistent_ingredients SET name=? WHERE id=?', (new_name, ingredient_id))
    db.commit()
    db.close()
    flash('Ingredient renamed.', 'success')
    return redirect('/persistent_ingredients')

@app.route('/persistent_ingredients', methods=['GET', 'POST'])
def persistent_ingredients():
    if request.method == 'POST':
        name = request.form['name'].strip()
        category = request.form.get('category', '').strip()
        shareable = 1 if request.form.get('shareable') else 0
        db = get_db()
        db.execute('INSERT INTO persistent_ingredients (name, category, shareable) VALUES (?, ?, ?)',
                   (name, category, shareable))
        db.commit()
        db.close()
        flash('Ingredient added!', 'success')
        return redirect('/persistent_ingredients')
    db = get_db()
    category = (request.args.get('category') or '').strip()
    if category:
        ingredients = db.execute('SELECT * FROM persistent_ingredients WHERE category=? ORDER BY id DESC',
                                 (category,)).fetchall()
    else:
        ingredients = db.execute('SELECT * FROM persistent_ingredients ORDER BY id DESC').fetchall()
    categories = [r['category'] for r in db.execute(
        'SELECT DISTINCT category FROM persistent_ingredients WHERE category IS NOT NULL AND category != "" '
        'ORDER BY category').fetchall()]
    db.close()
    return render_template('persistent_ingredients.html', ingredients=ingredients,
                           categories=categories, active_category=category)


def _sku_conflict(db, sku, ingredient_id, table):
    """Return the row of a *different* ingredient in `table` that already uses `sku`."""
    return db.execute(
        'SELECT * FROM ' + table + ' WHERE tesco_sku=? AND id != ? LIMIT 1',
        (sku, ingredient_id)).fetchone()


@app.route('/merge_confirm/<int:keep_id>/<int:drop_id>')
def merge_confirm(keep_id, drop_id):
    """Confirmation page: ask whether to merge two ingredients that share a Tesco SKU."""
    db = get_db()
    keep = db.execute('SELECT * FROM persistent_ingredients WHERE id=?', (keep_id,)).fetchone()
    drop = db.execute('SELECT * FROM persistent_ingredients WHERE id=?', (drop_id,)).fetchone()
    db.close()
    if not keep or not drop:
        flash('Ingredient not found.', 'warning')
        return redirect(url_for('persistent_ingredients'))
    db = get_db()
    keep_links = db.execute('SELECT COUNT(*) FROM persistent_ingredient_meals WHERE persistent_ingredient_id=?',
                            (keep_id,)).fetchone()[0]
    drop_links = db.execute('SELECT COUNT(*) FROM persistent_ingredient_meals WHERE persistent_ingredient_id=?',
                            (drop_id,)).fetchone()[0]
    db.close()
    return render_template('merge_confirm.html', keep=keep, drop=drop,
                           keep_links=keep_links, drop_links=drop_links)


@app.route('/merge_persistent_ingredient/<int:keep_id>/<int:drop_id>', methods=['POST'])
def merge_persistent_ingredient(keep_id, drop_id):
    """Merge one persistent ingredient into another: meal links move to the
    kept ingredient, the kept one takes the SKU, and the merged one is removed."""
    db = get_db()
    keep = db.execute('SELECT * FROM persistent_ingredients WHERE id=?', (keep_id,)).fetchone()
    drop = db.execute('SELECT * FROM persistent_ingredients WHERE id=?', (drop_id,)).fetchone()
    if not keep or not drop:
        db.close()
        flash('Ingredient not found.', 'warning')
        return redirect('/persistent_ingredients')
    if not keep['tesco_sku'] and drop['tesco_sku']:
        db.execute('UPDATE persistent_ingredients SET tesco_sku=? WHERE id=?', (drop['tesco_sku'], keep_id))
    # Move each meal link of the dropped ingredient to the kept one (no duplicates).
    for link in db.execute('SELECT * FROM persistent_ingredient_meals WHERE persistent_ingredient_id=?', (drop_id,)).fetchall():
        existing = db.execute('SELECT id FROM persistent_ingredient_meals WHERE meal_id=? AND persistent_ingredient_id=?',
                              (link['meal_id'], keep_id)).fetchone()
        if not existing:
            db.execute('INSERT INTO persistent_ingredient_meals (meal_id, persistent_ingredient_id, quantity) '
                       'SELECT meal_id, ?, quantity FROM persistent_ingredient_meals WHERE id=?',
                       (keep_id, link['id']))
    db.execute('DELETE FROM persistent_ingredient_meals WHERE persistent_ingredient_id=?', (drop_id,))
    db.execute('DELETE FROM persistent_ingredients WHERE id=?', (drop_id,))
    db.commit()
    db.close()
    flash(f'Merged into "{keep["name"]}".', 'success')
    return redirect('/persistent_ingredients')

@app.route('/votes', methods=['GET', 'POST'])
def votes():
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description', '').strip()
        if title:
            db = get_db()
            from datetime import datetime
            db.execute('INSERT INTO votes (name, description, created_at) VALUES (?, ?, ?)',
                       (title, description, datetime.now().strftime('%Y-%m-%d %H:%M')))
            vote_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            meal_ids = request.form.getlist('meal_ids')
            for meal_id in meal_ids:
                row = db.execute('SELECT name FROM meals WHERE id=?', (int(meal_id),)).fetchone()
                if row:
                    db.execute('INSERT INTO vote_options (vote_id, meal_name) VALUES (?, ?)', (vote_id, row['name']))
            db.commit()
            db.close()
            flash('Vote created — link copied to your clipboard.', 'success')
            return redirect(f'/votes?created={vote_id}')
    db = get_db()
    meals = db.execute('SELECT * FROM meals ORDER BY name').fetchall()
    votes_list = db.execute('SELECT * FROM votes ORDER BY id DESC').fetchall()
    db.close()
    created_id = request.args.get('created', type=int)
    return render_template('votes.html', votes_list=votes_list, meals=meals, created_id=created_id)

@app.route('/vote/<int:vote_id>/delete', methods=['POST'])
def delete_vote(vote_id):
    db = get_db()
    vote = db.execute('SELECT name FROM votes WHERE id=?', (vote_id,)).fetchone()
    if vote:
        db.execute('DELETE FROM vote_votes WHERE vote_id=?', (vote_id,))
        db.execute('DELETE FROM vote_options WHERE vote_id=?', (vote_id,))
        db.execute('DELETE FROM votes WHERE id=?', (vote_id,))
        db.commit()
        flash(f'Vote "{vote["name"]}" deleted.', 'success')
    db.close()
    return redirect('/votes')

@app.route('/vote/<int:vote_id>')
def vote_detail(vote_id):
    db = get_db()
    vote = db.execute('SELECT * FROM votes WHERE id=?', (vote_id,)).fetchone()
    if not vote:
        db.close()
        return 'Vote not found', 404
    options = db.execute('SELECT id, meal_name FROM vote_options WHERE vote_id=?', (vote_id,)).fetchall()
    db.close()
    return render_template('vote_detail.html', vote=vote, options=options)
@app.route('/vote/<int:vote_id>/cast', methods=['POST'])
def cast_vote(vote_id):
    db = get_db()
    option_ids = request.form.getlist('option_ids')
    if len(option_ids) > 3:
        option_ids = option_ids[:3]
    if option_ids:
        for opt_id in option_ids:
            meal_name = db.execute('SELECT meal_name FROM vote_options WHERE id=?', (int(opt_id),)).fetchone()['meal_name']
            db.execute('INSERT INTO vote_votes (vote_id, voter, meal_name) VALUES (?, ?, ?)',
                      (vote_id, session.get('voter', 'Anonymous'), meal_name))
        db.commit()
    flash(f'Vote cast for {len(option_ids)} option(s)!', 'success')
    db.close()
    return redirect(url_for('vote_results', vote_id=vote_id))
@app.route('/vote/<int:vote_id>/results')
def vote_results(vote_id):
    db = get_db()
    vote = db.execute('SELECT * FROM votes WHERE id=?', (vote_id,)).fetchone()
    if not vote:
        db.close()
        return 'Vote not found', 404

    options = db.execute('SELECT vo.id, vo.meal_name FROM vote_options vo WHERE vo.vote_id=? ORDER BY vo.id', (vote_id,)).fetchall()

    vote_counts = {}
    total = 0
    if options:
        meal_names = [o['meal_name'] for o in options]
        placeholders = ','.join(['?'] * len(meal_names))
        sql = "SELECT meal_name, COUNT(*) as cnt FROM vote_votes WHERE vote_id=? AND meal_name IN (" + placeholders + ") GROUP BY meal_name"
        rows = db.execute(sql, [vote_id] + meal_names).fetchall()
        for row in rows:
            vote_counts[row['meal_name']] = row['cnt']
            total += row['cnt']

    # Convert sqlite3.Row objects to dicts so we can attach vote_count
    results = []
    for opt in options:
        results.append({
            'id': opt['id'],
            'meal_name': opt['meal_name'],
            'vote_count': vote_counts.get(opt['meal_name'], 0)
        })
    # Sort by vote count descending (most voted first)
    results.sort(key=lambda x: x['vote_count'], reverse=True)

    db.close()
    return render_template('vote_results.html', vote=vote, options=results, total_votes=total)

@app.route('/shopping_list/<int:item_id>/toggle', methods=['POST'])
def toggle_shopping(item_id):
    db = get_db()
    item = db.execute('SELECT checked FROM shopping_list_items WHERE id=?', (item_id,)).fetchone()
    if item:
        db.execute('UPDATE shopping_list_items SET checked=? WHERE id=?', (1 - item['checked'], item_id))
        db.commit()
    db.close()
    flash('Item updated!', 'success')
    return redirect(url_for('shopping_list_get'))


@app.route('/create_shopping_list', methods=['POST'])
def create_shopping_list():
    '''Create shopping list from selected meals'''
    db = get_db()
    vote_id = request.form.get('vote_id', '')
    meal_names = request.form.getlist('meal_ids')
    
    if not meal_names:
        flash('No meals selected', 'warning')
        if vote_id:
            return redirect(url_for('vote_results', vote_id=int(vote_id)))
        return redirect(url_for('votes'))
    
    # Look up meal IDs by name
    meal_ids = []
    for name in meal_names:
        meal = db.execute('SELECT id FROM meals WHERE name=?', (name.strip(),)).fetchone()
        if meal:
            meal_ids.append(meal['id'])
    
    if not meal_ids:
        flash('Selected meals not found', 'warning')
        return redirect(url_for('vote_results', vote_id=int(vote_id)) if vote_id else url_for('votes'))
    
    # Aggregate ingredients from selected meals
    agg = {}  # {name: {'quantity': '', 'unit': '', 'meals': set, 'shareable': bool, 'sku': ''}}

    def _add_agg(name, quantity, unit, sku, shareable, meal_id, meal_name):
        if name in agg:
            if sku and not agg[name]['sku']:
                agg[name]['sku'] = sku
            agg[name]['meals'].add(meal_id)
        else:
            agg[name] = {
                'quantity': quantity or '',
                'unit': unit or '',
                'meals': {meal_id},
                'shareable': bool(shareable),
                'sku': sku or '',
                'meal_name': meal_name
            }

    for meal_id in meal_ids:
        meal_name = db.execute(
            'SELECT name FROM meals WHERE id=?', (meal_id,)
        ).fetchone()['name']
        # Get regular ingredients
        rows = db.execute(
            'SELECT name, quantity, tesco_sku, shareable FROM ingredients WHERE meal_id=?',
            (meal_id,)
        ).fetchall()
        for row in rows:
            _add_agg(
                row['name'].strip().lower(), row['quantity'], '',
                row['tesco_sku'], row['shareable'], meal_id, meal_name
            )
        
        # Get persistent ingredient meals
        pim_rows = db.execute(
            '''SELECT pi.name, pi.category, pim.quantity, pi.tesco_sku, pi.shareable
               FROM persistent_ingredient_meals pim
               JOIN persistent_ingredients pi ON pim.persistent_ingredient_id = pi.id
               WHERE pim.meal_id=?''',
            (meal_id,)
        ).fetchall()
        for row in pim_rows:
            _add_agg(
                row['name'].strip().lower(), row['quantity'], row['category'],
                row['tesco_sku'], row['shareable'], meal_id, meal_name
            )
    
    # Clear existing shopping list and insert aggregated items
    db.execute('DELETE FROM shopping_list_items')
    db.execute('DELETE FROM shopping_list_meals')
    for meal_id in meal_ids:
        db.execute('INSERT INTO shopping_list_meals (shopping_list_id, meal_id) VALUES (?, ?)', (1, meal_id))
    # Fall back to a same-named persistent ingredient's Tesco SKU when the
    # regular ingredient rows weren't matched individually
    for name, data in agg.items():
        if not data['sku']:
            row = db.execute(
                'SELECT tesco_sku FROM persistent_ingredients '
                'WHERE lower(name)=? AND tesco_sku IS NOT NULL AND tesco_sku != "" '
                'ORDER BY id LIMIT 1',
                (name,)
            ).fetchone()
            if row and row['tesco_sku']:
                data['sku'] = row['tesco_sku']

    for name, data in agg.items():
        n_meals = len(data['meals'])
        if data['shareable']:
            # Shared goods (rice, pasta...): one unit covers all selected meals
            quantity = ''
        elif n_meals > 1:
            # Per-meal goods (meat, eggs...): one unit for every meal that uses it
            quantity = 'x' + str(n_meals) if not data['quantity'] else 'x' + str(n_meals) + ' ' + data['quantity']
        else:
            quantity = data['quantity']
        db.execute(
            'INSERT INTO shopping_list_items (name, quantity, checked, tesco_sku) VALUES (?, ?, 0, ?)',
            (name.title() if name else '', quantity, data.get('sku') or '')
        )
    
    db.commit()
    db.close()
    flash(f'Shopping list created with {len(agg)} items!', 'success')
    if vote_id:
        return redirect(url_for('shopping_list_get', vote_id=vote_id))
    return redirect(url_for('shopping_list_get'))
@app.route('/shopping_list/<int:item_id>/delete', methods=['POST'])
def delete_shopping(item_id):
    db = get_db()
    db.execute('DELETE FROM shopping_list_items WHERE id=?', (item_id,))
    db.commit()
    db.close()
    flash('Item deleted!', 'success')
    return redirect(url_for('shopping_list_get'))

@app.route('/shopping_list', methods=['GET'])
def shopping_list_get():
    db = get_db()
    items = [dict(r) for r in db.execute('SELECT * FROM shopping_list_items ORDER BY name').fetchall()]
    meals = db.execute(
        'SELECT m.* FROM meals m JOIN shopping_list_meals s ON s.meal_id = m.id ORDER BY m.id'
    ).fetchall()
    products = {
        r['sku']: dict(r) for r in db.execute('SELECT * FROM tesco_products WHERE sku != ""').fetchall()
    }
    db.close()
    for item in items:
        item['tesco'] = products.get(item['tesco_sku'])
        if item['tesco'] is None and item['tesco_sku']:
            # Has a SKU but no cache row (matched before cache writes existed) -
            # fill it with a live lookup so the list stops showing "Not connected".
            if _refresh_product_cache(item['tesco_sku'], name_hint=item['name']):
                db = get_db()
                row = db.execute(
                    'SELECT * FROM tesco_products WHERE sku=?', (item['tesco_sku'],)
                ).fetchone()
                db.close()
                if row:
                    item['tesco'] = dict(row)
    signed_in = tesco.auth_status()['signed_in']
    vote_id = request.args.get('vote_id', '')
    return render_template('shopping_list.html', items=items, meals=meals, vote_id=vote_id, signed_in=signed_in)

@app.route('/tesco')
def tesco_status_page():
    status = tesco.auth_status()
    login = tesco.login_status()
    db = get_db()
    cached = db.execute('SELECT COUNT(*) AS n FROM tesco_products').fetchone()['n']
    db.close()
    return render_template('tesco_status.html', signed_in=status['signed_in'],
                           login=login, cached=cached,
                           chrome_found=bool(datadir.find_chrome()))


@app.route('/tesco/login', methods=['POST'])
def tesco_login():
    if tesco.login():
        flash('Sign-in started - complete the Tesco login in the Chrome window that opened.', 'success')
    else:
        flash('Sign-in is already in progress - check its status below.', 'warning')
    return redirect(url_for('tesco_status_page'))


@app.route('/tesco/login_status')
def tesco_login_status():
    return (tesco.login_status(), tesco.auth_status())


@app.route('/tesco/suggest/<int:ingredient_id>/<kind>')
def tesco_suggest(ingredient_id, kind):
    """Return the match-picker modal (HTML fragment) with up to 5 live results."""
    db = get_db()
    if kind == 'ing':
        ing = db.execute('SELECT * FROM ingredients WHERE id=?', (ingredient_id,)).fetchone()
    elif kind == 'persist':
        ing = db.execute('SELECT * FROM persistent_ingredients WHERE id=?', (ingredient_id,)).fetchone()
    else:
        db.close()
        return 'Unknown ingredient kind', 404
    db.close()
    if not ing:
        return 'Ingredient not found', 404
    error = None
    try:
        results = tesco.search(ing['name'], limit=5)
    except tesco.TescoError as exc:
        results, error = [], str(exc)
    return render_template(
        'tesco_match_modal.html', name=ing['name'], results=results,
        error=error, ingredient_id=ingredient_id, kind=kind,
    )


@app.route('/tesco/select/<int:ingredient_id>/<kind>', methods=['POST'])
def tesco_select_product(ingredient_id, kind):
    """Store the user-chosen Tesco product for an ingredient."""
    sku = (request.form.get('sku') or '').strip()
    title = (request.form.get('title') or '').strip()
    if not sku:
        return 'No product selected', 400
    db = get_db()
    # Cache the picked product so the shopping list can show title/price.
    _cache_product(db, {
        'sku': sku, 'title': title,
        'brand': (request.form.get('brand') or '').strip(),
        'price': _form_float('price'), 'unit_price': _form_float('unit_price'),
        'unit_of_measure': (request.form.get('unit_of_measure') or '').strip(),
        'image_url': (request.form.get('image_url') or '').strip(),
    }, matched_term=(request.form.get('name') or '').strip() or None)
    if kind == 'ing':
        row = db.execute('SELECT * FROM ingredients WHERE id=?', (ingredient_id,)).fetchone()
        if not row:
            db.close()
            return 'Ingredient not found', 404
        db.execute('UPDATE ingredients SET tesco_sku=? WHERE id=?', (sku, ingredient_id))
        db.commit()
        db.close()
        flash(f"Matched \"{title or sku}\"", 'success')
        return redirect(url_for('meal_detail', meal_id=row['meal_id']))
    row = db.execute('SELECT * FROM persistent_ingredients WHERE id=?', (ingredient_id,)).fetchone()
    if not row:
        db.close()
        return 'Ingredient not found', 404
    conflict = _sku_conflict(db, sku, ingredient_id, 'persistent_ingredients')
    db.execute('UPDATE persistent_ingredients SET tesco_sku=? WHERE id=?', (sku, ingredient_id))
    db.commit()
    db.close()
    if conflict:
        return redirect(url_for('merge_confirm', keep_id=ingredient_id, drop_id=conflict['id']))
    flash(f"Matched \"{title or sku}\"", 'success')
    return redirect(url_for('persistent_ingredients'))


def _form_float(field):
    raw = (request.form.get(field) or '').strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@app.route('/tesco/select_sku/<int:ingredient_id>/<kind>', methods=['POST'])
def tesco_select_sku(ingredient_id, kind):
    """Store a manually entered Tesco SKU for an ingredient.

    Looks the product up to display its title; if the lookup fails the SKU
    is still saved (the user said they know it) with a warning.
    """
    sku = (request.form.get('sku') or '').strip()
    if not sku or not sku.isdigit():
        return 'Enter a numeric Tesco SKU', 400
    if kind == 'ing':
        table = 'ingredients'
    elif kind == 'persist':
        table = 'persistent_ingredients'
    else:
        return 'Unknown ingredient kind', 404
    db = get_db()
    row = db.execute(f'SELECT * FROM {table} WHERE id=?', (ingredient_id,)).fetchone()
    if not row:
        db.close()
        return 'Ingredient not found', 404
    back_url = (url_for('meal_detail', meal_id=row['meal_id']) if kind == 'ing'
                else url_for('persistent_ingredients'))
    lookup_failed = False
    try:
        product = tesco.get_product(sku)
        title = product['title'] or sku
        _cache_product(db, product, matched_term=row['name'])
    except tesco.TescoError:
        title, lookup_failed = sku, True
    db.execute(f'UPDATE {table} SET tesco_sku=? WHERE id=?', (sku, ingredient_id))
    db.commit()
    conflict = None
    if table == 'persistent_ingredients':
        conflict = _sku_conflict(db, sku, ingredient_id, 'persistent_ingredients')
    db.close()
    if conflict:
        return redirect(url_for('merge_confirm', keep_id=ingredient_id, drop_id=conflict['id']))
    if lookup_failed:
        flash(f"Could not look up SKU {sku} - saved it anyway. Check the match later.", 'warning')
    else:
        flash(f"Matched \"{title}\" (SKU {sku})", 'success')
    return redirect(back_url)


@app.route('/tesco/match/<int:ingredient_id>', methods=['POST'])
def tesco_match_ingredient(ingredient_id):
    """Match a regular meal ingredient to a Tesco product (top result)."""
    db = get_db()
    ing = db.execute('SELECT * FROM ingredients WHERE id=?', (ingredient_id,)).fetchone()
    if not ing:
        db.close()
        return 'Ingredient not found', 404
    product, _results = match_ingredient_tesco(ing['name'])
    if product:
        db.execute('UPDATE ingredients SET tesco_sku=? WHERE id=?', (product['sku'], ingredient_id))
        db.commit()
        flash(f"Matched \"{product['title']}\"", 'success')
    else:
        flash(f"No Tesco product found for \"{ing['name']}\". Try again later.", 'warning')
    db.close()
    return redirect(url_for('meal_detail', meal_id=ing['meal_id']))


@app.route('/tesco/match_persistent/<int:ingredient_id>', methods=['POST'])
def tesco_match_persistent(ingredient_id):
    """Match a persistent ingredient to a Tesco product (top result)."""
    db = get_db()
    ing = db.execute('SELECT * FROM persistent_ingredients WHERE id=?', (ingredient_id,)).fetchone()
    if not ing:
        db.close()
        return 'Ingredient not found', 404
    product, _results = match_ingredient_tesco(ing['name'])
    conflict = None
    if product:
        db.execute('UPDATE persistent_ingredients SET tesco_sku=? WHERE id=?', (product['sku'], ingredient_id))
        db.commit()
        conflict = _sku_conflict(db, product['sku'], ingredient_id, 'persistent_ingredients')
        flash(f"Matched \"{product['title']}\"", 'success')
    else:
        flash(f"No Tesco product found for \"{ing['name']}\". Try again later.", 'warning')
    db.close()
    if conflict:
        return redirect(url_for('merge_confirm', keep_id=ingredient_id, drop_id=conflict['id']))
    return redirect(url_for('persistent_ingredients'))


@app.route('/tesco/add_to_basket', methods=['POST'])
def tesco_add_to_basket():
    """Add every shopping-list item that has a Tesco SKU to the basket."""
    if not tesco.auth_status()['signed_in']:
        flash('Sign in to Tesco first.', 'warning')
        return redirect(url_for('tesco_status_page'))
    db = get_db()
    items = db.execute('SELECT * FROM shopping_list_items WHERE tesco_sku IS NOT NULL AND tesco_sku != ""').fetchall()
    db.close()
    if not items:
        flash('No shopping list items have Tesco products matched yet.', 'warning')
        return redirect(url_for('shopping_list_get'))
    added, errors = 0, []
    for item in items:
        qty = tesco.parse_qty(item['quantity'])
        try:
            tesco.basket_set(item['tesco_sku'], qty)
            added += 1
        except tesco.TescoError as exc:
            errors.append(f"{item['name']}: {str(exc)[:120]}")
    if errors:
        flash('Added %d item(s); %d failed: %s' % (added, len(errors), '; '.join(errors[:3])), 'warning')
    else:
        flash(f'Added {added} item(s) to your Tesco basket!', 'success')
    return redirect(url_for('shopping_list_get'))


if __name__ == "__main__":
    datadir.migrate_legacy_db()
    init_db()
    import sys
    port = int(os.environ.get('PORT', '5000'))
    # Frozen installs serve with waitress; dev keeps the Flask debug server.
    # FLASK_DEBUG=0 turns the debug reloader off (used by the self-updater's
    # re-exec so the old process doesn't come back on top of the new one).
    if getattr(sys, 'frozen', False):
        # Frozen installs serve the whole LAN (family members open vote
        # links via the machine's network name, e.g. shoppingapp.local).
        import socket
        import threading
        import time
        import webbrowser

        def _open_browser(delay):
            time.sleep(delay)
            try:
                webbrowser.open('http://localhost:%d' % port)
            except Exception:
                pass

        def _port_in_use():
            s = socket.socket()
            s.settimeout(0.25)
            try:
                s.connect(('127.0.0.1', port))
                return True
            except OSError:
                return False
            finally:
                s.close()

        if os.environ.get('SHOPPING_APP_NO_BROWSER') != '1' and _port_in_use():
            # An instance is already running — the shortcut is just a
            # launcher, so hand the user to the existing app.
            _open_browser(0.5)
            sys.exit(0)
        if os.environ.get('SHOPPING_APP_NO_BROWSER') != '1':
            threading.Thread(target=_open_browser, args=(1.0,), daemon=True).start()
        from waitress import serve
        serve(app, host='0.0.0.0', port=port)
    else:
        debug = os.environ.get('FLASK_DEBUG', '1') != '0'
        app.run(debug=debug, use_reloader=debug, host='127.0.0.1', port=port)
