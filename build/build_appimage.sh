#!/usr/bin/env bash
# Build ShoppingApp-x86_64.AppImage from dist/ShoppingApp (run build.py linux first).
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
DIST="$ROOT/dist/ShoppingApp"

[ -x "$DIST/ShoppingApp" ] || { echo "dist/ShoppingApp missing - run: venv/bin/python build/build.py linux"; exit 1; }

APPDIR="$ROOT/build/AppDir"
rm -rf "$APPDIR"
rm -f "$ROOT"/build/ShoppingApp*.AppImage "$ROOT"/build/dist-test.AppImage
mkdir -p "$APPDIR/usr/bin"

# Copy the whole app (binary + _internal + resources) into usr/bin/
cp -a "$DIST/." "$APPDIR/usr/bin/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -e
# Find a free port and start the app, then open the web UI in the browser.
cd "$(dirname "$(readlink -f "$0")")/usr/bin"
START_PORT="${PORT:-5000}"
PORT=$START_PORT
for i in 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19; do
    p=$((START_PORT + i))
    if ! (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null; then
        PORT=$p
        break
    fi
    exec 3>&- 3<&-
done
export PORT
./ShoppingApp &
APP_PID=$!
trap 'kill $APP_PID 2>/dev/null' EXIT
# wait for the server to come up
for i in $(seq 1 50); do
    if (exec 3<>/dev/tcp/127.0.0.1/$PORT) 2>/dev/null; then
        exec 3>&- 3<&-
        break
    fi
    sleep 0.2
done
URL="http://127.0.0.1:$PORT"
echo "Shopping App: $URL"
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
elif command -v sensible-browser >/dev/null 2>&1; then
    sensible-browser "$URL" >/dev/null 2>&1 &
fi
wait $APP_PID
EOF
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/ShoppingApp.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=ShoppingApp
Comment=Shared meal, voting and Tesco shopping list
Exec=AppRun
Icon=ShoppingApp
Terminal=false
Categories=Office;
EOF

# Icon filename must match the Icon= entry in the .desktop file
cp icon-256.png "$APPDIR/ShoppingApp.png"

# Assemble the AppImage manually: type2-runtime ELF + squashfs payload.
# (appimagetool 12/14 on this box pulls runtimes that fail to mount here with
# EPERM, and appimagetool 14 itself needs libgpgme.so.11 which isn't packaged.
# The runtime below (type2-runtime commit 61e6688) is verified to work.)
RUNTIME="$ROOT/build/runtime-61e6688-x86_64"
[ -x "$RUNTIME" ] || { echo "runtime missing: $RUNTIME"; exit 1; }

PAYLOAD="$ROOT/build/payload.sqsh"
mksquashfs "$APPDIR" "$PAYLOAD" -comp zstd -noappend -no-progress >/dev/null

OUT="$ROOT/dist/ShoppingApp-x86_64.AppImage"
rm -f "$OUT"
cat "$RUNTIME" "$PAYLOAD" > "$OUT"
chmod +x "$OUT"
rm -f "$PAYLOAD"

echo
echo "Built: $ROOT/dist/ShoppingApp-x86_64.AppImage"
du -sh "$ROOT/dist/ShoppingApp-x86_64.AppImage"
