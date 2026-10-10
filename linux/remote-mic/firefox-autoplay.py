#!/usr/bin/env python3
"""Opt-in, profile-local Firefox autoplay settings for Xiaomi video use.

Never alter prefs.js (owned by Firefox), cookies, or website settings.
No changes are made without --apply.  Settings take effect after Firefox
restarts; next-episode selection remains the website's responsibility.
"""
from __future__ import annotations

import argparse
import configparser
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

PREFERENCES = {
    "media.autoplay.default": "0",
    "media.block-autoplay-until-in-foreground": "false",
}
ASSIGNMENT = re.compile(r'^\s*user_pref\s*\(\s*[\'\"]([^\'\"]+)[\'\"]\s*,\s*(.*?)\s*\)\s*;?')


def profile_from_root(root: Path) -> Path | None:
    config_path = root / "profiles.ini"
    if not config_path.is_file():
        return None
    config = configparser.ConfigParser(interpolation=None)
    config.read(config_path, encoding="utf-8")
    sections = [s for s in config.sections() if s.startswith("Profile")]
    selected = []
    # Installation default takes precedence when present; otherwise the
    # profile explicitly marked Default=1 must be unambiguous.
    for section in config.sections():
        if section.startswith("Install"):
            default = config.get(section, "Default", fallback="")
            for name in sections:
                if config.get(name, "Path", fallback="") == default:
                    selected.append(name)
    if not selected:
        selected = [s for s in sections if config.get(s, "Default", fallback="0") == "1"]
    selected = sorted(set(selected))
    if len(selected) != 1:
        raise RuntimeError(f"Ambiguous Firefox profile at {root}; supply --profile explicitly")
    section = selected[0]
    value = config.get(section, "Path", fallback="")
    if not value:
        raise RuntimeError(f"Firefox profile has no path: {section}")
    if config.get(section, "IsRelative", fallback="1") == "1":
        profile = (root / value).resolve()
        if not profile.is_relative_to(root.resolve()):
            raise RuntimeError("Firefox profile escapes installation directory")
    else:
        profile = Path(value).expanduser().resolve()
    if not profile.is_dir():
        raise RuntimeError(f"Firefox profile directory missing: {profile}")
    return profile


def select_profile(explicit: Path | None, home: Path) -> Path:
    if explicit is not None:
        profile = explicit.expanduser().resolve()
        if not profile.is_dir():
            raise RuntimeError("--profile must point to an existing Firefox profile")
        return profile
    roots = (
        home / "snap/firefox/common/.mozilla/firefox",
        home / ".mozilla/firefox",
    )
    choices = [p for root in roots if (p := profile_from_root(root)) is not None]
    if len(choices) != 1:
        raise RuntimeError("Cannot select one Firefox profile; supply --profile explicitly")
    return choices[0]


def read_prefs(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = ASSIGNMENT.match(line)
            if match and match.group(1) in PREFERENCES:
                result[match.group(1)] = match.group(2).strip()
    return result


def apply(profile: Path) -> tuple[bool, Path | None]:
    dest = profile / "user.js"
    original = dest.read_text(encoding="utf-8") if dest.exists() else ""
    lines = original.splitlines(keepends=True)
    filtered = [line for line in lines if not (
        (match := ASSIGNMENT.match(line)) and match.group(1) in PREFERENCES
    )]
    prefix = "" if not filtered or filtered[-1].endswith("\n") else "\n"
    contents = "".join(filtered) + prefix + "".join(
        f'user_pref("{key}", {value});\n' for key, value in PREFERENCES.items()
    )
    if contents == original:
        return False, None
    backup = None
    if dest.exists():
        label = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = dest.with_name(f"user.js.xiaomi-backup-{label}")
        counter = 1
        while candidate.exists():
            candidate = dest.with_name(f"user.js.xiaomi-backup-{label}-{counter}")
            counter += 1
        shutil.copy2(dest, candidate)
        backup = candidate
    fd, temp = tempfile.mkstemp(prefix=".xiaomi-autoplay-", dir=profile)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(contents)
        os.chmod(temp, 0o600)
        os.replace(temp, dest)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True, backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, help="Explicit Firefox profile directory")
    parser.add_argument("--apply", action="store_true", help="Opt in to autoplay on ALL websites")
    args = parser.parse_args(argv)
    try:
        profile = select_profile(args.profile, Path.home())
        print(f"Firefox profile: {profile}")
        print("Firefox current preferences (prefs.js):", read_prefs(profile / "prefs.js"))
        print("Persistent overrides (user.js):", read_prefs(profile / "user.js"))
        if not args.apply:
            print("Read-only status. Pass --apply to opt in to browser-wide autoplay.")
            return 0
        changed, backup = apply(profile)
        if backup:
            print(f"Previous user.js saved locally: {backup}")
        print("Persistent Firefox autoplay configuration:", "updated" if changed else "already correct")
        print("Restart Firefox for any new user.js settings to take effect.")
        print("This permits media autoplay, but does not enable a website's next-episode switch.")
        return 0
    except (RuntimeError, OSError, configparser.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
