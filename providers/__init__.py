"""Grocer provider abstraction (multi-grocer plan, step 2).

Each supermarket backend implements the Grocer interface and registers a
singleton in REGISTRY keyed by its DB `retailer` value. app.py talks to
retailers only through get_grocer()/list_grocers(); it never imports a
specific provider module.

Adding a retailer = new module in this package + one registry line here
(see PLAN-multi-grocer.md).
"""


class GrocerError(Exception):
    """A provider-level failure (API error, missing CLI, timeout, ...).

    Providers translate their own exceptions into this; callers can catch
    it regardless of which retailer is behind it.
    """


class Grocer:
    """Interface every supermarket backend must implement.

    Product dicts use one shared shape across all providers:
        {sku, title, brand, price, unit_price, unit_of_measure,
         image_url, on_offer}
    (any key may be ''/None when the retailer doesn't have that data)
    """
    key = None          # DB retailer value, e.g. 'tesco'
    name = None         # human display name, e.g. 'Tesco'

    supports_search = True      # catalogue search available
    supports_basket = True      # remote basket write available
    supports_auth = True        # needs (and has) a sign-in flow

    def search(self, query, limit=5):
        """Search the catalogue. Returns list of product dicts."""
        raise GrocerError(f'{self.name}: search not supported')

    def get_product(self, sku):
        """Look up one product by SKU. Returns a product dict."""
        raise GrocerError(f'{self.name}: product lookup not supported')

    def auth_status(self):
        """Return {'signed_in': bool}. Must be cheap/safe (templates call it)."""
        return {'signed_in': False}

    def login(self):
        """Start an interactive sign-in (background thread). Returns True if
        started, False if already running."""
        return False

    def login_status(self):
        """Return a dict with 'running' (and provider extras) for polling."""
        return {'running': False}

    def basket(self):
        """Return the remote basket contents (provider-specific shape)."""
        raise GrocerError(f'{self.name}: basket not supported')

    def basket_set(self, sku, qty):
        """Set a basket line to an exact quantity (0 removes it)."""
        raise GrocerError(f'{self.name}: basket not supported')

    def checkout_url(self):
        """Return the URL to hand the user for final checkout, or None if
        the provider has no checkout hand-off."""
        return None

    def parse_qty(self, quantity_text):
        """Extract an integer basket count from free-text recipe quantities.
        Providers whose basket API doesn't take counts can keep the default
        of 1."""
        return 1


REGISTRY = {}


def register(grocer):
    """Register a provider singleton under its key."""
    if not grocer.key or not grocer.name:
        raise ValueError('Grocer.key and Grocer.name are required')
    if grocer.key in REGISTRY:
        raise ValueError(f'grocer already registered: {grocer.key}')
    REGISTRY[grocer.key] = grocer
    return grocer


def get_grocer(name):
    """Return the provider for a DB retailer value, or None if unknown."""
    return REGISTRY.get(name)


def list_grocers():
    """All registered providers, in display-name order (for selectors)."""
    return sorted(REGISTRY.values(), key=lambda g: g.name.lower())


# Import provider modules for their registration side effects.
from . import tesco as _tesco  # noqa: E402,F401
from . import sainsburys as _sainsburys  # noqa: E402,F401
from . import asda as _asda  # noqa: E402,F401
register(_tesco.TescoGrocer())
register(_sainsburys.SainsburysGrocer())
register(_asda.AsdaGrocer())
