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


def is_wps_presentation_application(app_name: str, frame_title: str) -> bool:
    """Strictly distinguish WPS slide editor from Writer/Spreadsheets."""
    app = ' '.join((app_name or '').strip().casefold().split())
    title = (frame_title or '').casefold()
    if app in {'wpp', 'wps presentation', 'wps 演示'}:
        return True
    if app not in {'wps office', 'wpsoffice', 'kingsoft office'}:
        return False
    return bool(re.search(r'\.(?:pptx?|dps)(?:\b|\s|\*)', title)
                or 'wps 演示' in title or 'wps presentation' in title)


def _active_frames(desktop: Any, atspi: Any) -> list[tuple[str, Any]]:
    """List AT-SPI ACTIVE frames, including unrelated applications."""
    found = []
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        try:
            for j in range(app.get_child_count()):
                frame = app.get_child_at_index(j)
                if (frame.get_role_name() == 'frame' and
                        frame.get_state_set().contains(atspi.StateType.ACTIVE)):
                    found.append((app.get_name() or '', frame))
        except Exception:
            continue
    return found


def _contains_focused_descendant(frame: Any, atspi: Any) -> bool:
    """Look for actual keyboard focus, only when ACTIVE flags conflict.

    GNOME Wayland sometimes advertises two simultaneously ACTIVE windows,
    one of which is stale. Bounded traversal avoids unbounded browser trees.
    """
    from collections import deque
    queue = deque([(frame, 0)])
    examined = 0
    while queue and examined < 500:
        child, depth = queue.popleft()
        examined += 1
        try:
            if child.get_state_set().contains(atspi.StateType.FOCUSED):
                return True
            if depth < 10:
                for index in range(min(child.get_child_count(), 50)):
                    queue.append((child.get_child_at_index(index), depth + 1))
        except Exception:
            continue
    return False


def _foreground_frame(desktop: Any, atspi: Any) -> tuple[str, Any] | None:
    """Choose one actual focused frame, otherwise refuse risky remaps."""
    frames = _active_frames(desktop, atspi)
    if len(frames) == 1:
        return frames[0]
    if not frames:
        return None
    focused = [(app, frame) for app, frame in frames
               if _contains_focused_descendant(frame, atspi)]
    # A false negative is safer than Ctrl+W or F5 in the wrong application.
    return focused[0] if len(focused) == 1 else None


def _compositor_window() -> tuple[str, str, str] | None:
    """GNOME Shell's actual focus (app ID, WM class, title), or unavailable.

    A tiny read-only local GNOME extension exports this information. Unlike
    AT-SPI ACTIVE flags, Mutter's focus_window reflects Wayland window focus.
    None means the extension is absent, NOT that the foreground is a browser.
    """
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = bus.call_sync(
            'org.gnome.Shell',
            '/org/gnome/Shell/Extensions/XiaomiRemoteFocus',
            'org.xiaomi.RemoteFocus', 'GetFocus', None,
            GLib.VariantType('(sss)'), Gio.DBusCallFlags.NO_AUTO_START,
            600, None)
        return tuple(result.unpack())
    except Exception:
        return None


def _shell_browser_kind(app_id: str, wm_class: str) -> str | None:
    """Classify trusted compositor app identity, never a window title."""
    tokens = set(re.split(r'[^a-z0-9]+',
                          ((app_id or '') + ' ' + (wm_class or '')).casefold()))
    if tokens.intersection({'firefox', 'librewolf', 'waterfox', 'floorp'}):
        return 'firefox'
    if tokens.intersection({'chrome', 'chromium', 'brave', 'edge', 'msedge',
                            'vivaldi', 'opera', 'epiphany', 'falkon',
                            'midori', 'qutebrowser', 'zen'}):
        return 'chromium'
    return None


def _shell_wps_presentation(app_id: str, wm_class: str, title: str) -> bool:
    identity = (app_id + ' ' + wm_class).casefold()
    tokens = set(re.split(r'[^a-z0-9]+', identity))
    if 'wpp' in tokens:
        return True
    if {'wps', 'wpsoffice', 'kingsoft'}.intersection(tokens):
        return bool(re.search(r'\.(?:pptx?|dps)(?:\b|\s|\*)', title.casefold())
                    or 'wps 演示' in title.casefold()
                    or 'wps presentation' in title.casefold())
    return False


def wps_presentation_focused() -> bool:
    """Only map WPS when the compositor confirms the slide editor."""
    shell = _compositor_window()
    if shell is not None:
        return _shell_wps_presentation(*shell)
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        selected = _foreground_frame(Atspi.get_desktop(0), Atspi)
        return bool(selected and
                    is_wps_presentation_application(selected[0],
                                                    selected[1].get_name()))
    except Exception:
        return False


def browser_window_focused() -> bool:
    """Map browser shortcuts only when the actual foreground is a browser."""
    shell = _compositor_window()
    if shell is not None:
        return _shell_browser_kind(shell[0], shell[1]) is not None
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        selected = _foreground_frame(Atspi.get_desktop(0), Atspi)
        return bool(selected and is_browser_application(selected[0]))
    except Exception:
        return False


def active_browser_window(desktop: Any = None, atspi: Any = None) -> tuple[str, str] | None:
    """Prefer GNOME Shell focus; open AT-SPI only for legacy fallback."""
    shell = _compositor_window()
    if shell is not None:
        browser = _shell_browser_kind(shell[0], shell[1])
        return (browser, shell[2].strip()) if browser else None
    if desktop is None or atspi is None:
        try:
            import gi
            gi.require_version('Atspi', '2.0')
            from gi.repository import Atspi
            desktop, atspi = Atspi.get_desktop(0), Atspi
        except Exception:
            return None
    selected = _foreground_frame(desktop, atspi)
    if not selected:
        return None
    app, frame = selected
    name = ' '.join(app.strip().casefold().split())
    if name == 'google chrome':
        browser = 'chromium'
    elif name == 'firefox':
        browser = 'firefox'
    else:
        return None
    try:
        return browser, (frame.get_name() or '').strip()
    except Exception:
        return None


def is_firefox_pip_window(browser: str, window_title: str) -> bool:
    """Firefox built-in Picture-in-Picture has its own active window."""
    if browser != 'firefox':
        return False
    normalized = window_title.strip().casefold()
    return normalized in ('画中画', 'picture-in-picture', 'picture in picture')


def firefox_pip_focused() -> bool:
    """Recognize PiP with compositor focus and lazy legacy fallback."""
    try:
        active = active_browser_window()
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
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
        active = active_browser_window()
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
        active = active_browser_window()
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
        active = active_browser_window()
        if not active:
            return False
        browser, title = active
        # YouTube video titles end in " - YouTube" before the browser
        # suffix ("— Mozilla Firefox", "- Google Chrome", etc.).
        # Do not mistake YouTube Music or the YouTube homepage for a video.
        if not re.search(r'\s-\sYouTube(?:\s*[—-]\s*.+)?$', title, re.I):
            return False

        # Only a confirmed YouTube video title needs the costly AT-SPI walk.
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        desktop = Atspi.get_desktop(0)
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
