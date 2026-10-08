#!/usr/bin/env python3
"""Conservative active media-tab detection for Global Speed in Chrome/Firefox.

Both browsers use Global Speed keyboard shortcuts D (+0.1x), A (-0.1x).
The remote volume key is stolen only while its active browser window has a
matching MPRIS media session. Background player tabs do not qualify.
"""
from __future__ import annotations

import sys
import json
import urllib.request
from typing import Any

if '/usr/lib/python3/dist-packages' not in sys.path:
    sys.path.append('/usr/lib/python3/dist-packages')


def active_browser_window(desktop: Any, atspi: Any) -> tuple[str, str] | None:
    """Return (MPRIS player prefix, active browser window title)."""
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        name = (app.get_name() or '').strip().casefold()
        if name == 'google chrome':
            browser = 'chromium'
        elif name == 'firefox':
            browser = 'firefox'
        else:
            continue
        for j in range(app.get_child_count()):
            frame = app.get_child_at_index(j)
            try:
                if frame.get_role_name() != 'frame':
                    continue
                if frame.get_state_set().contains(atspi.StateType.ACTIVE):
                    return browser, (frame.get_name() or '').strip()
            except Exception:
                continue
    return None


def is_firefox_pip_window(browser: str, window_title: str) -> bool:
    """Firefox built-in Picture-in-Picture has its own active window."""
    if browser != 'firefox':
        return False
    normalized = window_title.strip().casefold()
    return normalized in ('画中画', 'picture-in-picture', 'picture in picture')


def firefox_pip_focused() -> bool:
    """Recognize the native Firefox PiP window, independent of video tab title."""
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        active = active_browser_window(Atspi.get_desktop(0), Atspi)
        return active is not None and is_firefox_pip_window(*active)
    except Exception:
        return False


def media_title_matches_window(window_title: str, media_title: str, status: str) -> bool:
    """Match the foreground tab, never a background playing browser tab."""
    if status not in {'Playing', 'Paused'}:
        return False
    media = media_title.strip().casefold()
    window = window_title.strip().casefold()
    return len(media) >= 3 and media in window


def active_browser_media_session() -> tuple[object, str] | None:
    """Return the foreground browser's matching media player or None.

    A background player must never consume OK / volume ring buttons.
    """
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi, Gio, GLib
        active = active_browser_window(Atspi.get_desktop(0), Atspi)
        if not active:
            return None
        browser, window_title = active
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        names = bus.call_sync(
            'org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'ListNames', None,
            GLib.VariantType('(as)'), Gio.DBusCallFlags.NONE, 300, None
        ).unpack()[0]
        for name in names:
            if not name.startswith('org.mpris.MediaPlayer2.' + browser + '.'):
                continue
            try:
                result = bus.call_sync(
                    name, '/org/mpris/MediaPlayer2',
                    'org.freedesktop.DBus.Properties', 'GetAll',
                    GLib.Variant('(s)', ('org.mpris.MediaPlayer2.Player',)),
                    GLib.VariantType('(a{sv})'),
                    Gio.DBusCallFlags.NONE, 300, None
                )
                props = result.unpack()[0]
                metadata = props.get('Metadata') or {}
                has_selected_media = media_title_matches_window(
                    window_title,
                    str(metadata.get('xesam:title') or ''),
                    str(props.get('PlaybackStatus') or ''),
                )
                is_pip = is_firefox_pip_window(browser, window_title)
                is_live_pip_player = is_pip and str(
                    props.get('PlaybackStatus') or ''
                ) in ('Playing', 'Paused')
                if (has_selected_media or is_live_pip_player) and bool(
                    props.get('CanControl', False)
                ):
                    return bus, name
            except Exception:
                continue
        return None
    except Exception:
        return None


def browser_media_tab_focused() -> bool:
    # First choice: the matching MPRIS media session.
    if active_browser_media_session() is not None:
        return True
    # Many sites do not expose MPRIS, or its metadata differs from the
    # tab title. A browser userscript reporting a focused <video> is a
    # stronger and more universal positive signal.
    try:
        import gi
        gi.require_version('Atspi','2.0')
        from gi.repository import Atspi
        active=active_browser_window(Atspi.get_desktop(0), Atspi)
        if not active:
            return False
        browser=active[0]
        req=urllib.request.Request(
            "http://127.0.0.1:18766/video/active?browser="+browser)
        with urllib.request.urlopen(req,timeout=0.15) as r:
            return bool(json.load(r).get('active'))
    except Exception:
        return False


def toggle_browser_play_pause() -> bool:
    """Directly toggle selected Chrome/Firefox media, not an unrelated player."""
    player = active_browser_media_session()
    if not player:
        return False
    try:
        from gi.repository import Gio
        bus, name = player
        bus.call_sync(name, '/org/mpris/MediaPlayer2',
                      'org.mpris.MediaPlayer2.Player', 'PlayPause',
                      None, None, Gio.DBusCallFlags.NONE, 700, None)
        return True
    except Exception:
        return False


if __name__ == '__main__':
    import json
    print(json.dumps({'video_tab_focused': browser_media_tab_focused()}))
