#!/usr/bin/env bash
# Build dist/EmailAssistant-<version>-x86_64.AppImage (run via `make appimage`).
# Downloads (once, cached in build/appimage/cache, checked against pinned SHA256):
#   APPIMAGE_PYTHON_URL     relocatable CPython from python-build-standalone
#   APPIMAGETOOL_URL        appimagetool, which packs the AppDir into the AppImage
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${APPIMAGE_PYTHON_URL:?set in .env}" "${APPIMAGE_PYTHON_SHA256:?}" "${APPIMAGETOOL_URL:?}" "${APPIMAGETOOL_SHA256:?}"
BUILD="${APPIMAGE_BUILD_DIR:-$ROOT/build/appimage}"
CACHE="$BUILD/cache"
APPDIR="$BUILD/AppDir"
OUT="${APPIMAGE_OUTPUT_DIR:-$ROOT/dist}"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")"
NAME="EmailAssistant-$VERSION-x86_64.AppImage"

fetch() {  # url sha256 -> cached file path
    local file="$CACHE/$(basename "${1//%2B/+}")"
    if [ ! -f "$file" ]; then
        echo "Downloading $1" >&2
        curl -fL --retry 3 -o "$file.part" "$1"
        mv "$file.part" "$file"
    fi
    echo "$2  $file" | sha256sum -c --quiet - || { echo "Checksum mismatch for $file" >&2; rm -f "$file"; exit 1; }
    printf '%s' "$file"
}

mkdir -p "$CACHE" "$OUT"
PYTHON_TGZ="$(fetch "$APPIMAGE_PYTHON_URL" "$APPIMAGE_PYTHON_SHA256" | tail -n1)"
TOOL="$(fetch "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA256" | tail -n1)"
chmod +x "$TOOL"

echo "Assembling $APPDIR"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/opt/email-assistant"
tar -xzf "$PYTHON_TGZ" -C "$APPDIR/opt"            # -> opt/python
PY="$APPDIR/opt/python/bin/python3"
"$PY" -m pip install --no-cache-dir --disable-pip-version-check --quiet "$ROOT"
# trim what a runtime never needs
find "$APPDIR/opt/python" -name "__pycache__" -type d -prune -exec rm -rf {} +
rm -rf "$APPDIR/opt/python/lib/python3."*/test "$APPDIR/opt/python/lib/python3."*/idlelib

RES="$APPDIR/opt/email-assistant"
cp -r "$ROOT/config" "$ROOT/prompts" "$ROOT/data" "$ROOT/docs" "$RES/"
mkdir -p "$RES/ui" && cp -r "$ROOT/ui/dist" "$RES/ui/dist"
cp "$ROOT/docker-compose.yml" "$ROOT/.env.example" "$ROOT/packaging/appimage/launcher.py" "$RES/"

cp "$ROOT/packaging/appimage/AppRun" "$APPDIR/AppRun"
cp "$ROOT/packaging/appimage/email-assistant.desktop" "$APPDIR/"
cp "$ROOT/packaging/appimage/email-assistant.svg" "$APPDIR/email-assistant.svg"
ln -sf email-assistant.svg "$APPDIR/.DirIcon"

echo "Packing $OUT/$NAME"
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT/$NAME"
echo "Built $OUT/$NAME ($(du -h "$OUT/$NAME" | cut -f1))"
