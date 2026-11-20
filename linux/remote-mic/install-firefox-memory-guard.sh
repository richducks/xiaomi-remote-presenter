#!/usr/bin/env bash
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)"
local_dir="$HOME/.local/lib/xiaomi-remote-presenter"
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$local_dir" "$unit_dir"
install -m 0644 "$src/firefox_extension_memory_guard.py" "$local_dir/firefox_extension_memory_guard.py"
cat > "$unit_dir/xiaomi-firefox-extension-memory-guard.service" <<'SERVICE'
[Unit]
Description=Prevent runaway Firefox WebExtensions memory exhaustion
After=graphical-session.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/.local/lib/xiaomi-remote-presenter/firefox_extension_memory_guard.py
SERVICE
cat > "$unit_dir/xiaomi-firefox-extension-memory-guard.timer" <<'TIMER'
[Unit]
Description=Check Firefox extension memory every three minutes

[Timer]
OnBootSec=3min
OnUnitActiveSec=3min
AccuracySec=30s
Persistent=false
Unit=xiaomi-firefox-extension-memory-guard.service

[Install]
WantedBy=timers.target
TIMER
systemctl --user daemon-reload
systemctl --user enable --now xiaomi-firefox-extension-memory-guard.timer
systemctl --user start xiaomi-firefox-extension-memory-guard.service
systemctl --user is-active --quiet xiaomi-firefox-extension-memory-guard.timer
echo "Firefox extension memory failsafe enabled (two checks >= 7 GiB; 3 min apart)."
