"""Backwards-compatibility shim - the Tesco backend now lives in
providers/tesco.py (multi-grocer plan, step 2).

Existing imports (app.py, tests) keep working unchanged. New code should
use `providers.get_grocer('tesco')` instead of importing this module.
"""
from providers import Grocer, GrocerError  # noqa: F401
from providers.tesco import (  # noqa: F401
    CLI_JS, LOGIN_SCRIPT, NODE, SESSION_FILE,
    TescoError, TescoGrocer,
    auth_status, basket, basket_set, get_product, login, login_status,
    parse_qty, search,
)
