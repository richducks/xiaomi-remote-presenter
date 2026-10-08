#!/usr/bin/env python3
"""Conservative active media-tab detection for Global Speed in Chrome/Firefox.

Both browsers use Global Speed keyboard shortcuts D (+0.1x), A (-0.1x).
The remote volume key is stolen only while its active browser window has a
matching MPRIS media session. Background player tabs do not qualify.
"""
from __future__ import annotations

import sys
import json
import re
import urllib.request
from typing import Any

if '/usr/lib/python3/dist-packages' not in sys.path:
    sys.path.append('/usr/lib/python3/dist-packages')


# Trusted *application* names from Linux accessibility (AT-SPI), not window
# titles. A terminal or file manager may have "Firefox" in its title, but
# must never be treated as a browser or receive Ctrl+W from the remote.
_BROWSER_APP_NAMES = frozenset({
    'firefox', 'mozilla firefox', 'firefox nightly',
    'firefox developer edition', 'firefox esr',
    'google chrome', 'google chrome beta', 'google chrome dev',
    'google chrome unstable', 'chrome', 'chromium', 'chromium browser',
    'ungoogled chromium', 'ungoogled-chromium',
    'microsoft edge', 'microsoft edge beta', 'microsoft edge dev',
    'microsoft edge canary',
    'brave', 'brave browser', 'brave browser beta',
    'opera', 'opera gx', 'opera beta', 'opera developer',
    'vivaldi', 'vivaldi stable', 'vivaldi snapshot',
    'librewolf', 'waterfox', 'floorp', 'zen', 'zen browser',
    'tor browser', 'epiphany', 'gnome web', 'web', 'midori',
    'qutebrowser', 'falkon', 'yandex browser',
})


def is_browser_application(app_name: str) -> bool:
    """Only match known standalone web browsers, never tabs or window titles."""
    normalized = ' '.join((app_name or '').strip().casefold().split())
    return normalized in _BROWSER_APP_NAMES


def browser_window_focused() -> bool:
    """Whether the *foreground window* belongs to a supported web browser.

    Does not require playback/MPRIS, so browser Home -> Ctrl+T and TV
    -> Ctrl+W also work on ordinary pages without any media support.
    """
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            try:
                if not is_browser_application(app.get_name()):
                    continue
                for j in range(app.get_child_count()):
                    frame = app.get_child_at_index(j)
                    if (frame.get_role_name() == 'frame' and
                            frame.get_state_set().contains(Atspi.StateType.ACTIVE)):
                        return True
            except Exception:
                continue
        return False
    except Exception:
        # Fail closed: leave the physical Home key unchanged if the desktop
        # accessibility service is unavailable.
        return False


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


def youtube_video_tab_focused() -> bool:
    """Allow YouTube's native K shortcut only on its selected video page.

    YouTube's page title can be machine-translated from Traditional Chinese
    into Simplified Chinese while MPRIS keeps the original title. This
    prevents exact MPRIS title matching from recognizing the active video.
    The foreground video page is identified from its browser window title.
    We intentionally do not require the Firefox-only userscript heartbeat:
    a YouTube watch page may not expose MPRIS and Chrome has no video
    helper, yet its native K shortcut still works. The active window must
    belong to a supported browser, and focused editable fields are excluded
    so the shortcut never types into search/comments.
    """
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        desktop = Atspi.get_desktop(0)
        active = active_browser_window(desktop, Atspi)
        if not active:
            return False
        browser, title = active
        # YouTube video titles end in " - YouTube" before the browser
        # suffix ("— Mozilla Firefox", "- Google Chrome", etc.).
        # Do not mistake YouTube Music or the YouTube homepage for a video.
        if not re.search(r'\s-\sYouTube(?:\s*[—-]\s*.+)?$', title, re.I):
            return False

        # The K shortcut should never type the letter 'k' into YouTube's
        # search box or a chat/comment field. Check accessibility focus.
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if not app or not is_browser_application(app.get_name()):
                continue
            for j in range(app.get_child_count()):
                frame = app.get_child_at_index(j)
                try:
                    if (frame.get_role_name() != 'frame' or
                            not frame.get_state_set().contains(
                                Atspi.StateType.ACTIVE)):
                        continue
                    queue = [(frame, 0)]
                    seen = 0
                    while queue and seen < 2400:
                        item, depth = queue.pop(0)
                        seen += 1
                        if not item:
                            continue
                        try:
                            state = item.get_state_set()
                            if state.contains(Atspi.StateType.FOCUSED):
                                if (state.contains(Atspi.StateType.EDITABLE)
                                        or item.get_role_name() in (
                                            'entry', 'password text',
                                            'combo box')):
                                    return False
                            if depth < 12:
                                for k in range(min(item.get_child_count(), 120)):
                                    queue.append((item.get_child_at_index(k), depth + 1))
                        except Exception:
                            continue
                except Exception:
                    continue
        return True
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
