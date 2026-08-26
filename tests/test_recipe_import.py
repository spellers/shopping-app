import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import recipe_import

JSONLD_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Chicken fried rice",
 "description":"A one-pot classic",
 "recipeIngredient":["1 tbsp sunflower oil","3 eggs","600g cooked rice"]}
</script>
</head><body><h1>Chicken fried rice</h1></body></html>
"""

GRAPH_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"WebPage","name":"x"},
 {"@type":"Recipe","name":{"@value":"Tag soup"},"recipeIngredient":["2 <b>potatoes</b>","1 can tomatoes"]}]
}
</script>
</head><body></body></html>
"""

NO_LD_PAGE = """
<html><head><title>Easy Pasta - My Kitchen</title></head><body>
<h2>Ingredients</h2>
<ul>
 <li>200g pasta</li>
 <li>1 onion, chopped</li>
 <li>a handful of basil</li>
</ul>
<h3>Method</h3>
<ol><li>Cook the pasta</li></ol>
</body></html>
"""


def test_parse_jsonld():
    r = recipe_import.parse_recipe(JSONLD_PAGE)
    assert r['name'] == 'Chicken fried rice'
    assert r['description'] == 'A one-pot classic'
    assert r['ingredients'] == ['1 tbsp sunflower oil', '3 eggs', '600g cooked rice']


def test_parse_jsonld_graph_and_tags():
    r = recipe_import.parse_recipe(GRAPH_PAGE)
    assert r['name'] == 'Tag soup'
    assert r['ingredients'] == ['2 potatoes', '1 can tomatoes']


def test_html_fallback():
    r = recipe_import.parse_recipe(NO_LD_PAGE)
    assert r['name'] == 'Easy Pasta'
    assert r['ingredients'] == ['200g pasta', '1 onion, chopped', 'a handful of basil']


def test_no_recipe_found():
    assert recipe_import.parse_recipe('<html><body><p>hello</p></body></html>') is None


def test_split_ingredient():
    assert recipe_import.split_ingredient('2 tbsp sweet chilli sauce') == ('2 tbsp', 'sweet chilli sauce')
    assert recipe_import.split_ingredient('600g cooked rice see tip, below') == ('600g', 'cooked rice')
    assert recipe_import.split_ingredient('3 eggs beaten with some seasoning') == ('3', 'eggs beaten with some seasoning')
    assert recipe_import.split_ingredient('a pinch of salt') == ('a pinch', 'salt')
    assert recipe_import.split_ingredient('1/2 tsp salt') == ('1/2 tsp', 'salt')
    assert recipe_import.split_ingredient('140g frozen sweetcorn (see tip)') == ('140g', 'frozen sweetcorn')
    assert recipe_import.split_ingredient('fresh herbs') == ('', 'fresh herbs')
    assert recipe_import.split_ingredient('600g cooked rice see tip, below') == ('600g', 'cooked rice')
    assert recipe_import.split_ingredient('2 tbsp ketchup, optional') == ('2 tbsp', 'ketchup')


def test_normalize_url():
    assert recipe_import._normalize('example.com/x') == 'https://example.com/x'
    assert recipe_import._normalize('  https://a.com/x  ') == 'https://a.com/x'
    with pytest.raises(recipe_import.RecipeError):
        recipe_import._normalize('')
    with pytest.raises(recipe_import.RecipeError):
        recipe_import._normalize('not a url')


def test_fetch_recipe_uses_fetched_html(monkeypatch):
    monkeypatch.setattr(recipe_import, 'fetch_html', lambda url, timeout=20: JSONLD_PAGE)
    r = recipe_import.fetch_recipe('https://example.com/recipe')
    assert r['name'] == 'Chicken fried rice'


def test_fetch_recipe_browser_fallback(monkeypatch):
    """Plain fetch fails (bot wall) -> headless browser copy is used."""
    def _no_plain(url, timeout=20):
        raise recipe_import.RecipeError('blocked')
    monkeypatch.setattr(recipe_import, 'fetch_html', _no_plain)
    monkeypatch.setattr(recipe_import, 'headless_html', lambda url, timeout=35: JSONLD_PAGE)
    r = recipe_import.fetch_recipe('https://blocked.example.com/recipe')
    assert r['name'] == 'Chicken fried rice'


def test_fetch_recipe_gives_up(monkeypatch):
    def _no_plain(url, timeout=20):
        raise recipe_import.RecipeError('blocked')
    monkeypatch.setattr(recipe_import, 'fetch_html', _no_plain)
    monkeypatch.setattr(recipe_import, 'headless_html',
                        lambda url, timeout=35: '<html><body>nothing</body></html>')
    with pytest.raises(recipe_import.RecipeError):
        recipe_import.fetch_recipe('https://example.com/nope')
