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

echo "Karabiner rule installed:"
echo "  $ASSET_DIR/xiaomi-remote-presenter.json"
echo
echo "Open Karabiner-Elements -> Complex Modifications -> Add predefined rule"
echo "and enable the Xiaomi Remote 2 Pro Presenter rules."
