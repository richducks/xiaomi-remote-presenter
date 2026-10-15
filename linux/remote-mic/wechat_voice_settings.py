"""Validated, privacy-preserving preferences for native WeChat voice.

These settings never enable automatic sending or a second transcription path.
"""
from __future__ import annotations
import json
from pathlib import Path

FILE = Path(__file__).with_name("wechat_voice_settings.json")
DEFAULT = {"version": 1, "enabled": True, "auto_focus_composer": True,
           "preview_settle_ms": 850}


def validate(config):
    if not isinstance(config, dict) or set(config) != set(DEFAULT):
        raise ValueError("invalid WeChat voice settings structure")
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("unsupported WeChat voice settings version")
    for key in ("enabled", "auto_focus_composer"):
        if type(config[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    timeout = config["preview_settle_ms"]
    if type(timeout) is not int or not 200 <= timeout <= 1800:
        raise ValueError("preview_settle_ms must be 200..1800")
    return dict(config)


def load_settings(path=FILE):
    try:
        if path.stat().st_size > 4096:
            raise ValueError("settings too large")
        return validate(json.loads(path.read_text(encoding="utf8")))
    except (OSError, ValueError, KeyError, TypeError):
        return dict(DEFAULT)


if __name__ == "__main__":
    import sys
    try:
        if len(sys.argv) != 3 or sys.argv[1] != "--check":
            raise ValueError("expected --check path")
        validate(json.loads(Path(sys.argv[2]).read_text(encoding="utf8")))
        print("VALID: WeChat voice settings")
    except Exception as exc:
        print("INVALID:", exc)
        raise SystemExit(1)
