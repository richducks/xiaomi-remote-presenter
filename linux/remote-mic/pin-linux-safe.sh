#!/usr/bin/env bash
# Persist the currently working Ubuntu Xiaomi SAFE profile locally.
# All backups stay in the user's HOME, never in the public Git repository.
set -euo pipefail
umask 077

NEW=xiaomi-remote-video-only.service
OLD=xiaomi-remote-hid-filter.service
OLD_PPT=xiaomi-remote-wps-linux.service
BASE="${XDG_STATE_HOME:-$HOME/.local/state}/xiaomi-remote-presenter"
FILES=(video_only_hid.py video_browser_context.py chatgpt_web_bridge.py)
ACTION="${1:---backup}"
if [[ $# -gt 1 || "$ACTION" != "--backup" && "$ACTION" != "--verify" && "$ACTION" != "--restore" ]]; then
  echo "Usage: bash pin-linux-safe.sh [--backup|--verify|--restore]" >&2
  exit 2
fi

source_dir="$(systemctl --user show -P WorkingDirectory "$NEW")"
if [[ -z "$source_dir" || ! -d "$source_dir" ]]; then
  echo "SAFE service working directory unavailable." >&2
  exit 2
fi
for file in "${FILES[@]}"; do
  if [[ ! -f "$source_dir/$file" ]]; then
    echo "Missing deployed file: $file" >&2
    exit 2
  fi
done

if [[ "$ACTION" == "--backup" ]]; then
  for old in "$OLD" "$OLD_PPT"; do
    if systemctl --user is-active --quiet "$old"; then
      echo "Refusing snapshot: legacy HID service $old is still active" >&2
      exit 2
    fi
    if systemctl --user is-enabled --quiet "$old"; then
      echo "Legacy service $old is enabled for startup; disabling it."
      systemctl --user disable "$old" >/dev/null
    fi
  done
  systemctl --user enable --now "$NEW" >/dev/null
  systemctl --user is-active --quiet "$NEW"
  systemctl --user is-enabled --quiet "$NEW"
  mkdir -p "$BASE"
  snapshot="$(mktemp -d "$BASE/safe-$(date +%Y%m%d-%H%M%S)-XXXX")"
  for file in "${FILES[@]}"; do cp -p -- "$source_dir/$file" "$snapshot/$file"; done
  printf '%s\n' "$source_dir" > "$snapshot/deployed-directory"
  systemctl --user cat "$NEW" > "$snapshot/systemd-user-service.txt"
  (
    cd "$snapshot"
    sha256sum "${FILES[@]}" > checksums.sha256
  )
  ln -sfn -- "$snapshot" "$BASE/latest"
  echo "SAFE profile pinned; current service active and enabled at user login."
  echo "Local private backup: $snapshot"
  exit 0
fi

snapshot="$BASE/latest"
if [[ ! -d "$snapshot" ]]; then
  echo "No prior SAFE snapshot. Run --backup first." >&2
  exit 2
fi
target="$(cat "$snapshot/deployed-directory")"
if [[ "$source_dir" != "$target" ]]; then
  echo "Service source moved since snapshot; refusing automatic restore." >&2
  exit 2
fi
(cd "$snapshot" && sha256sum -c checksums.sha256 >/dev/null)

if [[ "$ACTION" == "--verify" ]]; then
  status=0
  for file in "${FILES[@]}"; do
    if ! cmp -s "$snapshot/$file" "$source_dir/$file"; then
      echo "Different from pinned backup: $file"; status=1
    fi
  done
  systemctl --user is-enabled --quiet "$NEW" || { echo "SAFE service not enabled"; status=1; }
  systemctl --user is-active --quiet "$NEW" || { echo "SAFE service not active"; status=1; }
  for old in "$OLD" "$OLD_PPT"; do
    if systemctl --user is-active --quiet "$old"; then
      echo "Legacy service is active: $old"; status=1
    fi
  done
  if [[ $status -eq 0 ]]; then echo "Pinned SAFE profile verified; no drift."; fi
  exit "$status"
fi

# Explicit --restore only. Back up current files before overwriting them.
for old in "$OLD" "$OLD_PPT"; do
  if systemctl --user is-active --quiet "$old"; then
    echo "Legacy HID service $old active; refusing restore." >&2
    exit 2
  fi
done
recovery="$(mktemp -d "$BASE/pre-restore-$(date +%Y%m%d-%H%M%S)-XXXX")"
for file in "${FILES[@]}"; do cp -p "$source_dir/$file" "$recovery/$file"; done
systemctl --user stop "$NEW"
for file in "${FILES[@]}"; do cp -p "$snapshot/$file" "$source_dir/$file"; done
systemctl --user enable --now "$NEW" >/dev/null
echo "Restored SAFE code from $snapshot (previous code: $recovery)"
