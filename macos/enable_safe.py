#!/usr/bin/env python3
"""Safely add the Xiaomi browser-only rule to the selected Karabiner profile.

No root permissions. Back up existing settings and replace only previously
installed Xiaomi rules; preserve all unrelated user's rules and profiles.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent
SAFE_FILE = ROOT / "xiaomi-remote-safe.json"
DEFAULT_CONFIG = Path.home() / ".config/karabiner/karabiner.json"
RULE_PREFIX = "Xiaomi Remote 2 Pro SAFE · "


def apply_safe(config_file: Path, safe_file: Path = SAFE_FILE) -> tuple[Path, int]:
    if not config_file.is_file():
        raise ValueError(
            f"Karabiner settings not found: {config_file}. "
            "Open Karabiner-Elements once to create the profile, then retry."
        )
    saved = config_file.read_bytes()
    document = json.loads(saved)
    safe = json.loads(safe_file.read_text(encoding="utf-8"))
    profiles = document.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("Karabiner has no profiles; refusing to overwrite settings")
    chosen = [profile for profile in profiles if profile.get("selected") is True]
    if len(chosen) != 1:
        raise ValueError("Exactly one Karabiner profile must be selected")
    current = chosen[0]
    modifications = current.setdefault("complex_modifications", {})
    previous = modifications.setdefault("rules", [])
    if not isinstance(previous, list):
        raise ValueError("Unexpected Karabiner complex_modifications.rules format")
    additions = safe.get("rules")
    if not isinstance(additions, list) or not additions:
        raise ValueError("The Xiaomi SAFE rules file contains no rules")
    # Explicitly activating SAFE replaces earlier Xiaomi full presenter or
    # optional video rules. Preserve all unrelated user rules and all profiles;
    # backup captures the prior mode for manual restoration.
    from build_rules import build_core, build_optional_speed, build_optional_video_ok
    known = {rule["description"] for bundle in (
        build_core(), build_optional_speed(), build_optional_video_ok())
        for rule in bundle["rules"]}
    original = [rule for rule in previous
                if not (str(rule.get("description", "")).startswith(RULE_PREFIX)
                        or rule.get("description") in known)]
    new_rules = original + additions
    if new_rules == previous:
        return config_file, 0
    modifications["rules"] = new_rules
    now = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = config_file.with_name(f"karabiner.json.xiaomi-backup-{now}")
    if backup.exists():
        backup = config_file.with_name(f"karabiner.json.xiaomi-backup-{now}-{os.getpid()}")
    shutil.copy2(config_file, backup)
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    handle, temp = tempfile.mkstemp(dir=config_file.parent,
                                    prefix=".xiaomi-safe-karabiner-")
    try:
        os.chmod(temp, config_file.stat().st_mode & 0o777)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temp, config_file)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return backup, len(additions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        backup, count = apply_safe(args.config)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, f"SAFE mode not activated: {error}\n")
    if count:
        print(f"Enabled {count} device-scoped Xiaomi SAFE rules. Backup: {backup}")
        print("Karabiner may need to be restarted to reload the updated profile.")
    else:
        print("Xiaomi SAFE rules already installed; no changes needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
