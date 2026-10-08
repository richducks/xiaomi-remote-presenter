#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
SERVICE_BASE="$(printenv XDG_CONFIG_HOME || true)"
if [[ -z "$SERVICE_BASE" ]]; then SERVICE_BASE="$HOME/.config"; fi
SERVICE_DIR="$SERVICE_BASE/systemd/user"
if [[ "$ROOT_DIR" =~ [[:space:]] ]]; then echo "Use a project path without spaces." >&2;exit 2;fi
if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then echo "Run bash install.sh first." >&2;exit 2;fi
if [[ $# -gt 1 ]]; then echo "Usage: bash install-services.sh [--enable|--enable-mic]" >&2;exit 2;fi
action=''
if [[ $# -eq 1 ]];then action="$1";fi
if [[ -n "$action" && "$action" != "--enable" && "$action" != "--enable-mic" ]];then
  echo "Unsupported argument: $action" >&2;exit 2
fi
if [[ "$action" == "--enable" ]] && systemctl --user is-active --quiet xiaomi-remote-wps-linux.service; then
 echo "Old WPS HID service is active and grabs the same device. Stop it manually before enabling." >&2
 echo "systemctl --user disable --now xiaomi-remote-wps-linux.service" >&2
 exit 2
fi
mkdir -p "$SERVICE_DIR"
cat > "$SERVICE_DIR/xiaomi-remote-hid-filter.service" <<SERVICE
[Unit]
Description=Xiaomi Remote 2 Pro HID (WPS + Global Speed)
After=graphical-session.target bluetooth.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/.venv/bin/python $ROOT_DIR/remote_hid_filter.py
Restart=always
RestartSec=2
KillSignal=SIGINT
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
SERVICE
cat > "$SERVICE_DIR/xiaomi-chatgpt-web-bridge.service" <<SERVICE
[Unit]
Description=Xiaomi Remote browser bridge (Global Speed PiP + optional voice)
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/.venv/bin/python $ROOT_DIR/chatgpt_web_bridge.py
Restart=on-failure
RestartSec=3
KillSignal=SIGINT
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
SERVICE
cat > "$SERVICE_DIR/xiaomi-remote-mic.service" <<SERVICE
[Unit]
Description=Xiaomi Remote 2 Pro BLE/ATVV microphone
After=pipewire.service wireplumber.service bluetooth.target

[Service]
Type=simple
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/.venv/bin/xiaomi-remote-mic run --gain-db 6
Restart=on-failure
RestartSec=3
KillSignal=SIGINT
SuccessExitStatus=130
TimeoutStopSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
SERVICE
systemctl --user import-environment DISPLAY XAUTHORITY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP >/dev/null 2>&1 || true
systemctl --user daemon-reload
echo "Prepared units in $SERVICE_DIR"
case "$action" in
 --enable) systemctl --user enable --now xiaomi-remote-hid-filter.service xiaomi-chatgpt-web-bridge.service ;;
 --enable-mic) systemctl --user enable --now xiaomi-remote-mic.service ;;
 *) echo "Nothing started. Pass --enable or --enable-mic to enable.";;
esac
