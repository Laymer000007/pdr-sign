#!/usr/bin/env bash
# Build dist/PDR-sign-<version>-x86_64.AppImage (+ .zsync) from the PyInstaller bundle.
#   packaging/appimage/build.sh            # expects dist/pdr-sign/ and appimagetool on PATH
#   APPIMAGETOOL=/path/to/appimagetool packaging/appimage/build.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_ID="io.github.Laymer000007.PdrSign"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/pdr_sign/__init__.py")"
BUNDLE="$ROOT/dist/pdr-sign"
APPDIR="$ROOT/build/AppDir"
OUT="$ROOT/dist/PDR-sign-$VERSION-x86_64.AppImage"
TOOL="${APPIMAGETOOL:-appimagetool}"
UPDATE_INFO="gh-releases-zsync|Laymer000007|pdr-sign|latest|PDR-sign-*-x86_64.AppImage.zsync"

[ -x "$BUNDLE/pdr-sign" ] || { echo "Build the bundle first: pyinstaller packaging/pdr-sign.spec" >&2; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/metainfo" "$APPDIR/usr/share/icons"
cp -a "$BUNDLE" "$APPDIR/usr/lib/pdr-sign"
ln -s ../lib/pdr-sign/pdr-sign "$APPDIR/usr/bin/pdr-sign"
cp "$ROOT/packaging/appimage/AppRun" "$APPDIR/AppRun"
cp "$ROOT/packaging/linux/$APP_ID.desktop" "$APPDIR/$APP_ID.desktop"
cp "$ROOT/packaging/linux/$APP_ID.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/packaging/linux/$APP_ID.metainfo.xml" "$APPDIR/usr/share/metainfo/$APP_ID.appdata.xml"
cp -a "$ROOT/packaging/linux/icons/hicolor" "$APPDIR/usr/share/icons/"
cp "$ROOT/packaging/linux/icons/hicolor/256x256/apps/$APP_ID.png" "$APPDIR/$APP_ID.png"
ln -s "$APP_ID.png" "$APPDIR/.DirIcon"

rm -f "$OUT" "$OUT.zsync"
# appimagetool writes the .zsync into the current folder, so run it from dist/.
cd "$ROOT/dist"
ARCH=x86_64 "$TOOL" --no-appstream -u "$UPDATE_INFO" "$APPDIR" "$OUT"
ls -la "$OUT"*
