"""Update checking + one-click in-app updates against GitHub Releases.

The app polls the GitHub Releases API for the newest release of
spellers/shopping-app, picks the installer asset for the current platform,
and lets the UI show a "new version available" banner. Results are cached
on disk for CHECK_INTERVAL so page loads never hit the network, and the
refresh runs in a background thread. Everything degrades silently when
offline — the app is fully usable without any update awareness.

One-click updates (start_update): the user clicks "Update now" and the app
downloads the installer itself, installs it, and restarts into the new
version — no terminal, no manual install.

- Installed app, Windows: silent Inno Setup installer; a watchdog (bundled
  Node) waits for this process to exit, then launches the new executable.
- Installed app, Linux: the new AppImage replaces the old one (or is staged
  in the data dir if the install location is read-only); a watchdog
  relaunches it after this process exits.
- Developer checkout (not frozen): `git fetch` + `git checkout <tag>` and
  the process re-execs itself. Refuses to run if the tree has unsaved
  local changes.

The job runs in a background thread and its progress is exposed via
job_status() for the progress page.
"""
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta

import datadir

VERSION = "1.5.0"

REPO = "spellers/shopping-app"
RELEASE_API = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASE_PAGE = "https://github.com/%s/releases" % REPO

CHECK_INTERVAL = timedelta(hours=4)
DISMISS_UNTIL = timedelta(days=7)
HTTP_TIMEOUT = 5

_cache_lock = threading.Lock()
# One inflight marker per data dir, so a refresh for one location never
# suppresses a refresh for another (and threads write to the dir they
# were scheduled for, not wherever the data dir resolves later).
_inflight = {}
_inflight_lock = threading.Lock()

# One update job at a time; progress is polled by the UI.
_job_lock = threading.Lock()
_JOB_INIT = {
    'state': 'idle',        # idle | downloading | installing | restarting | done | error
    'tag': None,
    'progress': 0.0,        # 0-100, meaningful in 'downloading'
    'message': '',
    'error': None,
    'manual_url': None,     # fallback download link, filled on error
}

_job = dict(_JOB_INIT)


def _new_job_state():
    """Fresh job state dict (module level keeps _job's identity stable)."""
    return dict(_JOB_INIT)


def _cache_file():
    return os.path.join(_data_dir(), "update_check.json")


def _cache_path(data_dir):
    return os.path.join(data_dir, "update_check.json")


def _dismiss_file():
    return os.path.join(_data_dir(), "update_dismissed.json")


def _data_dir():
    """Resolve the data dir per-call so env changes (tests) are honoured."""
    return datadir.data_dir()


def _read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_json(path, payload):
    try:
        with open(path, "w") as fh:
            json.dump(payload, fh)
    except OSError:
        pass


def parse_version(text):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3). None if not a simple semver-ish tag."""
    if not text:
        return None
    m = re.match(r'^v?(\d+)\.(\d+)\.(\d+)$', str(text).strip())
    return tuple(int(g) for g in m.groups()) if m else None


def newer(latest_tag, current=VERSION):
    """True if latest_tag is a version newer than current."""
    a, b = parse_version(latest_tag), parse_version(current)
    return bool(a and b and a > b)


def asset_for_platform(assets):
    """Pick the download asset for the current platform from a release's asset list.

    Expects the GitHub API asset shape ({'name': ..., 'browser_download_url': ...}).
    Returns (name, url) or None.
    """
    if not assets:
        return None
    if sys.platform == 'win32':
        want = (lambda n: n.lower().endswith('.exe'))
    else:
        want = (lambda n: n.lower().endswith('.appimage'))
    for asset in assets:
        name = asset.get('name', '')
        if want(name):
            url = asset.get('browser_download_url') or asset.get('url')
            if url:
                return name, url
    return None


def _fetch_latest():
    """GET the latest release. Returns a normalized dict or None (offline/404)."""
    req = urllib.request.Request(RELEASE_API, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'ShoppingApp-updater',
    })
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.load(resp)
    except Exception:
        return None
    tag = data.get('tag_name')
    if not tag:
        return None
    return {
        'tag': tag,
        'name': data.get('name') or tag,
        'page': data.get('html_url') or RELEASE_PAGE,
        'assets': data.get('assets') or [],
    }


def _load_cached():
    """Return (cache_dict, fresh_bool)."""
    data = _read_json(_cache_file())
    if not data:
        return None, False
    try:
        checked_at = datetime.fromisoformat(data['checked_at'])
    except (KeyError, ValueError):
        return data, False
    return data, datetime.now() - checked_at < CHECK_INTERVAL


def check_now(data_dir=None):
    """Synchronously refresh the cache (used at startup and by tests)."""
    if data_dir is None:
        data_dir = _data_dir()
    with _cache_lock:
        release = _fetch_latest()
        checked_at = datetime.now()
        if release is not None:
            payload = dict(release)
        else:
            # Offline: keep serving a previously known release, if any.
            old = _read_json(_cache_path(data_dir))
            payload = dict(old) if old else {'error': 'offline'}
        payload['checked_at'] = checked_at.isoformat()
        _write_json(_cache_path(data_dir), payload)
        return payload


def ensure_check():
    """Make sure a check is scheduled; never blocks a request.

    If the cache is fresh (or an inflight refresh exists) this returns
    immediately. Otherwise a background thread refreshes the cache.
    """
    _data, fresh = _load_cached()
    if fresh:
        return
    data_dir = _data_dir()
    with _inflight_lock:
        ev = _inflight.get(data_dir)
        if ev is None:
            ev = threading.Event()
            _inflight[data_dir] = ev
        if ev.is_set():
            return
        ev.set()

    def _work():
        try:
            check_now(data_dir)
        finally:
            ev.clear()
    threading.Thread(target=_work, daemon=True).start()


def dismiss(tag):
    """Hide the banner for this release tag for a week."""
    if not tag:
        return
    _write_json(_dismiss_file(), {
        'tag': tag,
        'until': (datetime.now() + DISMISS_UNTIL).isoformat(),
    })


def dismissed_tag():
    """The tag the user dismissed, if the dismissal is still in effect."""
    data = _read_json(_dismiss_file())
    if not data:
        return None
    try:
        until = datetime.fromisoformat(data['until'])
    except (KeyError, ValueError):
        return None
    return data.get('tag') if datetime.now() < until else None


def status():
    """Update status for the UI.

    Returns a dict: current_version, latest_version (or None), update_available,
    download_url, download_name, release_page, dismissed.
    """
    result = {
        'current_version': VERSION,
        'latest_version': None,
        'update_available': False,
        'download_url': None,
        'download_name': None,
        'release_page': RELEASE_PAGE,
        'dismissed': False,
    }
    data, _ = _load_cached()
    if not data or 'tag' not in data:
        return result
    tag = data.get('tag')
    result['latest_version'] = tag
    result['release_page'] = data.get('page') or RELEASE_PAGE
    if not newer(tag, VERSION):
        return result
    asset = asset_for_platform(data.get('assets'))
    if asset:
        result['download_name'], result['download_url'] = asset
    result['update_available'] = True
    result['dismissed'] = (dismissed_tag() == tag)
    return result


# ---------------------------------------------------------------------------
# One-click updates
# ---------------------------------------------------------------------------

def job_status():
    """Copy of the update job state, for the progress page to poll."""
    with _job_lock:
        return dict(_job)


def _set_job(**kw):
    with _job_lock:
        _job.update(kw)


def _download(url, dest, job):
    """Stream `url` to `dest` (via .part), reporting progress 0-100."""
    req = urllib.request.Request(url, headers={'User-Agent': 'ShoppingApp-updater'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get('Content-Length') or 0)
        with open(dest + '.part', 'wb') as fh:
            got = 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                if total:
                    _set_job(progress=round(100 * got / total, 1),
                             message='Downloading… %d%%' % round(100 * got / total))
    os.replace(dest + '.part', dest)


def start_update():
    """Kick off a one-click update for the newest available release.

    Returns True if the job was started. Returns False if an update is not
    currently known or another update is already running.
    """
    st = status()
    with _job_lock:
        if _job['state'] in ('downloading', 'installing', 'restarting'):
            return False
        if not (st['update_available'] and st['download_url']):
            return False
        _job.update(_new_job_state())
    threading.Thread(target=_run_update, args=(st,), daemon=True).start()
    return True


def _run_update(st):
    """Background worker: download the installer, install it, restart.

    A developer checkout doesn't need the installer at all — it just
    checks out the tag and restarts — so the (large) download only
    happens for installed (frozen) apps.
    """
    tag = st['latest_version']
    try:
        if getattr(sys, 'frozen', False):
            data = _data_dir()
            staging = os.path.join(data, 'updates')
            os.makedirs(staging, exist_ok=True)
            dest = os.path.join(staging, st['download_name'])

            _set_job(state='downloading', tag=tag, progress=0.0,
                     message='Downloading the new version…', error=None)
            _download(st['download_url'], dest, st)

            _set_job(state='installing', message='Installing the new version…',
                     error=None)
            _install_frozen(dest, st)
        else:
            _set_job(state='installing', tag=tag,
                     message='Installing the new version…', error=None)
            _update_dev_checkout(tag)
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the UI
        _set_job(state='error',
                 error=str(exc) or exc.__class__.__name__,
                 manual_url=st.get('download_url'))


def _git(cwd, *args):
    import subprocess
    res = subprocess.run(['git'] + list(args), cwd=cwd, capture_output=True,
                         text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or 'git %s failed' % args[0])
    return res.stdout.strip()


def _update_dev_checkout(tag):
    """Update a developer checkout: git fetch + checkout <tag>, then restart
    via the watchdog (port-based, so it also works with the Flask reloader)."""
    import socket
    app_dir = datadir.app_dir()
    # .git is a directory in normal checkouts but a *file* in worktrees
    if not os.path.exists(os.path.join(app_dir, '.git')):
        raise RuntimeError(
            'This copy of the app is not a git checkout, so it cannot '
            'update itself. Use the manual download instead.')
    dirty = _git(app_dir, 'status', '--porcelain')
    if dirty:
        raise RuntimeError(
            'This copy of the app has unsaved local changes, so it cannot '
            'update itself safely. Save or discard them first.\n' +
            '\n'.join(dirty.splitlines()[:5]))
    _git(app_dir, 'fetch', '--tags', '--force')
    _git(app_dir, 'checkout', '-q', tag)

    port = os.environ.get('PORT') or '5000'
    # argv: [script, target, port, tag]
    script = (
        "import json, os, socket, subprocess, sys, time, urllib.request\n"
        "target, port, want = sys.argv[1], int(sys.argv[2]), sys.argv[3].lstrip('v')\n"
        "def port_free():\n"
        "    s = socket.socket()\n"
        "    s.settimeout(0.25)\n"
        "    try:\n"
        "        s.connect(('127.0.0.1', port))\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
        "    finally:\n"
        "        s.close()\n"
        "def running_version():\n"
        "    try:\n"
        "        with urllib.request.urlopen(\n"
        "                'http://127.0.0.1:%d/updates/status' % port, timeout=2) as r:\n"
        "            return json.loads(r.read()).get('current_version')\n"
        "    except Exception:\n"
        "        return None\n"
        "while not port_free():\n"
        "    time.sleep(0.5)\n"
        "# The port is free — but a service manager (e.g. systemd) may bring\n"
        "# the app back up itself on the freshly checked-out code. If the new\n"
        "# version appears on its own, do not double-launch.\n"
        "deadline = time.time() + 15\n"
        "while time.time() < deadline:\n"
        "    if running_version() == want:\n"
        "        sys.exit(0)\n"
        "    time.sleep(1)\n"
        "env = dict(os.environ, FLASK_DEBUG='0',\n"
        "           SHOPPING_APP_NO_BROWSER='1')\n"
        "subprocess.Popen([sys.executable, target], env=env,\n"
        "                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
        "                 stdin=subprocess.DEVNULL, start_new_session=True)\n")
    _spawn_watchdog(script, os.path.join(app_dir, 'app.py'), port, tag)
    _set_job(state='restarting', message='Restarting the app…')
    time.sleep(2.0)
    os._exit(0)


# Watchdog for the Linux AppImage install. argv (node script):
# [node, script, pid, target, port, tag]
_WATCHDOG_JS = """
const {spawn} = require('child_process');
const pid = +process.argv[2];
const target = process.argv[3];
const port = process.argv[4] ? +process.argv[4] : null;
const want = process.argv[5] ? process.argv[5].replace(/^v/, '') : null;
const alive = () => {
  try { process.kill(pid, 0); return true; } catch (e) { return false; }
};
function version() {
  return new Promise((resolve) => {
    if (!port || !want) return resolve(null);
    const req = require('http').get(
        {host: '127.0.0.1', port, path: '/updates/status', timeout: 2000},
        (res) => {
          let body = '';
          res.on('data', (c) => body += c);
          res.on('end', () => {
            try { resolve(JSON.parse(body).current_version || null); }
            catch (e) { resolve(null); }
          });
        });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}
async function wait() {
  while (alive()) { await new Promise((r) => setTimeout(r, 500)); }
  // Old process gone — but a service manager may bring the app back up
  // itself (the AppImage was replaced in place). If the new version appears
  // on its own, do not double-launch.
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if ((await version()) === want) process.exit(0);
    await new Promise((r) => setTimeout(r, 1000));
  }
  spawn(target, [], {detached: true, stdio: 'ignore', env: process.env}).unref();
}
wait();
"""


def _spawn_watchdog(script, *args):
    """Launch a detached watchdog process: [node|python, script, *args].

    `script` is the watchdog program; .js-style scripts run under the
    bundled/system node, anything else under the current python.
    """
    import subprocess
    is_js = script.lstrip().startswith('const')
    name = '_update_watchdog.js' if is_js else '_update_watchdog.py'
    script_path = os.path.join(_data_dir(), 'updates', name)
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    interpreter = ([datadir.node_executable()] if is_js
                   else [sys.executable])
    with open(script_path, 'w') as fh:
        fh.write(script)
    # SHOPPING_APP_NO_BROWSER rides through process.env into whatever the
    # watchdog launches, so self-update restarts don't pop up a browser.
    subprocess.Popen(
        interpreter + [script_path] + [str(a) for a in args],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True,
        env=dict(os.environ, SHOPPING_APP_NO_BROWSER='1'))


def _install_frozen(dest, st):
    """Replace the installed application and restart into the new one.

    Never returns on success: it spawns a watchdog that relaunches the new
    version after this process exits.
    """
    import subprocess
    data = _data_dir()
    if sys.platform == 'win32':
        # Silent Inno Setup install (argv: [script, pid, installer, exe, port]).
        # The watchdog runs the installer, then relaunches the app once the
        # old process has let the port go — [Run] postinstall is skipped for
        # silent installs, so it does the launch itself.
        localappdata = os.environ.get('LOCALAPPDATA') or ''
        new_exe = os.path.join(localappdata, 'ShoppingApp', 'ShoppingApp.exe')
        port = os.environ.get('PORT') or '5000'
        script = (
            "const {execFile,spawn}=require('child_process');"
            "const installer=process.argv[3];const target=process.argv[4];"
            "const port=+process.argv[5];"
            "const launch=()=>{"
            "const p=spawn(target,[],{detached:true,stdio:'ignore',env:process.env});"
            "p.unref();};\n"
            "const tryLaunch=()=>{"
            "const s=require('net').connect(port,'127.0.0.1');"
            "s.on('connect',()=>{s.destroy();setTimeout(tryLaunch,500)});"
            "s.on('error',()=>{setTimeout(launch,500)});};\n"
            "execFile(installer,['/VERYSILENT','/SUPPRESSMSGBOXES'],{windows:true},"
            "(e)=>{if(e)process.exit(1);tryLaunch();});")
        # argv (node script): [node, script, pid, installer, target, port]
        _spawn_watchdog(script, os.getpid(), dest, new_exe, port)
        _set_job(state='restarting', message='Installing and restarting…')
        time.sleep(2.0)
        os._exit(0)
    else:
        # AppImage: replace the install copy if it is writable (the running
        # FUSE mount is a separate inode, so this is safe), otherwise stage
        # the new one next to the data dir and launch that.
        installed = os.environ.get('APPIMAGE')
        target = None
        if installed and os.path.isfile(installed) and os.access(installed, os.W_OK):
            tmp = installed + '.new'
            shutil.copy2(dest, tmp)
            os.replace(tmp, installed)
            os.chmod(installed, 0o755)
            target = installed
        else:
            target = os.path.join(data, 'ShoppingApp.AppImage')
            shutil.copy2(dest, target)
            os.chmod(target, 0o755)
        port = os.environ.get('PORT') or '5000'
        # argv (node script): [node, script, pid, target, port, tag]
        _spawn_watchdog(_WATCHDOG_JS, os.getpid(), target, port, st['latest_version'])
        _set_job(state='restarting', message='Restarting the app…')
        time.sleep(2.0)
        os._exit(0)
