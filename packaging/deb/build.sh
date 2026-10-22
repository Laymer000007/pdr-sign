#!/usr/bin/env bash
# Build dist/pdr-sign_<version>_amd64.deb from the PyInstaller bundle in dist/pdr-sign/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_ID="io.github.Laymer000007.PdrSign"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/pdr_sign/__init__.py")"
BUNDLE="$ROOT/dist/pdr-sign"
PKG="$ROOT/build/deb/pdr-sign"
OUT="$ROOT/dist/pdr-sign_${VERSION}_amd64.deb"

[ -x "$BUNDLE/pdr-sign" ] || { echo "Build the bundle first: pyinstaller packaging/pdr-sign.spec" >&2; exit 1; }

rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/metainfo" "$PKG/usr/share/icons" "$PKG/usr/share/doc/pdr-sign" \
         "$PKG/usr/share/lintian/overrides"
cp -a "$BUNDLE" "$PKG/opt/pdr-sign"
ln -s /opt/pdr-sign/pdr-sign "$PKG/usr/bin/pdr-sign"
install -m 0644 "$ROOT/packaging/linux/$APP_ID.desktop" "$PKG/usr/share/applications/"
install -m 0644 "$ROOT/packaging/linux/$APP_ID.metainfo.xml" "$PKG/usr/share/metainfo/"
cp -a "$ROOT/packaging/linux/icons/hicolor" "$PKG/usr/share/icons/"
install -m 0644 "$ROOT/packaging/deb/copyright" "$PKG/usr/share/doc/pdr-sign/copyright"
install -m 0644 "$ROOT/packaging/deb/lintian-overrides" "$PKG/usr/share/lintian/overrides/pdr-sign"
printf 'pdr-sign (%s) unstable; urgency=medium\n\n  * Release %s. See https://github.com/Laymer000007/pdr-sign/releases\n\n -- corne <332404964+Laymer000007@users.noreply.github.com>  %s\n' \
    "$VERSION" "$VERSION" "$(date -R)" | gzip -9n > "$PKG/usr/share/doc/pdr-sign/changelog.Debian.gz"

# Tidy permissions: directories and executables 0755, everything else 0644.
find "$PKG" -type d -exec chmod 0755 {} +
find "$PKG" -type f -exec chmod 0644 {} +
chmod 0755 "$PKG/opt/pdr-sign/pdr-sign"

SIZE="$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)"
sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE/" "$ROOT/packaging/deb/control.in" > "$PKG/DEBIAN/control"
install -m 0755 "$ROOT/packaging/deb/postinst" "$PKG/DEBIAN/postinst"
install -m 0755 "$ROOT/packaging/deb/postrm" "$PKG/DEBIAN/postrm"

dpkg-deb --build --root-owner-group -Zxz "$PKG" "$OUT"
ls -la "$OUT"
