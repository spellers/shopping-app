#!/usr/bin/env python
"""Build the frozen ShoppingApp for a target platform.

Usage:
    python build/build.py linux    # -> dist/ShoppingApp/ (Linux)
    python build/build.py windows  # -> dist/ShoppingApp/ (Windows)

Steps: run PyInstaller with the spec, then stage the read-only resources
next to the executable:
    ShoppingApp/<ShoppingApp|ShoppingApp.exe>
    ShoppingApp/resources/node/...        (portable Node runtime)
    ShoppingApp/resources/node_modules/   (basketeer CLI + playwright-core)
    ShoppingApp/resources/templates/      (Flask templates)
    ShoppingApp/resources/scripts/        (tesco_login.js)
Layout matches datadir.node_executable(): resources/node/bin/node (linux)
or resources/node/node.exe (win).
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'build')
DIST = os.path.join(ROOT, 'dist')
APP = 'ShoppingApp'


def run(cmd, **kw):
    if cmd[0] == 'wine':
        cmd = [c.replace('\\', '/') for c in cmd]
    print('+', ' '.join(cmd))
    subprocess.run(cmd, check=True, **kw)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ('linux', 'windows'):
        sys.exit(__doc__)
    target = sys.argv[1]

    node_src = os.path.join(
        BUILD, 'node',
        'node-v22.22.1-linux-x64' if target == 'linux' else 'node-win-src-win')
    if not os.path.isdir(node_src):
        sys.exit(f'missing node runtime: {node_src} (download it into build/node/ first)')

    app_dir = os.path.join(DIST, APP)
    if os.path.isdir(app_dir):
        shutil.rmtree(app_dir)

    # Windows builds may be cross-compiled under Wine using an embeddable
    # Python (build/winpy).  Set WINE_PY to the wine python.exe path.
    win_py = os.environ.get('WINE_PY')
    if target == 'linux':
        pyinstaller_cmd = [os.path.join(ROOT, 'venv', 'bin', 'pyinstaller')]
    elif win_py:
        # Cross-compile under Wine: run the Windows embeddable Python
        # through wine (WINE_PY is the wine-visible .exe path).
        pyinstaller_cmd = ['wine', win_py, '-m', 'PyInstaller']
    else:
        pyinstaller_cmd = [os.path.join(ROOT, 'venv', 'Scripts', 'pyinstaller.exe')]
    run(pyinstaller_cmd + ['--noconfirm', '--distpath', DIST,
         '--workpath', os.path.join(BUILD, 'work'),
         os.path.join(BUILD, 'shopping_app.spec')])

    print('staging resources...')
    res = os.path.join(app_dir, 'resources')
    os.makedirs(res, exist_ok=True)

    def copy_tree(src, dst):
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        print(f'  {os.path.relpath(src, ROOT)} -> {os.path.relpath(dst, app_dir)}/')
        shutil.copytree(src, dst, symlinks=False,
                        ignore=shutil.ignore_patterns('__pycache__', '.DS_Store'))

    copy_tree(node_src, os.path.join(res, 'node'))
    copy_tree(os.path.join(ROOT, 'node_modules'), os.path.join(res, 'node_modules'))
    copy_tree(os.path.join(ROOT, 'templates'), os.path.join(res, 'templates'))
    copy_tree(os.path.join(ROOT, 'scripts'), os.path.join(res, 'scripts'))

    print('done ->', app_dir)


if __name__ == '__main__':
    main()
