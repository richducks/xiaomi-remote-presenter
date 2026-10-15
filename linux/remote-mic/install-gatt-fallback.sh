#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname "$0")" && pwd)"
case "$ROOT" in *' '*) echo "Project path must not contain spaces" >&2; exit 2;; esac
test -x "$ROOT/.venv/bin/python" || { echo "Run Linux install.sh first" >&2; exit 2; }
unitdir="$HOME/.config/systemd/user"
mkdir -p "$unitdir"
cat >"$unitdir/xiaomi-remote-gatt-key-bridge.service" <<SERVICE
[Unit]
Description=Xiaomi RC003 BLE GATT HID fallback
After=bluetooth.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$ROOT/.venv/bin/python $ROOT/gatt_key_bridge.py
Restart=on-failure
RestartSec=8
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
SERVICE
systemctl --user daemon-reload
systemctl --user enable --now xiaomi-remote-gatt-key-bridge.service
echo "RC003 GATT fallback enabled."
