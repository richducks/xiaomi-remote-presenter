#!/usr/bin/env bash
set -euo pipefail

APP_ID="xiaomi-remote-wps-linux"
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${APP_ID}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="${UNIT_DIR}/${APP_ID}.service"
RULE_PATH="/etc/udev/rules.d/71-xiaomi-remote-wps.rules"
TARGET_USER="${USER}"

if command -v apt-get >/dev/null 2>&1; then
  echo "[1/5] Installing Ubuntu dependencies..."
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-evdev x11-utils libxtst6 acl
else
  echo "This installer currently targets Ubuntu/Debian systems (apt-get required)." >&2
  exit 1
fi

echo "[2/5] Installing application files..."
mkdir -p "${APP_DIR}" "${UNIT_DIR}"
install -m 0755 "${ROOT_DIR}/remote_hid_filter.py" "${APP_DIR}/remote_hid_filter.py"
python3 -m venv --system-site-packages "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -c 'import evdev; print("evdev:", evdev.__version__)'

echo "[3/5] Installing narrow udev ACL rules..."
TMP_RULE="$(mktemp)"
cat > "${TMP_RULE}" <<EOF
# Xiaomi Remote 2 Pro (VID 2717, PID 32b8) for ${TARGET_USER}
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{id/vendor}=="2717", ATTRS{id/product}=="32b8", RUN+="/usr/bin/setfacl -m u:${TARGET_USER}:rw /dev/%k"
# uinput is required to create the filtered virtual keyboard.
KERNEL=="uinput", SUBSYSTEM=="misc", RUN+="/usr/bin/setfacl -m u:${TARGET_USER}:rw /dev/%k"
EOF
sudo install -m 0644 "${TMP_RULE}" "${RULE_PATH}"
rm -f "${TMP_RULE}"
sudo udevadm control --reload-rules

for sysdev in /sys/class/input/event*; do
  [[ -r "${sysdev}/device/id/vendor" && -r "${sysdev}/device/id/product" ]] || continue
  vendor="$(cat "${sysdev}/device/id/vendor")"
  product="$(cat "${sysdev}/device/id/product")"
  if [[ "${vendor,,}" == "2717" && "${product,,}" == "32b8" ]]; then
    event_name="$(basename "${sysdev}")"
    sudo setfacl -m "u:${TARGET_USER}:rw" "/dev/input/${event_name}"
    sudo udevadm trigger --action=change "${sysdev}" || true
  fi
done
if [[ -e /dev/uinput ]]; then
  sudo setfacl -m "u:${TARGET_USER}:rw" /dev/uinput
fi

echo "[4/5] Installing systemd user service..."
cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=Xiaomi Remote 2 Pro for WPS (OK->F5, BACK->ESC)
After=graphical-session.target bluetooth.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/remote_hid_filter.py
Restart=always
RestartSec=2
KillSignal=SIGINT
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user import-environment DISPLAY XAUTHORITY WAYLAND_DISPLAY 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable --now "${APP_ID}.service"

echo "[5/5] Verifying..."
sleep 2
systemctl --user --no-pager --full status "${APP_ID}.service" || true
echo
echo "Installed. Open a .ppt/.pptx in WPS Presentation:"
echo "  OK   -> F5 / start slideshow"
echo "  Back -> Esc / exit slideshow"
echo "Logs: journalctl --user -fu ${APP_ID}.service"
