#!/usr/bin/env bash
set -euo pipefail
here="$(cd -- "$(dirname "$0")" && pwd)"
runtime="$(cd -- "$here/.." && pwd)"
if [[ "$runtime" =~ [[:space:]] ]]; then
 echo "Please use a checkout path without whitespace" >&2; exit 2
fi
if [[ ! -x /usr/bin/xiaomi-remote-control ]]; then
 echo "Install the Linux amd64 Electron deb first" >&2; exit 2
fi
out="$HOME/.local/share/applications/xiaomi-remote-control.desktop"
mkdir -p "$(dirname "$out")"
cat >"$out" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Xiaomi Remote 2 Pro
Name[zh_CN]=小米遥控器 2 Pro 控制中心
Exec=env XIAOMI_REMOTE_HOME=$runtime /usr/bin/xiaomi-remote-control
Terminal=false
Categories=Utility;Settings;
StartupNotify=true
DESKTOP
if command -v desktop-file-validate >/dev/null; then desktop-file-validate "$out"; fi
echo "Desktop launcher ready: $out"
