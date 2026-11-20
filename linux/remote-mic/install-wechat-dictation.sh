#!/usr/bin/env bash
# One-time offline Chinese dictation setup for Linux native WeChat.
set -euo pipefail
cd "$(dirname "$0")"
UV="$(command -v uv || true)"
if [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ]; then UV="$HOME/.local/bin/uv"; fi
if [ -z "$UV" ]; then
  echo 'Install uv (https://docs.astral.sh/uv/) before installing WeChat dictation.' >&2
  exit 1
fi
"$UV" venv --python "$(command -v python3)" .venv-stt
"$UV" pip install --python .venv-stt/bin/python 'faster-whisper==1.2.1'
if ! command -v wl-copy >/dev/null 2>&1; then
  if command -v apt >/dev/null 2>&1 && command -v dpkg-deb >/dev/null 2>&1; then
    mkdir -p .vendor/wl-clipboard
    (cd .vendor/wl-clipboard && apt download wl-clipboard && dpkg-deb -x wl-clipboard_*.deb .)
  else
    echo 'Install wl-clipboard to support native Wayland WeChat text pasting.' >&2
    exit 1
  fi
fi
HF_HUB_DISABLE_XET=1 .venv-stt/bin/python - <<'PY'
from faster_whisper import WhisperModel
from pathlib import Path
cache = Path('.vendor/stt-models')
WhisperModel('base', device='cpu', compute_type='int8', download_root=str(cache))
print('Chinese offline speech model ready; no runtime cloud transcription needed.')
PY
