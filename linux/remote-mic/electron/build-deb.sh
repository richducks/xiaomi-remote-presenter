#!/usr/bin/env bash
set -euo pipefail
base="$(cd "$(dirname "$0")" && pwd)"
zip="$(printenv ELECTRON_ZIP || true)"
if [ -z "$zip" ]; then
  zip="$(find "$HOME/.cache/electron" -type f -name 'electron-v40.10.2-linux-x64.zip' -print -quit)"
fi
test -f "$zip" || { echo "Electron 40.10.2 Linux x64 ZIP not found" >&2; exit 2; }
node "$base/tests/smoke.cjs"
for f in "$base/"*.cjs; do node --check "$f"; done
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
dest="$tmp/pkg"
target="$dest/opt/xiaomi-remote-control"
mkdir -p "$dest/DEBIAN" "$dest/usr/bin" "$dest/usr/share/applications" "$target"
unzip -q "$zip" -d "$target"
mkdir -p "$target/resources/app"
cp "$base/"*.cjs "$base/"*.html "$base/"*.css "$base/package.json" "$base/ui-schema.json" "$target/resources/app/"
cat >"$dest/usr/bin/xiaomi-remote-control" <<'LAUNCH'
#!/bin/sh
exec /opt/xiaomi-remote-control/electron /opt/xiaomi-remote-control/resources/app "$@"
LAUNCH
chmod 755 "$dest/usr/bin/xiaomi-remote-control"
cat >"$dest/usr/share/applications/xiaomi-remote-control.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Xiaomi Remote 2 Pro
Name[zh_CN]=小米遥控器 2 Pro 控制中心
Comment=Xiaomi remote microphone, browser and WPS keys
Exec=/usr/bin/xiaomi-remote-control
Terminal=false
Categories=Utility;Settings;
StartupNotify=true
DESKTOP
cat >"$dest/DEBIAN/control" <<'CONTROL'
Package: xiaomi-remote-control
Version: 1.1.0
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Xiaomi Remote Linux Community <local@localhost>
Description: Electron app for Xiaomi Remote 2 Pro controls
 Manages existing Linux systemd user services and hot-reloaded key rules.
CONTROL
chmod 755 "$target/electron"
# .deb installs as root; SUID sandbox helper needs owner root and mode 4755.
chmod 4755 "$target/chrome-sandbox"
mkdir -p "$base/dist"
dpkg-deb --root-owner-group --build "$dest" "$base/dist/xiaomi-remote-control_1.1.0_amd64.deb"
echo "Built $base/dist/xiaomi-remote-control_1.1.0_amd64.deb"
