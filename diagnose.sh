#!/usr/bin/env bash
set -u

echo "== Session =="
printf 'XDG_SESSION_TYPE=%s\nDISPLAY=%s\nWAYLAND_DISPLAY=%s\n' \
  "${XDG_SESSION_TYPE:-}" "${DISPLAY:-}" "${WAYLAND_DISPLAY:-}"

echo
echo "== Xiaomi input devices =="
for f in /sys/class/input/event*/device/name; do
  [[ -r "$f" ]] || continue
  name="$(cat "$f")"
  if [[ "$name" == *小米* || "$name" == *Xiaomi* ]]; then
    event_name="$(basename "$(dirname "$f")")"
    echo "${event_name}: ${name}"
    ls -l "/dev/input/${event_name}" 2>/dev/null || true
    getfacl -p "/dev/input/${event_name}" 2>/dev/null || true
  fi
done

echo
echo "== WPS active window =="
xprop -root _NET_ACTIVE_WINDOW 2>/dev/null || true
wid="$(xprop -root _NET_ACTIVE_WINDOW 2>/dev/null | awk '{print $NF}')"
if [[ -n "${wid}" && "${wid}" != "0x0" ]]; then
  xprop -id "${wid}" WM_CLASS _NET_WM_NAME WM_NAME 2>/dev/null || true
fi

echo
echo "== Service =="
systemctl --user --no-pager --full status xiaomi-remote-wps-linux.service 2>/dev/null || true

echo
echo "== Recent logs =="
journalctl --user -u xiaomi-remote-wps-linux.service --since '-10 min' --no-pager 2>/dev/null | tail -100 || true
