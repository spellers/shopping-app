# Shopping App — Distribution

Two single-file artifacts, both built on this machine:

| File | Platform | What the user does |
|---|---|---|
| `dist/installer/ShoppingApp-Setup-1.5.0.exe` | Windows 10/11 (64-bit) | Double-click, follow the wizard |
| `dist/ShoppingApp-x86_64.AppImage` | Linux (64-bit) | Double-click (or `chmod +x`, then run) |

Both bundle everything the app needs: Python runtime, the web app, a
portable Node.js runtime, and the JS backends for the supermarket
providers — the Tesco (basketeer) CLI, open-supermarkets (Sainsbury's)
and playwright (headless/managed Chrome for Asda baskets and Sainsbury's
sign-in). The user does **not** need Python, Node, or any build tools.

## One external requirement: Google Chrome

The supermarket integrations drive the user's own Google Chrome:

- **Tesco** — headed browser, persistent profile in `~/.basketeer/chrome-profile`
- **Asda** — headless Chrome for guest-basket calls, profile in `~/.asda/`
- **Sainsbury's** — headed Chrome for sign-in (human completes MFA), profile in `~/.sainsburys/chrome-profile`

If Chrome isn't installed the app still works, but those features will
show a friendly "install Chrome" notice instead of an error.
Morrisons and Waitrose use plain HTTP and need no browser.

## Where data lives

All user data (SQLite DB, Flask secret key, per-retailer sessions and
Chrome profiles) lives in a per-user data directory, never next to the
executable:

- Linux: `~/.local/share/shopping-app/`, plus `~/.basketeer/`, `~/.asda/`, `~/.sainsburys/`, `~/.morrisons/`, `~/.waitrose/`
- Windows: `%LOCALAPPDATA%\ShoppingApp\`, plus `%USERPROFILE%\.basketeer\`, `\.asda\`, `\.sainsburys\`, `\.morrisons\`, `\.waitrose\`

This means:
- the install dir can be on a read-only volume (AppImage is a read-only mount)
- uninstalling / deleting the app never touches the user's data
- first run of the packaged app is a fresh empty DB (migrating the dev
  DB into a distribution build is intentionally out of scope)

## Verified

- **Linux AppImage**: direct execution (FUSE) mounts and serves HTTP;
  app picks a free port and opens the browser. (`--appimage-extract-and-run`
  is the fallback if FUSE is unavailable, e.g. some container setups.)
- **Windows installer**: silent install completed under Wine
  ("Installation process succeeded"), installed app launched and served
  HTTP (root 302, `/tesco/login_status` JSON).
  Full end-to-end on a real Windows machine is still worth a spot check —
  the Wine run exercises the same binaries but not a real desktop.

## Building

```bash
# Linux AppImage  (two steps: freeze, then package)
venv/bin/python build/build.py linux   # -> dist/ShoppingApp/
bash build/build_appimage.sh           # -> dist/ShoppingApp-x86_64.AppImage

# Windows  (two steps: freeze under Wine, then Inno Setup)
venv/bin/python build/build.py windows # -> dist/ShoppingApp/ (Windows PE)
WINEPREFIX=$HOME/odysseus/data/.wine DISPLAY=:99 wine \
  "$HOME/odysseus/data/.wine/drive_c/InnoSetup7/ISCC.exe" build/installer.iss
                                       # -> dist/installer/ShoppingApp-Setup-<ver>.exe
```

Build host prerequisites (all present here):
- `python3`, `node`, `pip`, `mksquashfs` (squashfs-tools)
- PyInstaller (in `venv/`)
- Linux: the verified type2 runtime at `build/runtime-61e6688-x86_64`
  (extracted from the linuxdeploy AppImage; `build_appimage.sh` concatenates
  it with a zstd squashfs payload — no appimagetool involved)
- Windows: Wine with the embedded Python at `build/winpy`, Inno Setup
  (6.3.3 or 7.x both work; the `.iss` handles both via `#if VER`)

## Known build-host quirks (recorded so they aren't re-discovered)

1. **AppImage runtime**: the type2-runtime `75849dc` that appimagetool 14
   fetches by default fails on this machine (`fusermount3` → EPERM, mount
   dies <100 ms). The linuxdeploy runtime (`61e6688`) works. The build
   script bakes in the working runtime.
2. **Inno Setup under Wine**: setup programs need an X display even in
   `/SILENT` mode (start Xvfb first); `{autopf}` expansion is broken in
   this Wine build, so the installer uses `{localappdata}` with
   `PrivilegesRequired=lowest` (per-user install, no admin needed).
3. **Inno 7.1.0 renamed `OutputBaseName` → `OutputBaseFilename`** — the
   script picks the right one via `#if VER >= 70000`.
