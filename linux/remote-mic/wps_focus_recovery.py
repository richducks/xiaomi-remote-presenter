#!/usr/bin/env python3
"""WPS Presentation: focus repair for RC003 OK->F5 after Back->Esc.

ONLY called by the WPS scoped HID rule after a confirmed WPS Back.
Never send a general global shortcut, and never infer WPS from title alone.
This restores the narrow XWayland workaround from the previous working code.
"""
from __future__ import annotations

import ctypes
import logging
import re
import subprocess
import time

from video_browser_context import _compositor_window, _shell_wps_presentation

LOG = logging.getLogger("xiaomi-wps-focus-recovery")

WPS_RESUME_SECONDS = 15.0


def safe_to_resume_wps() -> bool:
    """When previous WPS Back ended presentation, never steal focus from apps.

    Recovery is limited to WPS itself or GNOME Desktop Icons helper after the
    slideshow window was destroyed. In particular, refuse Firefox, Chrome,
    WeChat, terminal, remote desktop, other WPS document types.
    """
    shell = _compositor_window()
    if shell is None:
        return False
    app_id, wm_class, title = shell
    if _shell_wps_presentation(app_id, wm_class, title):
        return True
    if (app_id.casefold().startswith("window:") and
            wm_class.casefold() == "gjs" and title == "Desktop Icons 1"):
        return True
    return False


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
        x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
        x11.XDefaultScreen.restype = ctypes.c_int
        x11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x11.XDisplayWidth.restype = ctypes.c_int
        x11.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x11.XDisplayHeight.restype = ctypes.c_int
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
            if attrs.map_state != 2 or attrs.width < 380 or attrs.height < 220:
                LOG.warning("WPS window is hidden or too small to focus safely")
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
            if not x11.XQueryPointer(
                dpy, root,
                ctypes.byref(root_ret), ctypes.byref(child_ret),
                ctypes.byref(old_x), ctypes.byref(old_y),
                ctypes.byref(win_x), ctypes.byref(win_y),
                ctypes.byref(mask),
            ):
                return False
            # Never release a physically held mouse button or interrupt drag.
            if mask.value & 0x1F00:
                LOG.warning("WPS focus repair skipped: pointer button held")
                return False

            # Click the title-bar area. This gives Mutter a real user-like
            # activation event, unlike _NET_ACTIVE_WINDOW under Wayland.
            click_x = abs_x.value + min(max(attrs.width // 3, 180), max(attrs.width - 40, 40))
            click_y = abs_y.value + 18
            screen = x11.XDefaultScreen(dpy)
            width = x11.XDisplayWidth(dpy, screen)
            height = x11.XDisplayHeight(dpy, screen)
            if not (0 <= click_x < width and 0 <= click_y < height):
                LOG.warning("WPS focus repair skipped: target outside X display")
                return False

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
    # Recheck compositor focus immediately before a synthetic mouse click.
    if not safe_to_resume_wps():
        LOG.info("WPS focus repair skipped: another app is foreground")
        return False
    wid = find_wps_top_window()
    if not wid:
        LOG.warning("WPS presentation editor not found for focus recovery")
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
