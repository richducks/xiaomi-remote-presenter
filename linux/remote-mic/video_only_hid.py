#!/usr/bin/env python3
"""Safe Xiaomi RC003 browser-video and tab remote.

The old all-purpose HID filter is deliberately NOT used. This one service
handles video playback, browser shortcuts, and WPS Presentation keys. Normal
Enter still passes through with its original down/repeat/up sequence.
The PC keyboard is never opened or grabbed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from time import sleep as key_sleep

from evdev import InputDevice, UInput, ecodes, list_devices

from remote_rules import RuleBook
from key_layers import SYSTEM_KEY_CODES, is_system_key
from wps_focus_recovery import (
    WPS_RESUME_SECONDS, ensure_wps_editor_focus, safe_to_resume_wps,
)

from video_browser_context import (
    browser_window_focused,
    wps_presentation_focused,
    browser_media_tab_focused,
    firefox_pip_focused,
    toggle_browser_play_pause,
    youtube_video_tab_focused,
)

LOG = logging.getLogger("xiaomi-remote-video-only")
VID = 0x2717
PID = 0x32B8
VIRTUAL_NAME = "Xiaomi Remote Video Only"
# Never grab another remapper's virtual output.
VIRTUAL_DEVICE_NAMES = {VIRTUAL_NAME, "Xiaomi Remote 2 Pro Filtered"}
SPEED_KEYS = {ecodes.KEY_UP: ecodes.KEY_D, ecodes.KEY_DOWN: ecodes.KEY_A}
# System power, volume, brightness and sleep keys have higher authority than
# all applications. Preserve the physical down/repeat/up sequence; never
# synthesize OS shutdown or volume changes in the application remapper.
SYSTEM_VOLUME_KEYS = SYSTEM_KEY_CODES  # retained alias for prior regression tests
OK_KEYS = {ecodes.KEY_ENTER, ecodes.KEY_OK}
BACK_KEYS = {ecodes.KEY_BACK}
BLOCK_PHYSICAL_F5 = ecodes.KEY_F5  # Prevent RC003 microphone-key browser refresh.
# Xiaomi RC003 house: HOME/WWW (occasionally reported together); TV: GRAVE;
# three-line menu: COMPOSE. These are remapped ONLY if a browser has focus.
HOME_KEYS = {ecodes.KEY_HOME, ecodes.KEY_HOMEPAGE, ecodes.KEY_WWW}
BROWSER_TAB_KEYS = {
    **{key: ecodes.KEY_T for key in HOME_KEYS},
    ecodes.KEY_COMPOSE: ecodes.KEY_TAB,
    ecodes.KEY_GRAVE: ecodes.KEY_W,
}
# Some RC003 firmwares emit complete down/up pairs repeatedly during one
# physical press. A held-key set cannot catch those short pairs. Rate-limit
# browser-only shortcuts so a noisy button cannot switch/close many tabs.
# The close shortcut has the longest guard because it can discard work.
BROWSER_SHORTCUT_COOLDOWNS = {
    ecodes.KEY_T: 0.50,
    ecodes.KEY_TAB: 0.45,
    ecodes.KEY_W: 0.80,
    ecodes.KEY_LEFT: 0.45,
}
PIP_ENDPOINT = "http://127.0.0.1:18766/video/emit"
CHATGPT_ACTIVE = "http://127.0.0.1:18766/chatgpt/active"
CHATGPT_DRAFT_READY = "http://127.0.0.1:18766/chatgpt/draft-ready"
CHATGPT_TRIGGER = "http://127.0.0.1:18766/chatgpt/trigger"
WECHAT_DRAFT_READY = "http://127.0.0.1:18766/wechat/draft-ready"
WECHAT_SEND = "http://127.0.0.1:18766/wechat/send"


def chatgpt_window_focused(*, browser_already_confirmed: bool = False) -> bool:
    """Require compositor-confirmed browser AND live foreground JS tab.

    The event loop caches browser focus for a single physical key event.
    Rechecking it mid-routing can change the branch while focus is switching.
    """
    if not browser_already_confirmed and not browser_window_focused():
        return False
    try:
        with urllib.request.urlopen(CHATGPT_ACTIVE, timeout=0.22) as reply:
            return json.load(reply).get("active") is True
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return False


def chatgpt_draft_ready() -> bool:
    """Intercept remote OK only for a focused ChatGPT draft awaiting review."""
    if not browser_window_focused():
        return False
    try:
        with urllib.request.urlopen(CHATGPT_DRAFT_READY, timeout=0.22) as reply:
            return json.load(reply).get("ready") is True
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return False


def emit_chatgpt_action(action: str) -> bool:
    """Queue action to focused ChatGPT page; never inject system Enter."""
    if action not in ("new_chat", "voice_toggle", "send"):
        return False
    request = urllib.request.Request(
        CHATGPT_TRIGGER,
        data=json.dumps({"action": action}).encode(),
        headers={"Content-Type": "application/json", "X-Xiaomi-Remote-HID": "1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=0.3) as reply:
            return json.load(reply).get("ok") is True
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return False



def wechat_draft_state() -> tuple[bool, bool]:
    """Return (ready, busy). An early OK must not send an old draft."""
    try:
        with urllib.request.urlopen(WECHAT_DRAFT_READY, timeout=0.35) as reply:
            data = json.load(reply)
            return data.get('ready') is True, data.get('busy') is True
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return False, False


def send_wechat_draft() -> bool:
    request = urllib.request.Request(
        WECHAT_SEND, data=b'{}', method='POST',
        headers={'Content-Type': 'application/json',
                 'X-Xiaomi-Remote-HID': '1'},
    )
    try:
        with urllib.request.urlopen(request, timeout=0.7) as reply:
            return json.load(reply).get('ok') is True
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return False


def find_remote() -> InputDevice | None:
    """Only use the original Xiaomi HID, never a virtual/other keyboard."""
    for path in list_devices():
        try:
            device = InputDevice(path)
            if device.name in VIRTUAL_DEVICE_NAMES:
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
    # A zero-duration tap is occasionally missed by GNOME/Firefox under
    # load. Hold only synthesized remote actions, never physical Enter.
    key_sleep(0.035)
    ui.write(ecodes.EV_KEY, key, 0)
    ui.syn()

def modified_tap(ui: UInput, modifier: int, key: int) -> None:
    """Balanced shortcut, releasing the modifier before focus changes."""
    ui.write(ecodes.EV_KEY, modifier, 1)
    ui.write(ecodes.EV_KEY, key, 1)
    ui.syn()
    # Empirical GNOME/Firefox verification succeeded with ~60ms held
    # Ctrl+Tab. The prior immediate release had no dwell at all.
    key_sleep(0.060)
    ui.write(ecodes.EV_KEY, key, 0)
    ui.write(ecodes.EV_KEY, modifier, 0)
    ui.syn()


def ctrl_tap(ui: UInput, key: int) -> None:
    modified_tap(ui, ecodes.KEY_LEFTCTRL, key)


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
    last_ok_submit_at = -float("inf")
    # Exactly one owning evdev grab; app-scoped rules are interpreted here.
    rules = RuleBook()
    rule_held: set[int] = set()
    last_rule_at: dict[tuple[str, int | None, int], float] = {}
    last_passthrough_log_at: dict[int, float] = {}
    # A WPS Back->Esc can destroy the slideshow XWayland window while the
    # editor remains open but no longer accepts synthetic F5 until activated.
    wps_resume_until = 0.0
    wps_editor_repair_pending = False
    try:
        device.grab()
        LOG.info("unified safe filter grabbed %s %s; ordinary Enter untouched",
                 device.path, device.name)
        async for event in device.async_read_loop():
            if event.type != ecodes.EV_KEY:
                ui.write_event(event)
                continue

            code, value = event.code, event.value

            # A legacy RC003 microphone key generates F5. Never forward a
            # physical F5 that could refresh a form or lose typed text.
            if code == BLOCK_PHYSICAL_F5:
                continue

            # Power, volume and brightness belong to Ubuntu regardless of the
            # foreground app. Do not run app rules or video probes.
            if is_system_key(code):
                ui.write_event(event)
                continue

            # Consume matching up/repeat even after the shortcut switches
            # focus. NEVER create unpaired Ctrl/Alt or a stray physical Enter.
            if code in rule_held:
                if value == 0:
                    rule_held.discard(code)
                continue
            if value == 1:
                selected = None
                wps_needs_recovery = False
                wps_is_focused = False
                browser_is_focused = None  # cache within one key-down only
                for rule in rules.candidates(code):
                    if rule.scope == "wps":
                        wps_is_focused = await asyncio.to_thread(wps_presentation_focused)
                        # A previous WPS Back (Esc) explicitly arms a brief
                        # recovery window. Never reactivate WPS from a browser,
                        # other application, or without that prior WPS Back.
                        wps_needs_recovery = (
                            code in OK_KEYS and (
                                (wps_editor_repair_pending and wps_is_focused)
                                or time.monotonic() < wps_resume_until
                            )
                        )
                        safe_resume = (
                            wps_needs_recovery and
                            time.monotonic() < wps_resume_until and
                            await asyncio.to_thread(safe_to_resume_wps)
                        )
                        if wps_is_focused or safe_resume:
                            selected = rule
                            break
                        continue
                    if browser_is_focused is None:
                        browser_is_focused = await asyncio.to_thread(
                            browser_window_focused)
                    if not browser_is_focused:
                        continue
                    if rule.scope == "browser" or (
                        rule.scope == "chatgpt" and
                        await asyncio.to_thread(
                            chatgpt_window_focused,
                            browser_already_confirmed=True)
                    ):
                        selected = rule
                        break
                if selected is not None:
                    rule_held.add(code)
                    ident = (selected.scope, selected.modifier_code,
                             selected.key_code, selected.action)
                    now = time.monotonic()
                    if now - last_rule_at.get(ident, -float("inf")) >= selected.cooldown_ms / 1000.0:
                        last_rule_at[ident] = now
                        if selected.scope == "wps":
                            if code in BACK_KEYS:
                                wps_resume_until = now + WPS_RESUME_SECONDS
                                # After the short desktop-helper window expires,
                                # still repair WPS when it actually has focus.
                                # Never use this flag to steal focus from a browser.
                                wps_editor_repair_pending = True
                                LOG.info("WPS Esc: recovery armed for %.1fs", WPS_RESUME_SECONDS)
                            elif wps_needs_recovery:
                                # XWayland editor sometimes loses focus after
                                # closing the slideshow. Restore the editor
                                # before sending F5, only on this explicit OK.
                                restored = await asyncio.to_thread(ensure_wps_editor_focus)
                                LOG.info("WPS resume focus restored=%s", restored)
                                if not restored and not (
                                    wps_is_focused and
                                    await asyncio.to_thread(wps_presentation_focused)
                                ):
                                    LOG.warning("WPS resume cancelled: no safe editor window")
                                    continue
                                wps_resume_until = 0.0
                                wps_editor_repair_pending = False
                        if selected.action:
                            ok = await asyncio.to_thread(emit_chatgpt_action,
                                                         selected.action)
                            LOG.info("remote action %s queued=%s", selected.action, ok)
                        elif selected.modifier_code is None:
                            tap(ui, selected.key_code)
                        else:
                            modified_tap(ui, selected.modifier_code,
                                         selected.key_code)
                        LOG.info("remote rule %s applied in %s",
                                 selected.id, selected.scope)
                    else:
                        LOG.debug("remote rule %s bounced; ignored", selected.id)
                    continue

            # Only navigation key names, never text, in diagnostics.
            if code in BROWSER_TAB_KEYS and value == 1:
                now = time.monotonic()
                if now - last_passthrough_log_at.get(code, -float('inf')) > 10:
                    last_passthrough_log_at[code] = now
                    LOG.info("remote navigation %s pass-through: browser not confirmed",
                             ecodes.KEY[code])

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
                # WeChat's transcribed text stays visible until user OK.
                wechat_ready, wechat_busy = await asyncio.to_thread(wechat_draft_state)
                if wechat_ready or wechat_busy:
                    ok_held.add(code)
                    now = time.monotonic()
                    if wechat_ready and now - last_ok_submit_at >= 0.9:
                        last_ok_submit_at = now
                        sent = await asyncio.to_thread(send_wechat_draft)
                        LOG.info('WeChat OK send=%s', sent)
                    continue
                # In ChatGPT a reviewed, nonempty draft requires a manual OK.
                # Elsewhere preserve WPS, video and native Enter handling.
                if await asyncio.to_thread(chatgpt_draft_ready):
                    ok_held.add(code)
                    now = time.monotonic()
                    if now-last_ok_submit_at >= 0.9:
                        last_ok_submit_at=now
                        queued=await asyncio.to_thread(emit_chatgpt_action,"send")
                        LOG.info("remote OK reviewed draft submit queued=%s",queued)
                    continue
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
        except Exception:
            LOG.exception("input filter failed; reconnecting")
            await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
