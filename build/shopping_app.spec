# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the shopping app (onedir).

Build:  venv/bin/pyinstaller --distpath dist --workpath build/work build/shopping_app.spec
Resources (node, node_modules, templates, scripts) are copied next to the
executable by build/build.py, not by PyInstaller itself.
"""
import sys

block_cipher = None
APP_NAME = 'ShoppingApp'

a = Analysis(
    ['../app.py'],
    pathex=['..'],
    binaries=[],
    datas=[],
    hiddenimports=['waitress', 'jinja2', 'markupsafe'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
