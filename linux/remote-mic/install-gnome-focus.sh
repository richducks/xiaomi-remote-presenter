#!/usr/bin/env bash
# Optional GNOME 50 Wayland foreground bridge for Xiaomi 2 Pro.
# Uses a previously installed, disabled Xiaomi-WPS extension UUID on systems
# where GNOME 50 cannot discover new extensions until the next login.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/xiaomi-wps-ok@local"
SRC_DIR="$HERE/gnome-focus-extension"
BACKUPS="$HOME/.local/state/xiaomi-remote-presenter"
command -v gnome-extensions >/dev/null || { echo "GNOME Extensions CLI required" >&2; exit 2; }
case "$(gnome-shell --version 2>/dev/null)" in
  *" 50."*) ;;
  *) echo "This compositor bridge is built for GNOME Shell 50 only." >&2; exit 2 ;;
esac
if [[ -f "$EXT_DIR/extension.js" ]] && ! cmp -s "$SRC_DIR/extension.js" "$EXT_DIR/extension.js"; then
    if gnome-extensions list --enabled 2>/dev/null | grep -Fxq 'xiaomi-wps-ok@local'; then
      echo "Existing Xiaomi WPS extension active; disable it before replacing." >&2
      exit 2
    fi
    mkdir -p "$BACKUPS"
    backup="$BACKUPS/gnome-wps-original-$(date +%Y%m%d-%H%M%S)"
    cp -a "$EXT_DIR" "$backup"
    echo "Original Xiaomi WPS extension backed up: $backup"
fi
mkdir -p "$EXT_DIR"
for file in extension.js metadata.json; do
    tmp="$(mktemp "$EXT_DIR/.new.XXXXXX")"
    cp "$SRC_DIR/$file" "$tmp"
    chmod 644 "$tmp"
    mv -f "$tmp" "$EXT_DIR/$file"
done
if ! gnome-extensions enable xiaomi-wps-ok@local; then
    echo "GNOME has not discovered the new extension. Sign out and log back in once, then enable xiaomi-wps-ok@local." >&2
    exit 3
fi
if ! timeout 3 gdbus call --session --dest org.gnome.Shell \
    --object-path /org/gnome/Shell/Extensions/XiaomiRemoteFocus \
    --method org.xiaomi.RemoteFocus.GetFocus >/dev/null; then
    echo "Focus bridge is not responding. Check gnome-extensions info xiaomi-wps-ok@local." >&2
    exit 4
fi
echo "GNOME compositor focus bridge is active and verified."
