#!/usr/bin/env python3
"""Validated hot-reloaded application rules for the Xiaomi HID service.

No new input grab, polling daemon, shell commands, or global keyboard hooks.
A broken JSON edit keeps the previous working configuration.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import time
from evdev import ecodes
from key_layers import APP_SCOPES, SYSTEM_KEY_NAMES

LOG = logging.getLogger("xiaomi-remote-rules")
DEFAULT_PATH = Path(__file__).with_name("remote_rules.json")
INPUTS = frozenset("KEY_ENTER KEY_OK KEY_BACK KEY_HOME KEY_HOMEPAGE KEY_WWW KEY_COMPOSE KEY_GRAVE KEY_UP KEY_DOWN KEY_PLAYPAUSE KEY_VOLUMEUP KEY_VOLUMEDOWN KEY_MUTE KEY_POWER KEY_SLEEP KEY_BRIGHTNESSUP KEY_BRIGHTNESSDOWN".split())
RESERVED_SYSTEM_INPUTS = SYSTEM_KEY_NAMES
OUTPUTS = frozenset("KEY_F5 KEY_ESC KEY_LEFT KEY_RIGHT KEY_UP KEY_DOWN KEY_T KEY_W KEY_TAB KEY_D KEY_A KEY_K KEY_SPACE KEY_ENTER KEY_BACKSPACE KEY_PAGEUP KEY_PAGEDOWN KEY_HOME KEY_END".split())
MODIFIERS = frozenset("KEY_LEFTCTRL KEY_LEFTALT KEY_LEFTSHIFT".split())
SCOPES = frozenset(APP_SCOPES)
CHATGPT_ACTIONS = frozenset(("new_chat", "voice_toggle", "send"))
MAX_SIZE = 65536
# A missing file must preserve the known-working physical remote behavior.
DEFAULT_RULES = [
    {"id": "wps-ok-enter", "scope": "wps", "input": "KEY_ENTER", "tap": "KEY_F5"},
    {"id": "wps-ok", "scope": "wps", "input": "KEY_OK", "tap": "KEY_F5"},
    {"id": "wps-back", "scope": "wps", "input": "KEY_BACK", "tap": "KEY_ESC"},
    {"id": "browser-back", "scope": "browser", "input": "KEY_BACK", "shortcut": ["KEY_LEFTALT", "KEY_LEFT"], "cooldown_ms": 450},
    {"id": "browser-home", "scope": "browser", "input": "KEY_HOME", "shortcut": ["KEY_LEFTCTRL", "KEY_T"], "cooldown_ms": 500},
    {"id": "browser-homepage", "scope": "browser", "input": "KEY_HOMEPAGE", "shortcut": ["KEY_LEFTCTRL", "KEY_T"], "cooldown_ms": 500},
    {"id": "browser-www", "scope": "browser", "input": "KEY_WWW", "shortcut": ["KEY_LEFTCTRL", "KEY_T"], "cooldown_ms": 500},
    {"id": "browser-menu", "scope": "browser", "input": "KEY_COMPOSE", "shortcut": ["KEY_LEFTCTRL", "KEY_TAB"], "cooldown_ms": 450},
    {"id": "browser-tv", "scope": "browser", "input": "KEY_GRAVE", "shortcut": ["KEY_LEFTCTRL", "KEY_W"], "cooldown_ms": 800},
    # Keep the house icon consistent with browser-wide Ctrl+T on ChatGPT.
    # ChatGPT Back opens a new chat; outside ChatGPT Back keeps its old behavior.
    {"id": "chatgpt-back", "scope": "chatgpt", "input": "KEY_BACK", "action": "new_chat", "cooldown_ms": 950},
    {"id": "chatgpt-send", "scope": "chatgpt", "input": "KEY_GRAVE", "action": "send", "cooldown_ms": 1100},
]


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    scope: str
    input_code: int
    key_code: int | None
    modifier_code: int | None
    cooldown_ms: int
    action: str | None = None


def _code(name: object, allowed: frozenset[str]) -> int:
    if not isinstance(name, str) or name not in allowed:
        raise ValueError(f"key not allowed: {name!r}")
    return int(getattr(ecodes, name))


def validate(config: object) -> dict[int, tuple[Rule, ...]]:
    if not isinstance(config, dict) or set(config) != {"version", "rules"} or type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("expected {version: 1, rules: [...]}")
    items = config["rules"]
    if not isinstance(items, list) or len(items) > 64:
        raise ValueError("rules must be a list of at most 64 entries")
    mapping: dict[int, list[Rule]] = {}
    seen: set[tuple[str, int]] = set()
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not {"id", "scope", "input"} <= set(item) or not set(item) <= {"id", "scope", "input", "tap", "shortcut", "action", "cooldown_ms"}:
            raise ValueError("invalid rule fields")
        rid, scope = item["id"], item["scope"]
        if not isinstance(rid, str) or not rid or len(rid) > 64 or rid in ids:
            raise ValueError("duplicate/invalid rule id")
        ids.add(rid)
        if not isinstance(scope, str) or scope not in SCOPES:
            raise ValueError("scope must be wps, browser or chatgpt")
        input_code = _code(item["input"], INPUTS)
        if isinstance(item["input"], str) and item["input"] in RESERVED_SYSTEM_INPUTS:
            raise ValueError("system-level power, volume and brightness keys cannot be remapped by application rules")
        if scope != "wps" and input_code in (ecodes.KEY_ENTER, ecodes.KEY_OK):
            raise ValueError("browser Enter/OK would break video and text input")
        if (scope, input_code) in seen:
            raise ValueError("duplicate key in the same application")
        seen.add((scope, input_code))
        actions = int("tap" in item) + int("shortcut" in item) + int("action" in item)
        if actions != 1:
            raise ValueError("choose exactly one of tap, shortcut, action")
        action = item.get("action")
        if scope == "chatgpt":
            if not isinstance(action, str) or action not in CHATGPT_ACTIONS:
                raise ValueError("chatgpt rules must use an allowed web action")
            key = modifier = None
        elif action is not None:
            raise ValueError("web actions restricted to ChatGPT")
        elif "tap" in item:
            key = _code(item["tap"], OUTPUTS)
            modifier = None
        else:
            shortcut = item["shortcut"]
            if not isinstance(shortcut, list) or len(shortcut) != 2:
                raise ValueError("shortcut must be [modifier, key]")
            modifier = _code(shortcut[0], MODIFIERS)
            key = _code(shortcut[1], OUTPUTS)
        cooldown = item.get("cooldown_ms", 0)
        if type(cooldown) is not int or not 0 <= cooldown <= 5000:
            raise ValueError("cooldown_ms must be integer 0..5000")
        mapping.setdefault(input_code, []).append(Rule(rid, scope, input_code, key, modifier, cooldown, action))
    return {key: tuple(sorted(value, key=lambda r: {"wps": 0, "chatgpt": 1, "browser": 2}[r.scope]))
            for key, value in mapping.items()}


class RuleBook:
    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path is not None else Path(os.getenv("XIAOMI_REMOTE_RULES", str(DEFAULT_PATH)))
        self._rules = validate({"version": 1, "rules": DEFAULT_RULES})
        self._stamp: tuple[int, int] | None = None
        self._last_check = -float("inf")
        self.refresh(force=True)

    def refresh(self, *, force: bool = False) -> None:
        now = time.perf_counter()  # distinct from shortcut debounce monotonic clock
        if not force and now - self._last_check < 1.0:
            return
        self._last_check = now
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            if self._stamp is not None:
                LOG.warning("rules missing; retaining last known good configuration")
            return
        except OSError as exc:
            LOG.warning("rules stat failed; retaining old rules: %s", exc)
            return
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp == self._stamp:
            return
        try:
            if stat.st_size > MAX_SIZE:
                raise ValueError("file too large")
            raw = self.path.read_bytes()
            if len(raw) > MAX_SIZE:
                raise ValueError("file too large")
            loaded = validate(json.loads(raw.decode("utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            LOG.warning("invalid rules, retaining last known good config: %s", exc)
            return
        self._rules, self._stamp = loaded, stamp
        LOG.info("rules loaded: %d rules from %s", sum(map(len, loaded.values())), self.path)

    def candidates(self, key: int) -> tuple[Rule, ...]:
        self.refresh()
        return self._rules.get(key, ())


def check(path: Path) -> int:
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_SIZE:
            raise ValueError("file too large")
        rules = validate(json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"INVALID: {exc}")
        return 1
    print(f"VALID: {sum(map(len, rules.values()))} app-specific rules")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Check scoped Xiaomi remote rules")
    parser.add_argument("--check", type=Path, default=None)
    parser.add_argument("--defaults", action="store_true",
                        help="Emit the single source of default rules as JSON")
    args = parser.parse_args()
    if args.defaults:
        if args.check is not None:
            parser.error("--defaults cannot be combined with --check")
        print(json.dumps({"version": 1, "rules": DEFAULT_RULES}, ensure_ascii=False))
    else:
        raise SystemExit(check(args.check or DEFAULT_PATH))
