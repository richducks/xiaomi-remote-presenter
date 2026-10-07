#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import re
import subprocess
import time

from evdev import InputDevice, UInput, ecodes, list_devices

LOG = logging.getLogger("xiaomi-remote-wps")

VID = int(os.getenv("XIAOMI_REMOTE_VID", "0x2717"), 0)
PID = int(os.getenv("XIAOMI_REMOTE_PID", "0x32B8"), 0)
FILTER_NAME = "Xiaomi Remote 2 Pro Filtered"

BLOCK_PHYSICAL_F5 = os.getenv("XIAOMI_BLOCK_PHYSICAL_F5", "1").lower() not in {
    "0", "false", "no", "off"
}
WPS_RESUME_WINDOW_SECONDS = float(
    os.getenv("XIAOMI_WPS_RESUME_WINDOW_SECONDS", "15")
)

BLOCK_KEY = ecodes.KEY_F5
OK_KEYS = {ecodes.KEY_ENTER, ecodes.KEY_OK}
BACK_KEYS = {ecodes.KEY_BACK}


def _run(*args: str) -> str:
    try:
        result = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=0.8,
            check=False,
        )
        return result.stdout or ""
    except Exception:
        return ""


def active_window_id() -> str | None:
    root = _run("xprop", "-root", "_NET_ACTIVE_WINDOW")
    match = re.search(r"0x[0-9a-fA-F]+", root)
    if not match or match.group(0) == "0x0":
        return None
    return match.group(0)


def is_wps_presentation_window(props: str, tree: str = "") -> bool:
    props_lower = props.lower()

    if re.search(r'wm_class.*"wpp"', props_lower):
        return True

    if "wpsoffice" in props_lower and (
        re.search(r'\.(ppt|pptx|dps)(?:\s|\*|\-|")', props_lower)
        or "wps 演示" in props
        or "wps presentation" in props_lower
    ):
        return True

    if "wpsoffice" in props_lower and re.search(
        r'\("wpp"\s+"wpp"\)', tree.lower()
    ):
        return True

    return False


def wps_presentation_is_focused() -> bool:
    wid = active_window_id()
    if not wid:
        return False

    props = _run("xprop", "-id", wid, "WM_CLASS", "_NET_WM_NAME", "WM_NAME")
    tree = ""
    if "wpsoffice" in props.lower():
        tree = _run("xwininfo", "-id", wid, "-tree")
    return is_wps_presentation_window(props, tree)


def find_wps_top_window() -> str | None:
    tree = _run("xwininfo", "-root", "-tree")
    for line in tree.splitlines():
        low = line.lower()
        if "wps office" in low and "wpsoffice" in low:
            match = re.search(r"0x[0-9a-fA-F]+", line)
            if match:
                return match.group(0)
    return None


def click_focus_x11_window(wid: str) -> bool:
    """Restore XWayland WPS focus by simulating a short title-bar click."""
    try:
        x11 = ctypes.CDLL("libX11.so.6")
        xtst = ctypes.CDLL("libXtst.so.6")

        class XWindowAttributes(ctypes.Structure):
            _fields_ = [
                ("x", ctypes.c_int),
                ("y", ctypes.c_int),
                ("width", ctypes.c_int),
                ("height", ctypes.c_int),
                ("border_width", ctypes.c_int),
                ("depth", ctypes.c_int),
                ("visual", ctypes.c_void_p),
                ("root", ctypes.c_ulong),
                ("class_", ctypes.c_int),
                ("bit_gravity", ctypes.c_int),
                ("win_gravity", ctypes.c_int),
                ("backing_store", ctypes.c_int),
                ("backing_planes", ctypes.c_ulong),
                ("backing_pixel", ctypes.c_ulong),
                ("save_under", ctypes.c_int),
                ("colormap", ctypes.c_ulong),
                ("map_installed", ctypes.c_int),
                ("map_state", ctypes.c_int),
                ("all_event_masks", ctypes.c_long),
                ("your_event_mask", ctypes.c_long),
                ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int),
                ("screen", ctypes.c_void_p),
            ]

        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x11.XDefaultRootWindow.restype = ctypes.c_ulong
        x11.XGetWindowAttributes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(XWindowAttributes),
        ]
        x11.XGetWindowAttributes.restype = ctypes.c_int
        x11.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong),
        ]
        x11.XTranslateCoordinates.restype = ctypes.c_int
        x11.XQueryPointer.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint),
        ]
        x11.XQueryPointer.restype = ctypes.c_int
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

        xtst.XTestFakeMotionEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        xtst.XTestFakeMotionEvent.restype = ctypes.c_int
        xtst.XTestFakeButtonEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        xtst.XTestFakeButtonEvent.restype = ctypes.c_int

        display = x11.XOpenDisplay(None)
        if not display:
            return False

        try:
            window = int(wid, 16)
            root = x11.XDefaultRootWindow(display)

            attrs = XWindowAttributes()
            if not x11.XGetWindowAttributes(display, window, ctypes.byref(attrs)):
                return False

            abs_x = ctypes.c_int()
            abs_y = ctypes.c_int()
            child = ctypes.c_ulong()
            if not x11.XTranslateCoordinates(
                display,
                window,
                root,
                0,
                0,
                ctypes.byref(abs_x),
                ctypes.byref(abs_y),
                ctypes.byref(child),
            ):
                return False

            root_ret = ctypes.c_ulong()
            child_ret = ctypes.c_ulong()
            old_x = ctypes.c_int()
            old_y = ctypes.c_int()
            win_x = ctypes.c_int()
            win_y = ctypes.c_int()
            mask = ctypes.c_uint()
            x11.XQueryPointer(
                display,
                root,
                ctypes.byref(root_ret),
                ctypes.byref(child_ret),
                ctypes.byref(old_x),
                ctypes.byref(old_y),
                ctypes.byref(win_x),
                ctypes.byref(win_y),
                ctypes.byref(mask),
            )

            click_x = abs_x.value + min(
                max(attrs.width // 3, 180),
                max(attrs.width - 40, 40),
            )
            click_y = abs_y.value + 18

            xtst.XTestFakeMotionEvent(display, -1, click_x, click_y, 0)
            xtst.XTestFakeButtonEvent(display, 1, 1, 0)
            xtst.XTestFakeButtonEvent(display, 1, 0, 0)
            x11.XFlush(display)
            time.sleep(0.08)

            xtst.XTestFakeMotionEvent(display, -1, old_x.value, old_y.value, 0)
            x11.XFlush(display)
            return True
        finally:
            x11.XCloseDisplay(display)
    except Exception:
        LOG.exception("failed to click-focus WPS window %s", wid)
        return False


def ensure_wps_editor_focus() -> bool:
    wid = find_wps_top_window()
    if not wid:
        return False
    focused = click_focus_x11_window(wid)
    if focused:
        time.sleep(0.12)
    return focused


def find_remote() -> InputDevice | None:
    for path in list_devices():
        try:
            device = InputDevice(path)
            if device.name == FILTER_NAME:
                device.close()
                continue
            if device.info.vendor == VID and device.info.product == PID:
                return device
            device.close()
        except Exception:
            continue
    return None


async def forward_device(device: InputDevice) -> None:
    virtual = UInput.from_device(
        device,
        name=FILTER_NAME,
        bustype=device.info.bustype,
        vendor=VID,
        product=PID,
        version=device.info.version,
        phys="xiaomi-remote-wps-filter",
    )
    mapped_down: dict[int, int] = {}
    blocked_f5 = 0
    wps_resume_until = 0.0

    try:
        device.grab()
        LOG.info(
            "grabbed %s %s vendor=%04x product=%04x; "
            "OK->F5, BACK->ESC in WPS Presentation; block_physical_f5=%s",
            device.path,
            device.name,
            VID,
            PID,
            BLOCK_PHYSICAL_F5,
        )

        async for event in device.async_read_loop():
            if event.type == ecodes.EV_KEY:
                if BLOCK_PHYSICAL_F5 and event.code == BLOCK_KEY:
                    blocked_f5 += 1
                    LOG.info(
                        "blocked physical KEY_F5 value=%s count=%s",
                        event.value,
                        blocked_f5,
                    )
                    continue

                if event.code in OK_KEYS or event.code in BACK_KEYS:
                    target = (
                        ecodes.KEY_F5
                        if event.code in OK_KEYS
                        else ecodes.KEY_ESC
                    )
                    focused = wps_presentation_is_focused()
                    resume_context = (
                        event.code in OK_KEYS
                        and time.monotonic() < wps_resume_until
                        and find_wps_top_window() is not None
                    )

                    if event.value == 1 and (focused or resume_context):
                        if event.code in OK_KEYS:
                            if resume_context:
                                ensure_wps_editor_focus()
                            wps_resume_until = 0.0
                        else:
                            wps_resume_until = (
                                time.monotonic() + WPS_RESUME_WINDOW_SECONDS
                            )

                        mapped_down[event.code] = target
                        virtual.write(ecodes.EV_KEY, target, 1)
                        LOG.info(
                            "mapped %s down -> %s (focused=%s resume=%s)",
                            ecodes.KEY[event.code],
                            ecodes.KEY[target],
                            focused,
                            resume_context,
                        )
                        continue

                    if event.code in mapped_down:
                        mapped_target = mapped_down[event.code]
                        if event.value == 2:
                            virtual.write(ecodes.EV_KEY, mapped_target, 2)
                            continue
                        if event.value == 0:
                            virtual.write(ecodes.EV_KEY, mapped_target, 0)
                            del mapped_down[event.code]
                            LOG.info(
                                "mapped %s up -> %s",
                                ecodes.KEY[event.code],
                                ecodes.KEY[mapped_target],
                            )
                            continue

            virtual.write_event(event)
    finally:
        try:
            device.ungrab()
        except Exception:
            pass
        virtual.close()
        device.close()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    while True:
        device = find_remote()
        if not device:
            LOG.warning("remote not found or permission denied; retrying")
            await asyncio.sleep(2)
            continue

        try:
            await forward_device(device)
        except PermissionError as exc:
            LOG.error("permission denied: %s", exc)
            await asyncio.sleep(3)
        except OSError as exc:
            LOG.warning("remote disconnected or input reset: %s", exc)
            await asyncio.sleep(1)
        except Exception:
            LOG.exception("filter loop failed")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
