#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import urllib.request
import urllib.error
import ctypes
import logging
import re
import subprocess
import time

from evdev import InputDevice, UInput, ecodes, list_devices

from video_browser_context import (
    browser_media_tab_focused, firefox_pip_focused, toggle_browser_play_pause,
    browser_window_focused,
)

LOG = logging.getLogger('xiaomi-remote-hid-filter')
VID = 0x2717
PID = 0x32B8
FILTER_NAME = 'Xiaomi Remote 2 Pro Filtered'

# The remote has previously emitted a physical F5-like key that refreshed Chrome.
# Keep blocking that physical key everywhere. WPS F5 is synthesized only from OK.
BLOCK_KEY = ecodes.KEY_F5
OK_KEYS = {ecodes.KEY_ENTER, ecodes.KEY_OK}
BACK_KEYS = {ecodes.KEY_BACK}
# Xiaomi remote exposes KEY_HOME and KEY_WWW in its physical HID map;
# firmware variants can use either for the house-shaped Home/browser key.
# Some other keyboards use KEY_HOMEPAGE. All stay untouched outside browsers.
HOME_KEYS = {ecodes.KEY_HOME, ecodes.KEY_HOMEPAGE, ecodes.KEY_WWW}
# Xiaomi RC003 TV key is HID Keyboard usage 0x35 (= grave/tilde
# on a US keyboard), reported as Linux KEY_GRAVE (41). It is NOT
# KEY_TV, which is absent from this RC003 device capability list.
# The device VID/PID filter keeps the PC keyboard unaffected.
TV_KEYS = {ecodes.KEY_GRAVE}
CLOSE_TAB_KEYS = HOME_KEYS | TV_KEYS
# Standard HID keyboard Application/Menu key (usage 0x65), advertised
# as KEY_COMPOSE by this RC003 keyboard. Do not remap unrelated keys.
MENU_KEYS = {ecodes.KEY_COMPOSE}

# Single speed engine: Firefox/Chrome Global Speed extension.
# ONLY the remote round D-pad UP/DOWN is remapped to the extension's
# keyboard shortcuts. KEY_VOLUMEUP / KEY_VOLUMEDOWN are deliberately
# untouched, so the Xiaomi's physical volume keys (and headphones)
# still control sound.
VIDEO_RATE_KEYS = {
    ecodes.KEY_UP: ecodes.KEY_D,        # Global Speed +0.1x
    ecodes.KEY_DOWN: ecodes.KEY_A,      # Global Speed -0.1x
}

# The ordinary web video shortcut never uses this endpoint.
# Only Firefox native PiP can route keys back to the original Global Speed
# content script, and only while userscript v0.5+ is actively connected.
PIP_GLOBAL_SPEED_ENDPOINT = "http://127.0.0.1:18766/video/emit"


def route_firefox_pip_to_global_speed(key_code: int) -> bool:
    kind = {
        ecodes.KEY_UP: "speed_up",
        ecodes.KEY_DOWN: "speed_down",
    }.get(key_code)
    if not kind:
        return False
    payload = json.dumps({
        "browser": "firefox", "pip": True, "type": kind,
    }).encode("utf-8")
    req = urllib.request.Request(
        PIP_GLOBAL_SPEED_ENDPOINT, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=0.35) as response:
            return bool(json.load(response).get("ok"))
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return False


WPS_RESUME_WINDOW_SECONDS = 15.0


def find_wps_top_window() -> str | None:
    tree = _run('xwininfo', '-root', '-tree')
    for line in tree.splitlines():
        low = line.lower()
        if 'wps office' in low and 'wpsoffice' in low:
            match = re.search(r'0x[0-9a-fA-F]+', line)
            if match:
                return match.group(0)
    return None


def activate_x11_window(wid: str) -> bool:
    try:
        x11 = ctypes.CDLL('libX11.so.6')
        xtst = ctypes.CDLL('libXtst.so.6')

        class XWindowAttributes(ctypes.Structure):
            _fields_ = [
                ('x', ctypes.c_int), ('y', ctypes.c_int),
                ('width', ctypes.c_int), ('height', ctypes.c_int),
                ('border_width', ctypes.c_int), ('depth', ctypes.c_int),
                ('visual', ctypes.c_void_p), ('root', ctypes.c_ulong),
                ('class_', ctypes.c_int), ('bit_gravity', ctypes.c_int),
                ('win_gravity', ctypes.c_int), ('backing_store', ctypes.c_int),
                ('backing_planes', ctypes.c_ulong), ('backing_pixel', ctypes.c_ulong),
                ('save_under', ctypes.c_int), ('colormap', ctypes.c_ulong),
                ('map_installed', ctypes.c_int), ('map_state', ctypes.c_int),
                ('all_event_masks', ctypes.c_long),
                ('your_event_mask', ctypes.c_long),
                ('do_not_propagate_mask', ctypes.c_long),
                ('override_redirect', ctypes.c_int),
                ('screen', ctypes.c_void_p),
            ]

        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XGetWindowAttributes.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XWindowAttributes)
        ]
        x11.XGetWindowAttributes.restype = ctypes.c_int
        x11.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong),
        ]
        x11.XTranslateCoordinates.restype = ctypes.c_int
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        x11.XQueryPointer.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
        ]
        x11.XQueryPointer.restype = ctypes.c_int
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

        xtst.XTestFakeMotionEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong
        ]
        xtst.XTestFakeMotionEvent.restype = ctypes.c_int
        xtst.XTestFakeButtonEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong
        ]
        xtst.XTestFakeButtonEvent.restype = ctypes.c_int

        dpy = x11.XOpenDisplay(None)
        if not dpy:
            return False

        try:
            win = int(wid, 16)
            root = x11.XDefaultRootWindow(dpy)

            attrs = XWindowAttributes()
            if not x11.XGetWindowAttributes(dpy, win, ctypes.byref(attrs)):
                return False

            abs_x = ctypes.c_int()
            abs_y = ctypes.c_int()
            child = ctypes.c_ulong()
            if not x11.XTranslateCoordinates(
                dpy, win, root, 0, 0,
                ctypes.byref(abs_x), ctypes.byref(abs_y), ctypes.byref(child)
            ):
                return False

            # Save current pointer position.
            root_ret = ctypes.c_ulong()
            child_ret = ctypes.c_ulong()
            old_x = ctypes.c_int()
            old_y = ctypes.c_int()
            win_x = ctypes.c_int()
            win_y = ctypes.c_int()
            mask = ctypes.c_uint()
            x11.XQueryPointer(
                dpy, root,
                ctypes.byref(root_ret), ctypes.byref(child_ret),
                ctypes.byref(old_x), ctypes.byref(old_y),
                ctypes.byref(win_x), ctypes.byref(win_y),
                ctypes.byref(mask),
            )

            # Click the title-bar area. This gives Mutter a real user-like
            # activation event, unlike _NET_ACTIVE_WINDOW under Wayland.
            click_x = abs_x.value + min(max(attrs.width // 3, 180), max(attrs.width - 40, 40))
            click_y = abs_y.value + 18

            xtst.XTestFakeMotionEvent(dpy, -1, click_x, click_y, 0)
            xtst.XTestFakeButtonEvent(dpy, 1, 1, 0)
            xtst.XTestFakeButtonEvent(dpy, 1, 0, 0)
            x11.XFlush(dpy)
            time.sleep(0.08)

            # Restore the pointer so the workaround is almost invisible.
            xtst.XTestFakeMotionEvent(dpy, -1, old_x.value, old_y.value, 0)
            x11.XFlush(dpy)
            return True
        finally:
            x11.XCloseDisplay(dpy)
    except Exception:
        LOG.exception('failed to click-focus WPS window %s', wid)
        return False


def ensure_wps_editor_focus() -> bool:
    wid = find_wps_top_window()
    if not wid:
        return False
    ok = activate_x11_window(wid)
    if ok:
        time.sleep(0.12)
    return ok


def _run(*args: str) -> str:
    try:
        p = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=0.8,
            check=False,
        )
        return p.stdout or ''
    except Exception:
        return ''


def wps_presentation_is_focused() -> bool:
    root = _run('xprop', '-root', '_NET_ACTIVE_WINDOW')
    match = re.search(r'0x[0-9a-fA-F]+', root)
    if not match or match.group(0) == '0x0':
        return False

    wid = match.group(0)
    props = _run('xprop', '-id', wid, 'WM_CLASS', '_NET_WM_NAME', 'WM_NAME')
    p = props.lower()

    if re.search(r'wm_class.*"wpp"', p):
        return True

    if 'wpsoffice' in p and (
        re.search(r'\.(ppt|pptx|dps)(?:\s|\*|\-|")', p)
        or 'wps 演示' in props
        or 'wps presentation' in p
    ):
        return True

    # WPS can expose a generic wpsoffice top-level window with a wpp child.
    if 'wpsoffice' in p:
        tree = _run('xwininfo', '-id', wid, '-tree').lower()
        if re.search(r'\("wpp"\s+"wpp"\)', tree):
            return True

    return False


def find_remote() -> InputDevice | None:
    for path in list_devices():
        try:
            d = InputDevice(path)
            if d.name == FILTER_NAME:
                d.close()
                continue
            if d.info.vendor == VID and d.info.product == PID:
                return d
            d.close()
        except Exception:
            continue
    return None


async def forward_device(dev: InputDevice) -> None:
    ui = UInput.from_device(
        dev,
        name=FILTER_NAME,
        bustype=dev.info.bustype,
        vendor=VID,
        product=PID,
        version=dev.info.version,
        phys='xiaomi-remote-filter',
    )
    blocked = 0
    mapped_down: dict[int, int] = {}
    swallowed_ok: set[int] = set()
    swallowed_close_tab: set[int] = set()
    swallowed_menu: set[int] = set()
    swallowed_browser_back: set[int] = set()
    # The remote advertises both KEY_HOME and KEY_WWW. Guard against
    # firmware emitting both for the same physical press.
    last_home_close_at = -float('inf')
    wps_resume_until = 0.0

    try:
        dev.grab()
        LOG.info(
            'grabbed %s %s vendor=%04x product=%04x; '
            'physical F5 blocked; WPS OK->F5 BACK->ESC; browser Home/TV->Ctrl+W MENU->Ctrl+Tab BACK->Ctrl+T; Global Speed D/A + PiP helper; physical volume untouched; OK->PlayPause',
            dev.path, dev.name, VID, PID,
        )

        async for ev in dev.async_read_loop():
            if ev.type == ecodes.EV_KEY:
                # Preserve the browser-refresh protection already in use.
                if ev.code == BLOCK_KEY:
                    blocked += 1
                    LOG.info(
                        'blocked physical KEY_F5 value=%s count=%s',
                        ev.value, blocked,
                    )
                    continue

                if ev.code in MENU_KEYS:
                    # Browser next-tab shortcut, independent of video/MPRIS.
                    # SYN after press and release makes this a single short
                    # Ctrl+Tab, never a held modifier. Consume repeats and
                    # physical release, even after browser focus changes.
                    # Non-browser apps receive the physical Menu unchanged.
                    if ev.code in swallowed_menu:
                        if ev.value == 0:
                            swallowed_menu.remove(ev.code)
                        continue
                    if ev.value == 1 and await asyncio.to_thread(browser_window_focused):
                        swallowed_menu.add(ev.code)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_TAB, 1)
                        ui.syn()
                        ui.write(ecodes.EV_KEY, ecodes.KEY_TAB, 0)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
                        ui.syn()
                        LOG.info("browser Menu %s -> Ctrl+Tab (next tab)",
                                 ecodes.KEY[ev.code])
                        continue

                if ev.code in BACK_KEYS:
                    # Browser Back opens a fresh tab (Ctrl+T), instead of
                    # navigating backwards. This must precede the WPS
                    # Back->Esc branch, which remains in place for WPS.
                    # Consume repeat and release even if focus changes after
                    # the new tab appears. Always release Ctrl immediately.
                    if ev.code in swallowed_browser_back:
                        if ev.value == 0:
                            swallowed_browser_back.remove(ev.code)
                        continue
                    if ev.value == 1 and await asyncio.to_thread(browser_window_focused):
                        swallowed_browser_back.add(ev.code)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_T, 1)
                        ui.syn()
                        ui.write(ecodes.EV_KEY, ecodes.KEY_T, 0)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
                        ui.syn()
                        LOG.info("browser Back %s -> Ctrl+T (new tab)",
                                 ecodes.KEY[ev.code])
                        continue
                    # Non-browser Back: use existing WPS Esc or original key.

                if ev.code in CLOSE_TAB_KEYS:
                    # Home and TV close one *foreground browser tab* via the
                    # exact same Ctrl+W shortcut. Keep both physical keys
                    # unchanged outside supported browser windows. Always
                    # release Ctrl+W before focus can change and suppress
                    # repeat/up events, so holding the remote never closes
                    # more than one tab or leaves Ctrl stuck.
                    if ev.code in swallowed_close_tab:
                        if ev.value == 0:
                            swallowed_close_tab.remove(ev.code)
                        continue
                    if ev.value == 1 and await asyncio.to_thread(browser_window_focused):
                        swallowed_close_tab.add(ev.code)
                        if ev.code in HOME_KEYS:
                            # HOME and WWW can both fire for one physical
                            # press. Deduplicate only those two variants,
                            # not independently pressed TV and Home buttons.
                            now = time.monotonic()
                            if now - last_home_close_at < 0.18:
                                LOG.info("browser Home duplicate suppressed: %s",
                                         ecodes.KEY[ev.code])
                                continue
                            last_home_close_at = now
                        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_W, 1)
                        ui.syn()
                        ui.write(ecodes.EV_KEY, ecodes.KEY_W, 0)
                        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
                        ui.syn()
                        label = "TV" if ev.code in TV_KEYS else "Home"
                        LOG.info("browser %s %s -> Ctrl+W (close current tab)",
                                 label, ecodes.KEY[ev.code])
                        continue
                    # Non-browser: pass original TV/Home key unchanged.

                if ev.code in VIDEO_RATE_KEYS:
                    # ONLY Firefox native PiP: request a Global Speed
                    # KeyD/KeyA dispatch on the ORIGINAL PAGE. No window
                    # switching and no direct playbackRate modification.
                    # If the helper is absent, pass the physical key through
                    # and do not disturb normal playback/window focus.
                    if ev.value == 1 and await asyncio.to_thread(firefox_pip_focused):
                        if await asyncio.to_thread(route_firefox_pip_to_global_speed, ev.code):
                            mapped_down[ev.code] = 0
                            LOG.info("Firefox PiP Global Speed keyboard request %s",
                                     ecodes.KEY[ev.code])
                            continue
                        LOG.warning(
                            "Firefox PiP Global Speed helper v0.5 not connected "
                            "or no playing video: %s", ecodes.KEY[ev.code],
                        )
                        # Keep original PiP navigation if helper is absent.
                        # Never fall through into the ordinary D/A mapping.
                        ui.write_event(ev)
                        continue
                    # Decide once on key-down. The matching key-up/repeat
                    # stays mapped even if window focus changes meanwhile.
                    if ev.value == 1 and await asyncio.to_thread(browser_media_tab_focused):
                        target=VIDEO_RATE_KEYS[ev.code]
                        mapped_down[ev.code]=target
                        ui.write(ecodes.EV_KEY,target,1)
                        LOG.info("Global Speed mapped %s -> %s",
                                 ecodes.KEY[ev.code],ecodes.KEY[target])
                        continue
                    if ev.code in mapped_down:
                        target=mapped_down[ev.code]
                        if ev.value == 2:
                            if target:
                                ui.write(ecodes.EV_KEY,target,2)
                            continue
                        if ev.value == 0:
                            if target:
                                ui.write(ecodes.EV_KEY,target,0)
                            del mapped_down[ev.code]
                            continue

                if ev.code in OK_KEYS:
                    # A successful MPRIS PlayPause call acts on the *foreground*
                    # media tab. Swallow the physical down/repeat/up sequence to
                    # avoid double toggles, while preserving WPS F5 elsewhere.
                    if ev.code in swallowed_ok:
                        if ev.value == 0:
                            swallowed_ok.remove(ev.code)
                        continue
                    if ev.value == 1 and await asyncio.to_thread(toggle_browser_play_pause):
                        swallowed_ok.add(ev.code)
                        LOG.info("browser video OK -> PlayPause via MPRIS")
                        continue

                if ev.code in OK_KEYS or ev.code in BACK_KEYS:
                    target = ecodes.KEY_F5 if ev.code in OK_KEYS else ecodes.KEY_ESC

                    focused = wps_presentation_is_focused()
                    resume_context = (
                        ev.code in OK_KEYS
                        and time.monotonic() < wps_resume_until
                    )

                    # After leaving slideshow, WPS/XWayland can temporarily focus a
                    # 1x1 helper window. In that specific resume context, reactivate
                    # the real WPS top-level window before sending F5.
                    if ev.value == 1 and (focused or resume_context):
                        if ev.code in OK_KEYS:
                            if resume_context or focused:
                                ensure_wps_editor_focus()
                            wps_resume_until = 0.0
                        else:
                            wps_resume_until = time.monotonic() + WPS_RESUME_WINDOW_SECONDS

                        mapped_down[ev.code] = target
                        ui.write(ecodes.EV_KEY, target, 1)
                        LOG.info(
                            'mapped %s down -> %s (WPS focused=%s resume=%s)',
                            ecodes.KEY[ev.code],
                            ecodes.KEY[target],
                            focused,
                            resume_context,
                        )
                        continue

                    # Repeat/release must follow the decision made on key down,
                    # even if focus changes while the key is held.
                    if ev.code in mapped_down:
                        mapped_target = mapped_down[ev.code]
                        if ev.value == 2:
                            ui.write(ecodes.EV_KEY, mapped_target, 2)
                            continue
                        if ev.value == 0:
                            ui.write(ecodes.EV_KEY, mapped_target, 0)
                            del mapped_down[ev.code]
                            LOG.info(
                                'mapped %s up -> %s',
                                ecodes.KEY[ev.code],
                                ecodes.KEY[mapped_target],
                            )
                            continue

            # Everything else remains unchanged.
            ui.write_event(ev)
    finally:
        try:
            dev.ungrab()
        except Exception:
            pass
        ui.close()
        dev.close()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )
    while True:
        dev = find_remote()
        if not dev:
            LOG.warning('remote not found or permission denied; retrying')
            await asyncio.sleep(2)
            continue
        try:
            await forward_device(dev)
        except PermissionError as exc:
            LOG.error('permission denied: %s', exc)
            await asyncio.sleep(3)
        except OSError as exc:
            LOG.warning('remote disconnected or input reset: %s', exc)
            await asyncio.sleep(1)
        except Exception:
            LOG.exception('filter loop failed')
            await asyncio.sleep(2)


if __name__ == '__main__':
    asyncio.run(main())
