"""Platform-aware locations for user data and bundled resources.

Everything mutable (SQLite DB, Tesco session, Chrome profile, secret key)
lives in a per-user data directory so the installed application stays
read-only. When the app is frozen by PyInstaller the bundled resources
(node + basketeer) live in a `resources` folder next to the executable.
"""
import os
import shutil
import sys
import uuid


def _is_frozen():
    return bool(getattr(sys, 'frozen', False))


def app_dir():
    """Directory holding the application code (read-only once installed)."""
    if _is_frozen():
        # PyInstaller unpacks onefile apps into a temp dir; resources must
        # come from the real install location instead.
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    """Per-user writable directory for the DB, Tesco session and secrets."""
    override = os.environ.get('SHOPPING_APP_DATA')
    if override:
        path = os.path.abspath(os.path.expanduser(override))
    elif sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
        path = os.path.join(base, 'ShoppingApp')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
        path = os.path.join(base, 'shopping-app')
    os.makedirs(path, exist_ok=True)
    return path


def db_path():
    """Path of the SQLite database (in the user data directory)."""
    return os.path.join(data_dir(), 'shopping_app.db')


def migrate_legacy_db():
    """One-off: move a pre-packaging DB from the app directory to data_dir()."""
    legacy = os.path.join(app_dir(), 'shopping_app.db')
    target = db_path()
    if os.path.exists(legacy) and not os.path.exists(target):
        try:
            shutil.move(legacy, target)
        except OSError:
            pass


def resource_dir():
    """Directory with bundled resources (node, basketeer, login scripts).

    Frozen: <install dir>/resources.  Dev: the project directory itself.
    """
    if _is_frozen():
        return os.path.join(app_dir(), 'resources')
    return app_dir()


def node_executable():
    """The node binary the basketeer CLI runs on.

    Frozen apps use the bundled portable node; dev uses the system node.
    Returns None if no usable node can be found.
    """
    res = resource_dir()
    if sys.platform == 'win32':
        candidates = [
            os.path.join(res, 'node', 'node.exe'),
        ]
    else:
        candidates = [
            os.path.join(res, 'node', 'bin', 'node'),
        ]
    for cand in candidates:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    system = shutil.which('node')
    if system:
        return system
    return candidates[0]  # let the caller surface a friendly error


def secret_key():
    """Persistent Flask secret key (created on first run)."""
    keyfile = os.path.join(data_dir(), 'secret.key')
    try:
        with open(keyfile) as fh:
            key = fh.read().strip()
            if key:
                return key
    except OSError:
        pass
    key = uuid.uuid4().hex
    try:
        with open(keyfile, 'w') as fh:
            fh.write(key)
        os.chmod(keyfile, 0o600)
    except OSError:
        pass
    return key


def find_chrome():
    """Locate the user's Google Chrome.

    basketeer drives the system Chrome (channel: "chrome"); without it,
    basket operations and sign-in cannot work. Returns the executable path
    or None.
    """
    if sys.platform == 'win32':
        pf = os.environ.get('ProgramFiles') or r'C:\Program Files'
        pf86 = os.environ.get('ProgramFiles(x86)') or r'C:\Program Files (x86)'
        local = os.environ.get('LOCALAPPDATA') or ''
        cands = [
            os.path.join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(pf86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(local, 'Google', 'Chrome', 'Application', 'chrome.exe'),
        ]
        for c in cands:
            if c and os.path.isfile(c):
                return c
    elif sys.platform == 'darwin':
        cands = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    else:
        cands = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/snap/bin/chromium',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
        ]
        for c in cands:
            if os.path.exists(c):
                return c
        for name in ('google-chrome', 'google-chrome-stable', 'chromium'):
            found = shutil.which(name)
            if found:
                return found
    return None
