"""RC003 input authority boundaries; one small shared policy, no runtime daemon.

Priority: system keys always pass to Linux, BLE microphone handled by voice
service, other keys can be scoped to foreground app, then pass through.
Power events only reach the OS when real HID reports carry recognized usages.
No application / UI can bind or synthesize them as custom actions.
"""
from __future__ import annotations
from evdev import ecodes

SYSTEM_KEY_NAMES = frozenset({
    "KEY_POWER", "KEY_SLEEP", "KEY_VOLUMEUP", "KEY_VOLUMEDOWN",
    "KEY_MUTE", "KEY_BRIGHTNESSUP", "KEY_BRIGHTNESSDOWN",
})
SYSTEM_KEY_CODES = frozenset(getattr(ecodes, n) for n in SYSTEM_KEY_NAMES)
# Microphone recording is controlled by a separate BLE ATVV service, never
# by the keyboard binding layer or by the system-level key handler.
APP_SCOPES = ("wps", "chatgpt", "browser")


def is_system_key(code: int) -> bool:
    return code in SYSTEM_KEY_CODES
