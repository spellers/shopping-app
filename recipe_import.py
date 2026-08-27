"""Import meals from recipe web pages.

Layered, generic approach (no per-site scrapers):
  1. Fetch the page with urllib + browser-like headers.
  2. Parse the page's schema.org Recipe data (JSON-LD) - the standard that
     most major recipe sites embed, so one parser covers hundreds of sites.
  3. If the plain request is blocked (bot walls) or has no structured data,
     re-fetch with a headless browser (if one is installed) and re-parse.
  4. Last resort: pull the visible ingredient list from the HTML.

This module only fetches and parses; it never touches the database.
"""
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

FETCH_TIMEOUT = 20


class RecipeError(Exception):
    """Raised when a page cannot be read or no recipe is found in it."""


def _normalize(url):
    url = (url or '').strip()
    if not url:
        raise RecipeError('Please enter a recipe link.')
    if not re.match(r'^https?://', url, re.I):
        url = 'https://' + url
    if ' ' in url:
        raise RecipeError("That doesn't look like a link - try the full address, "
                          "e.g. https://www.example.com/recipes/...")
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc or '.' not in parsed.netloc:
        raise RecipeError("That doesn't look like a link - try the full address, "
                          "e.g. https://www.example.com/recipes/...")
    return url


def fetch_html(url, timeout=FETCH_TIMEOUT):
    """Fetch a page with browser-like headers. Raises RecipeError."""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.9',
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', 'replace')
    except Exception:
        raise RecipeError("Couldn't reach that page. Check the link is correct "
                          'and try again.')


def _find_chrome():
    for name in ('google-chrome', 'google-chrome-stable', 'chromium',
                 'chromium-browser', 'microsoft-edge', 'msedge'):
        path = shutil.which(name)
        if path:
            return path
    return None


def headless_html(url, timeout=35):
    """Render a page in a headless browser (for bot-walled / JS-heavy sites)."""
    chrome = _find_chrome()
    if not chrome:
        raise RecipeError('No headless browser available on this machine.')
    try:
        with tempfile.TemporaryDirectory() as td:
            # CREATE_NO_WINDOW: a windowless frozen app would otherwise
            # spawn a console window for the child process (Windows only).
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            proc = subprocess.run(
                [chrome, '--headless=new', '--no-first-run', '--no-default-browser-check',
                 '--disable-gpu', f'--user-data-dir={td}',
                 '--virtual-time-budget=15000', '--dump-dom', url],
                capture_output=True, timeout=timeout + 15, **kwargs)
        body = proc.stdout.decode('utf-8', 'replace')
        if len(body) < 500:
            raise RecipeError('The page blocked automated access.')
        return body
    except subprocess.TimeoutExpired:
        raise RecipeError('The page took too long to load.')
    except RecipeError:
        raise
    except Exception:
        raise RecipeError("Couldn't load that page in the browser.")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _clean_text(value):
    """Strip tags/entities/whitespace from a string or nested node."""
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return ' '.join(_clean_text(v) for v in value if v)
    if isinstance(value, dict):
        if 'name' in value:
            return _clean_text(value['name'])
        if '@value' in value:
            return _clean_text(value['@value'])
        return ''
    if isinstance(value, str):
        text = re.sub(r'<[^>]+>', ' ', value)
        return re.sub(r'\s+', ' ', html_lib.unescape(text)).strip()
    return str(value)


def _iter_nodes(data):
    """Yield every object in a JSON-LD payload (lists, @graph, nesting)."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_nodes(item)
    elif isinstance(data, dict):
        yield data
        for key in ('@graph', 'mainEntity', 'itemListElement', 'hasPart'):
            if key in data:
                yield from _iter_nodes(data[key])


def _jsonld_recipe(html):
    """Find a schema.org Recipe block (JSON-LD). Returns dict or None."""
    for block in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        for node in _iter_nodes(data):
            types = node.get('@type')
            types = types if isinstance(types, list) else [types]
            if 'Recipe' not in types:
                continue
            name = _clean_text(node.get('name'))
            if not name:
                continue
            raw = node.get('recipeIngredient')
            items = raw if isinstance(raw, list) else [raw]
            ingredients = [_clean_text(i) for i in items]
            ingredients = [i for i in ingredients if i]
            return {'name': name,
                    'description': _clean_text(node.get('description')),
                    'ingredients': ingredients}
    return None


def _html_fallback(html):
    """Last-resort parse: visible ingredient list after an 'ingredients' heading."""
    m = re.search(r'<h[1-6][^>]*>(.*?)</h[1-6]>\s*(?:<[^>]+>\s*)*<(ul|ol)\b[^>]*>(.*?)</\2>',
                  html, re.S | re.I)
    ingredients = []
    if m and re.search(r'ingredient', m.group(1), re.I):
        for li in re.findall(r'<li[^>]*>(.*?)</li>', m.group(3), re.S | re.I):
            text = _clean_text(li)
            if text:
                ingredients.append(text)
    if not ingredients:
        return None
    name = ''
    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
    if title:
        name = _clean_text(title.group(1))
        name = re.split(r'[\u2013\u2014|:-]', name)[0].strip()
    return {'name': name or 'Imported meal', 'description': '', 'ingredients': ingredients}


def parse_recipe(html):
    """Extract {name, description, ingredients} from recipe page HTML."""
    recipe = _jsonld_recipe(html)
    if recipe:
        return recipe
    return _html_fallback(html)


# ---------------------------------------------------------------------------
# Ingredient quantity splitting
# ---------------------------------------------------------------------------

_UNITS = (r'(?:kg|g|ml|l|tbsp|tsp|cups?|cans?|tins?|packs?|cloves?|slices?'
          r'|pinches?|bunches?|branches?|sticks?|sprigs?|heads?|pods?'
          r'|tablespoons?|teaspoons?)')
_NUM = r'(\d+(?:\.\d+)?|\d+\s*/\s*\d+)'


def split_ingredient(text):
    """'2 tbsp sweet chilli sauce' -> ('2 tbsp', 'sweet chilli sauce').

    Returns (quantity, name); quantity is '' when nothing is recognised.
    """
    t = re.sub(r'\s*\([^)]*\)\s*', ' ', text.strip()).strip()
    t = re.sub(r'\s+', ' ', t)
    # Drop recipe-note noise: "600g cooked rice see tip, below" -> "600g cooked rice"
    t = re.sub(r',?\s+see\s+(?:the\s+)?(?:tip|note|photo|below)[,\s]*(?:below)?\s*$',
               '', t, flags=re.I)
    t = re.sub(r',?\s+optional\s*$', '', t, flags=re.I)
    t = re.sub(r'\s+', ' ', t).strip(' ,;')
    m = re.match(r'^(' + _NUM + r'\s*(?:' + _UNITS + r'))\b\s*(?:of\s+)?(.*)$', t)
    if m:
        name = m.group(3).strip()
        return m.group(1).strip(), (name or t)
    m = re.match(r'^' + _NUM + r'\s+(.+)$', t)
    if m:
        return m.group(1), m.group(2).strip()
    m = re.match(r'^(?:a|an)\s+([a-z]+)\s+of\s+(.+)$', t, re.I)
    if m:
        return ('a ' + m.group(1)).lower(), m.group(2).strip()
    return '', t


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_recipe(url):
    """Fetch a recipe page and return {name, description, ingredients}.

    ingredients is a list of raw ingredient strings, e.g.
    '2 tbsp sweet chilli sauce'. Raises RecipeError on failure.
    """
    url = _normalize(url)
    plain = None
    try:
        plain = fetch_html(url)
    except RecipeError:
        pass
    recipe = parse_recipe(plain) if plain else None
    if recipe and recipe['ingredients']:
        return recipe
    try:
        rendered = headless_html(url)
        rendered_recipe = parse_recipe(rendered)
        if rendered_recipe and rendered_recipe['ingredients']:
            return rendered_recipe
    except RecipeError:
        pass
    if recipe:
        return recipe
    raise RecipeError(
        'That page loaded, but I could not find a recipe in it. '
        'Make sure the link points directly at a recipe page.')
