#!/usr/bin/env bash
set -euo pipefail
# Only install Python dependencies; no sudo, ACL, or service side effects.
ROOT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT_DIR"
if ! command -v python3 >/dev/null; then echo 'python3 required' >&2; exit 1; fi
if [[ ! -x .venv/bin/python ]]; then python3 -m venv --system-site-packages .venv; fi
.venv/bin/python -m pip install -e .
echo "Ready: $ROOT_DIR/.venv/bin/xiaomi-remote-mic doctor"
echo "Next: bash install-services.sh (review), then bash install-services.sh --enable"
