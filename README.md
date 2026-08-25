# Shopping App

A local web app for household meal planning: shared meal lists, ingredient
voting, a shopping list, and a Tesco grocery-basket integration (via the
[basketeer](https://www.npmjs.com/package/basketeer) CLI, which drives a real
Chrome session through Playwright).

## Features

- **Meal tracker** — plan meals with ingredients and quantities
- **Voting** — household members vote on what to cook
- **Persistent ingredients** — standing pantry/store staples
- **Shopping list** — aggregated from meals; quantities parsed from free text
  (`x4`, `2 loaves`, `500g` → correct counts)
- **Tesco basket sync** — one click adds the shopping list to your Tesco
  online basket (requires Google Chrome, since basketeer drives a real
  browser session)

## Running from source (Linux)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
npm install                 # basketeer + playwright-core
venv/bin/python app.py      # http://127.0.0.1:5000
```

Tesco login: open the Tesco page in the app and sign in — a Chrome window
opens, you log in normally, and the session is harvested to
`~/.basketeer/`.

## Tests

```bash
venv/bin/pytest tests/      # 60 tests
```

## Data

All mutable data lives in a per-user data directory (never next to the
code), so the app can be installed read-only:

- Linux: `~/.local/share/shopping-app/`
- Windows: `%LOCALAPPDATA%\ShoppingApp\`

Override with the `SHOPPING_APP_DATA` environment variable.

## Packaging

Prebuilt artifacts (not committed — built on demand):

| Artifact | Build |
|---|---|
| `dist/ShoppingApp-x86_64.AppImage` | `venv/bin/python build/build.py linux && build/build_appimage.sh` |
| `dist/installer/ShoppingApp-Setup-<ver>.exe` | Windows: `build\build.py windows` then `iscc build\installer.iss` (cross-builds work under Wine) |

See [PACKAGING.md](PACKAGING.md) for the full build documentation, including
the runtime/tooling quirks (AppImage runtime choice, Inno-under-Wine display
requirements).

## Layout

```
app.py          Flask application (meals, votes, shopping list)
tesco.py        basketeer CLI wrapper (login, search, basket)
datadir.py      platform-aware data/resource paths (dev + frozen)
templates/      Jinja2 templates
scripts/        tesco_login.js (basketeer session harvest)
build/          PyInstaller spec, build scripts, Inno Setup script, icons
tests/          pytest suite
```
