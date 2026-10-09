#!/usr/bin/env python3
"""Safe Xiaomi RC003 browser-video and tab remote.

The old all-purpose HID filter is deliberately NOT used. This service handles
video playback and three browser-only tab shortcuts; all other remote keys
(notably Enter) pass through with their original down/repeat/up sequence.
The PC keyboard is never opened or grabbed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request

from evdev import InputDevice, UInput, ecodes, list_devices

from video_browser_context import (
    browser_window_focused,
    browser_media_tab_focused,
    firefox_pip_focused,
    toggle_browser_play_pause,
    youtube_video_tab_focused,
)

LOG = logging.getLogger("xiaomi-remote-video-only")
VID = 0x2717
PID = 0x32B8
VIRTUAL_NAME = "Xiaomi Remote Video Only"
SPEED_KEYS = {ecodes.KEY_UP: ecodes.KEY_D, ecodes.KEY_DOWN: ecodes.KEY_A}
OK_KEYS = {ecodes.KEY_ENTER, ecodes.KEY_OK}
# Xiaomi RC003 house: HOME/WWW (occasionally reported together); TV: GRAVE;
# three-line menu: COMPOSE. These are remapped ONLY if a browser has focus.
HOME_KEYS = {ecodes.KEY_HOME, ecodes.KEY_HOMEPAGE, ecodes.KEY_WWW}
BROWSER_TAB_KEYS = {
    **{key: ecodes.KEY_T for key in HOME_KEYS},
    ecodes.KEY_COMPOSE: ecodes.KEY_TAB,
    ecodes.KEY_GRAVE: ecodes.KEY_W,
}
PIP_ENDPOINT = "http://127.0.0.1:18766/video/emit"


def find_remote() -> InputDevice | None:
    """Only use the original Xiaomi HID, never a virtual/other keyboard."""
    for path in list_devices():
        try:
            device = InputDevice(path)
            if device.name == VIRTUAL_NAME:
                device.close()
                continue
            if (device.info.vendor, device.info.product) == (VID, PID):
                return device
            device.close()
        except OSError:
            continue
    return None


def pip_global_speed(key: int) -> bool:
    """Ask the existing Firefox PiP helper to forward Global Speed D/A."""
    event_type = {
        ecodes.KEY_UP: "speed_up",
        ecodes.KEY_DOWN: "speed_down",
    }.get(key)
    if not event_type:
        return False
    request = urllib.request.Request(
        PIP_ENDPOINT,
        method="POST",
        data=json.dumps({
            "browser": "firefox",
            "pip": True,
            "type": event_type,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=0.35) as response:
            return bool(json.load(response).get("ok"))
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return False


def tap(ui: UInput, key: int) -> None:
    """Complete a keypress before application focus can change."""
    ui.write(ecodes.EV_KEY, key, 1)
    ui.syn()
    ui.write(ecodes.EV_KEY, key, 0)
    ui.syn()

def ctrl_tap(ui: UInput, key: int) -> None:
    """Single complete Ctrl+key, with no modifier held across window changes."""
    ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
    ui.write(ecodes.EV_KEY, key, 1)
    ui.syn()
    ui.write(ecodes.EV_KEY, key, 0)
    ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
    ui.syn()


async def forward_device(device: InputDevice) -> None:
    ui = UInput.from_device(
        device,
        name=VIRTUAL_NAME,
        bustype=device.info.bustype,
        vendor=VID,
        product=PID,
        version=device.info.version,
        phys="xiaomi-video-only",
    )
    video_held: set[int] = set()
    ok_held: set[int] = set()
    browser_tab_held: set[int] = set()
    last_home_tab_at = -float("inf")
    try:
        device.grab()
        LOG.info("safe video/browser filter grabbed %s %s; Enter untouched",
                 device.path, device.name)
        async for event in device.async_read_loop():
            if event.type != ecodes.EV_KEY:
                ui.write_event(event)
                continue

            code, value = event.code, event.value

            # Decide on physical down; swallow its matching repeat and
            # release even if the Ctrl shortcut changes focus. This prevents
            # stray tab switches/closes in unrelated applications.
            if code in browser_tab_held:
                if value == 0:
                    browser_tab_held.discard(code)
                continue
            if (code in BROWSER_TAB_KEYS and value == 1
                    and await asyncio.to_thread(browser_window_focused)):
                browser_tab_held.add(code)
                if code in HOME_KEYS:
                    # Some firmware sends HOME and WWW for the same press.
                    now = time.monotonic()
                    if now - last_home_tab_at < 0.18:
                        LOG.info("duplicate browser Home suppressed: %s",
                                 ecodes.KEY[code])
                        continue
                    last_home_tab_at = now
                target = BROWSER_TAB_KEYS[code]
                ctrl_tap(ui, target)
                LOG.info("browser tab: %s -> Ctrl+%s",
                         ecodes.KEY[code], ecodes.KEY[target])
                continue

            if code in video_held:
                if value == 0:
                    video_held.discard(code)
                # The speed/PiP action was completed at initial key-down.
                continue
            if code in SPEED_KEYS and value == 1:
                if await asyncio.to_thread(firefox_pip_focused):
                    if await asyncio.to_thread(pip_global_speed, code):
                        video_held.add(code)
                        LOG.info("Firefox PiP Global Speed %s", ecodes.KEY[code])
                        continue
                    # PiP without a live helper must keep its original arrows.
                elif await asyncio.to_thread(browser_media_tab_focused):
                    video_held.add(code)
                    tap(ui, SPEED_KEYS[code])
                    LOG.info("browser Global Speed %s -> %s",
                             ecodes.KEY[code], ecodes.KEY[SPEED_KEYS[code]])
                    continue

            if code in ok_held:
                if value == 0:
                    ok_held.discard(code)
                continue
            if code in OK_KEYS and value == 1:
                if await asyncio.to_thread(toggle_browser_play_pause):
                    ok_held.add(code)
                    LOG.info("video OK -> MPRIS PlayPause")
                    continue
                if await asyncio.to_thread(youtube_video_tab_focused):
                    ok_held.add(code)
                    tap(ui, ecodes.KEY_K)
                    LOG.info("YouTube video OK -> K PlayPause")
                    continue
                # Important: normal Enter is never synthesized, swallowed,
                # debounced, or remapped. Its physical sequence passes below.

            ui.write_event(event)
    finally:
        try:
            device.ungrab()
        except OSError:
            pass
        ui.close()
        device.close()


async def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    while True:
        device = find_remote()
        if device is None:
            LOG.warning("Xiaomi remote not found; retrying")
            await asyncio.sleep(3)
            continue
        try:
            await forward_device(device)
        except (PermissionError, OSError) as exc:
            LOG.warning("remote disconnected/unavailable: %s", exc)
            await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
