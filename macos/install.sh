#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer must run on macOS." >&2
  exit 1
fi

SRC_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ASSET_DIR="$HOME/.config/karabiner/assets/complex_modifications"
mkdir -p "$ASSET_DIR"
install -m 0644 "$SRC_DIR/xiaomi-remote-presenter.json" "$ASSET_DIR/xiaomi-remote-presenter.json"
install -m 0644 "$SRC_DIR/xiaomi-remote-video-speed.json" "$ASSET_DIR/xiaomi-remote-video-speed.json"

echo "Karabiner rule installed:"
echo "  $ASSET_DIR/xiaomi-remote-presenter.json"
echo "  $ASSET_DIR/xiaomi-remote-video-speed.json (optional)"
echo
echo "Open Karabiner-Elements -> Complex Modifications -> Add predefined rule"
echo "and enable the Xiaomi Remote 2 Pro Presenter rules."

echo
echo "For video OK, install ../browser/xiaomi-remote-video.user.js in Tampermonkey/Violentmonkey."
echo "Video speed UP/DOWN rules are NOT enabled automatically (they replace scroll)."
