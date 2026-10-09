#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer must run on macOS." >&2
  exit 1
fi
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--enable-safe" ) ]]; then
  echo "Usage: ./install.sh [--enable-safe]" >&2
  exit 2
fi

SRC_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ASSET_DIR="$HOME/.config/karabiner/assets/complex_modifications"
mkdir -p "$ASSET_DIR"
for name in xiaomi-remote-safe.json xiaomi-remote-presenter.json xiaomi-remote-video-ok.json xiaomi-remote-video-speed.json; do
  install -m 0644 "$SRC_DIR/$name" "$ASSET_DIR/$name"
done

echo "SAFE browser tab rules: $ASSET_DIR/xiaomi-remote-safe.json"
echo "Optional legacy full presenter/video OK/speed profiles are available but NOT enabled."
if [[ "${1:-}" == "--enable-safe" ]]; then
  if ! command -v python3 >/dev/null; then
    echo "Python 3 required for automatic SAFE profile activation." >&2
    exit 2
  fi
  echo "Activating Xiaomi SAFE rules in the current Karabiner profile (backup first)..."
  python3 "$SRC_DIR/enable_safe.py"
else
  echo "Open Karabiner-Elements -> Complex Modifications -> Add predefined rule"
  echo "Enable the three rules titled 'Xiaomi Remote 2 Pro SAFE ...'"
  echo "Or rerun: ./install.sh --enable-safe"
fi
echo "Optional video OK: the separate F13 rule intercepts remote Enter in ALL browser tabs."
echo "Do not enable video OK if normal browser Enter must remain untouched."
echo "Optional Global Speed D/A rule replaces browser scroll; enable only if desired."
echo "Browser video OK requires ../browser/xiaomi-remote-video.user.js."
