#!/usr/bin/env bash
set -euo pipefail

APP_ID="xiaomi-remote-wps-linux"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${APP_ID}"
UNIT_PATH="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/${APP_ID}.service"
RULE_PATH="/etc/udev/rules.d/71-xiaomi-remote-wps.rules"

systemctl --user disable --now "${APP_ID}.service" 2>/dev/null || true
rm -f "${UNIT_PATH}"
rm -rf "${APP_DIR}"
systemctl --user daemon-reload

if [[ -e "${RULE_PATH}" ]]; then
  sudo rm -f "${RULE_PATH}"
  sudo udevadm control --reload-rules
fi

echo "Removed ${APP_ID}."
echo "Re-pair/reconnect the remote or reboot if you want temporary device ACLs reset immediately."
