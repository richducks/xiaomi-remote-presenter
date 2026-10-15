#!/usr/bin/env python3
"""Fast native live WeChat dictation from Xiaomi BLE audio start/stop.

The Ctrl+Alt input-method recognizer produces live characters and its icon.
Do not run offline Whisper or paste a second transcript on BLE release.
"""
from __future__ import annotations

import asyncio
import atexit
from collections import deque
from functools import lru_cache
import logging
import re
import time

from video_browser_context import _compositor_window
from wechat_voice_settings import load_settings

LOG = logging.getLogger('xiaomi-wechat-dictation')
MAX_DURATION = 80
DRAFT_TTL = 45


def is_wechat_identity(app_id: str, wm_class: str) -> bool:
    """Never rely on a window title or a text prefix supplied by another app."""
    tokens = set(re.split(r'[^a-z0-9]+', (app_id + ' ' + wm_class).casefold()))
    return 'wechat' in tokens and ('tencent' in tokens or
                                   app_id.casefold() in ('wechat', 'wechat.desktop') or
                                   wm_class.casefold() == 'wechat')


def wechat_window() -> tuple[str, str, str] | None:
    shell = _compositor_window()
    return shell if shell and is_wechat_identity(shell[0], shell[1]) else None


# Discovered native Linux WeChat accessibility hierarchy (version 4.1.x).
# A fast validated path avoids ~1 second of full AT-SPI BFS on each press.
_WECHAT_COMPOSER_PATH = (0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 2, 2, 0, 0)


def _fast_chat_editor():
    if wechat_window() is None:
        return None
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        desktop = Atspi.get_desktop(0)
        for i in range(min(desktop.get_child_count(), 100)):
            app = desktop.get_child_at_index(i)
            if (app.get_name() or '').casefold() != 'wechat':
                continue
            node = app
            for idx in _WECHAT_COMPOSER_PATH:
                node = node.get_child_at_index(idx)
            if node.get_role_name() != 'text':
                continue
            state = node.get_state_set()
            if not (state.contains(Atspi.StateType.EDITABLE)
                    and state.contains(Atspi.StateType.FOCUSABLE)
                    and state.contains(Atspi.StateType.SHOWING)):
                continue
            comp = node.get_component_iface()
            rect = comp.get_extents(Atspi.CoordType.SCREEN) if comp else None
            frame = app.get_child_at_index(0)
            frame_comp = frame.get_component_iface()
            bounds = frame_comp.get_extents(Atspi.CoordType.SCREEN) if frame_comp else None
            if (rect and bounds and rect.width >= 120 and rect.height >= 35
                    and rect.x >= bounds.x + bounds.width * .20
                    and rect.y >= bounds.y + bounds.height * .60
                    and rect.x + rect.width <= bounds.x + bounds.width + 3
                    and rect.y + rect.height <= bounds.y + bounds.height + 3):
                return node, comp, Atspi
    except Exception:
        return None
    return None


def _chat_editor():
    """Locate the WeChat *chat* editor with a bounded nearby fallback.

    Qt may transiently reorder the final editor children. Searching the
    entire AT-SPI application can take seconds and start voice recognition
    only after the physical microphone key has already been released.
    """
    if wechat_window() is None:
        return None
    fast = _fast_chat_editor()
    if fast is not None:
        return fast
    # Full-screen Qt can rebuild the fixed path. A *currently focused*,
    # visible edit box in the WeChat chat area is unambiguous, and much
    # cheaper to find than scanning the whole application tree.
    focused = _focused_fullscreen_chat_editor()
    if focused is not None:
        return focused
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        from collections import deque
        desktop = Atspi.get_desktop(0)
        deadline = time.monotonic() + .48
        for i in range(min(desktop.get_child_count(), 100)):
            if time.monotonic() > deadline:
                break
            app = desktop.get_child_at_index(i)
            if (app.get_name() or '').casefold() != 'wechat':
                continue
            frame = app.get_child_at_index(0)
            frame_comp = frame.get_component_iface()
            bounds = frame_comp.get_extents(Atspi.CoordType.SCREEN) if frame_comp else None
            if not bounds or bounds.width < 420 or bounds.height < 420:
                continue
            # Try a resilient subtree search within the message composer
            # pane. This handles small native widget layout changes and
            # avoids walking 1000+ unrelated contact/settings widgets.
            for prefix in (14, 12):
                if time.monotonic() > deadline:
                    return None
                try:
                    node = app
                    for index in _WECHAT_COMPOSER_PATH[:prefix]:
                        node = node.get_child_at_index(index)
                except Exception:
                    continue
                q = deque([(node, 0)])
                candidates = []
                visited = 0
                while q and visited < 650 and time.monotonic() <= deadline:
                    current, depth = q.popleft()
                    visited += 1
                    try:
                        if current.get_role_name() == 'text':
                            state = current.get_state_set()
                            if (state.contains(Atspi.StateType.EDITABLE)
                                    and state.contains(Atspi.StateType.FOCUSABLE)
                                    and state.contains(Atspi.StateType.SHOWING)):
                                comp = current.get_component_iface()
                                rect = comp.get_extents(Atspi.CoordType.SCREEN) if comp else None
                                if (rect and rect.width >= 120 and rect.height >= 35
                                        and rect.x >= bounds.x + bounds.width * .20
                                        and rect.y >= bounds.y + bounds.height * .60
                                        and rect.x + rect.width <= bounds.x + bounds.width + 3
                                        and rect.y + rect.height <= bounds.y + bounds.height + 3):
                                    candidates.append((current, comp, Atspi))
                        if depth < 18:
                            for j in range(min(current.get_child_count(), 90)):
                                q.append((current.get_child_at_index(j), depth + 1))
                    except Exception:
                        continue
                if len(candidates) == 1:
                    LOG.debug('WeChat nearby composer lookup used prefix=%d nodes=%d',prefix,visited)
                    return candidates[0]
                # If a pane contains multiple plausible editors, never guess.
                if len(candidates) > 1:
                    return None
    except Exception as exc:
        LOG.debug('AT-SPI chat editor lookup unavailable: %s', exc)
    # Maximized/full-screen WeChat rebuilds its Qt/AT-SPI hierarchy, so the
    # compact editor path and its near-sibling prefixes may both disappear.
    # Only when the compositor still confirms WeChat, search *visible* chat
    # editors near the bottom right of its main window, with bounded work.
    return _fullscreen_chat_editor()


def _editor_geometry_is_chat_box(rect, bounds) -> bool:
    """Reject search, contact, settings and other non-chat editable fields."""
    return bool(rect and bounds and bounds.width >= 420 and bounds.height >= 420
                and rect.width >= 120
                and 28 <= rect.height <= min(520, bounds.height * .58)
                and rect.x >= bounds.x + bounds.width * .18
                and rect.y >= bounds.y + bounds.height * .44
                and rect.x + rect.width <= bounds.x + bounds.width + 4
                and rect.y + rect.height <= bounds.y + bounds.height + 4)


def _focused_fullscreen_chat_editor():
    """Find focused WeChat composer after the Qt window is maximized.

    This is only valid when Mutter reports WeChat itself as foreground, and
    only accepts a single visible editable text box in the chat area.
    It never injects into search, contacts or another application.
    """
    if wechat_window() is None:
        return None
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        desktop = Atspi.get_desktop(0)
        deadline = time.monotonic() + .34
        candidates = []
        for i in range(min(desktop.get_child_count(), 70)):
            if time.monotonic() >= deadline:
                break
            app = desktop.get_child_at_index(i)
            if (app.get_name() or '').casefold() != 'wechat':
                continue
            for j in range(min(app.get_child_count(), 5)):
                root = app.get_child_at_index(j)
                if root.get_role_name() not in ('frame', 'window'):
                    continue
                bounds_iface = root.get_component_iface()
                bounds = bounds_iface.get_extents(Atspi.CoordType.SCREEN) if bounds_iface else None
                if not bounds or bounds.width < 420 or bounds.height < 420:
                    continue
                q = deque([(root, 0)])
                seen = 0
                while q and seen < 1050 and time.monotonic() < deadline:
                    node, depth = q.popleft()
                    seen += 1
                    try:
                        state = node.get_state_set()
                        if node.get_role_name() in ('text', 'entry') and (
                            state.contains(Atspi.StateType.FOCUSED)
                            and state.contains(Atspi.StateType.EDITABLE)
                            and state.contains(Atspi.StateType.SHOWING)
                        ):
                            comp = node.get_component_iface()
                            box = comp.get_extents(Atspi.CoordType.SCREEN) if comp else None
                            if _editor_geometry_is_chat_box(box, bounds):
                                candidates.append((node, comp, Atspi))
                        if depth < 30:
                            for k in range(min(node.get_child_count(), 95)):
                                q.append((node.get_child_at_index(k), depth + 1))
                    except Exception:
                        continue
        if len(candidates) == 1:
            LOG.info('WeChat full-screen focused composer identified')
            return candidates[0]
    except Exception as exc:
        LOG.debug('WeChat focused editor lookup unavailable: %s', exc)
    return None


def _fullscreen_chat_editor():
    if wechat_window() is None:
        return None
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        desktop = Atspi.get_desktop(0)
        deadline = time.monotonic() + .70
        candidates = []
        for i in range(min(desktop.get_child_count(), 80)):
            if time.monotonic() > deadline:
                break
            app = desktop.get_child_at_index(i)
            if (app.get_name() or '').casefold() != 'wechat':
                continue
            for root_idx in range(min(app.get_child_count(), 8)):
                if time.monotonic() > deadline:
                    break
                frame = app.get_child_at_index(root_idx)
                if frame.get_role_name() not in ('frame', 'window'):
                    continue
                box = frame.get_component_iface()
                bounds = box.get_extents(Atspi.CoordType.SCREEN) if box else None
                if not bounds or bounds.width < 420 or bounds.height < 420:
                    continue
                queue = deque([(frame, 0)])
                visited = 0
                while queue and visited < 1900 and time.monotonic() < deadline:
                    node, depth = queue.popleft()
                    visited += 1
                    try:
                        if node.get_role_name() in ('text', 'entry'):
                            state = node.get_state_set()
                            if (state.contains(Atspi.StateType.EDITABLE)
                                    and state.contains(Atspi.StateType.FOCUSABLE)
                                    and state.contains(Atspi.StateType.SHOWING)):
                                comp = node.get_component_iface()
                                rect = comp.get_extents(Atspi.CoordType.SCREEN) if comp else None
                                if _editor_geometry_is_chat_box(rect, bounds):
                                    candidates.append((node, comp, Atspi))
                        if depth < 28:
                            for j in range(min(node.get_child_count(), 95)):
                                queue.append((node.get_child_at_index(j), depth + 1))
                    except Exception:
                        continue
        if len(candidates) == 1:
            LOG.info('WeChat full-screen composer resolved through bounded visual search')
            return candidates[0]
        LOG.info('WeChat full-screen composer ambiguous or unavailable (%d candidates)',
                 len(candidates))
    except Exception as exc:
        LOG.debug('WeChat full-screen accessibility search unavailable: %s', exc)
    return None


def wechat_editor_focused() -> bool:
    editor = _chat_editor()
    return bool(editor and editor[0].get_state_set().contains(editor[2].StateType.FOCUSED))


def focus_wechat_chat_editor() -> bool:
    """Focus the existing chat draft without a mouse click or blind Tab."""
    editor = _chat_editor()
    if not editor:
        return False
    node, component, atspi = editor
    if node.get_state_set().contains(atspi.StateType.FOCUSED):
        return True
    if not component.grab_focus():
        return False
    for _ in range(5):
        if node.get_state_set().contains(atspi.StateType.FOCUSED):
            # Final compositor verification protects against focus switching
            # while GNOME/Qt settles. The press helper checks again too.
            return wechat_window() is not None
        if wechat_window() is None:
            return False
        time.sleep(.03)
    return False


def _draft_signature() -> tuple[int, bytes] | None:
    """Compare drafts privately without logging message text or storing it.

    Distinguishes a fresh dictation from the user's pre-existing typed draft.
    """
    if wechat_window() is None:
        return None
    try:
        editor = _chat_editor()
        if editor is None:
            return None
        node, _, atspi = editor
        if not node.get_state_set().contains(atspi.StateType.FOCUSED):
            return None
        text = node.get_text_iface()
        if not text:
            return None
        length = text.get_character_count()
        if not isinstance(length, int) or not 0 <= length <= 100000:
            return None
        import hashlib
        digest = hashlib.blake2s(text.get_text(0, length).encode('utf-8'), digest_size=16).digest()
        return length, digest
    except Exception:
        return None


@lru_cache(maxsize=1)
def _keyboard():
    """Keep one keyboard registered with Mutter; no input grab or polling."""
    from evdev import UInput, ecodes
    # Only four keys are emitted. We advertise a standard keyboard's
    # capabilities so GNOME/Mutter also routes the shortcut to maximized or
    # full-screen Qt windows; sparse uinput devices get ID_INPUT_KEY=1 but
    # often not ID_INPUT_KEYBOARD=1 and are silently ignored.
    keys = sorted(set(range(1, 129)) |
                  {ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTALT,
                   ecodes.KEY_V, ecodes.KEY_ENTER})
    ui = UInput({ecodes.EV_KEY: keys}, name='Xiaomi WeChat Text Actions')
    atexit.register(ui.close)
    # A newly-added uinput device can otherwise lose its first key press.
    time.sleep(.28)
    return ui


async def prewarm_wechat_keyboard() -> None:
    """Register the virtual keyboard before the first speech-key press.

    Prewarming only prepares a device; it never emits a keystroke, grabs an
    input device, activates a window or starts a voice recognizer.
    """
    try:
        await asyncio.to_thread(_keyboard)
        LOG.debug('WeChat Ctrl+Alt keyboard warmed')
    except Exception as exc:
        LOG.warning('WeChat keyboard prewarm skipped: %s', exc)


def hold_wechat_ctrl_alt(pressed: bool) -> bool:
    """Emit only the requested two-key Ctrl+Alt chord; pair all releases."""
    from evdev import ecodes
    # The UInput registration delay must not cause a shortcut in a tab or WPS
    # that became focused after the remote's BLE audio_start was received.
    if pressed and wechat_window() is None:
        return False
    ui = _keyboard()
    if pressed:
        if wechat_window() is None:
            return False
        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTALT, 1)
    else:
        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTALT, 0)
        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
    ui.syn()
    return True


def paste_or_send(kind: str) -> bool:
    """Only run in a composer with live WeChat focus; use short virtual taps."""
    if kind not in ('paste', 'send') or not focus_wechat_chat_editor():
        return False
    from evdev import ecodes
    ui = _keyboard()
    if not wechat_editor_focused():
        return False
    if kind == 'paste':
        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
        ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
        ui.syn()
        time.sleep(0.065)
        ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
    else:
        ui.write(ecodes.EV_KEY, ecodes.KEY_ENTER, 1)
        ui.syn()
        time.sleep(0.055)
        ui.write(ecodes.EV_KEY, ecodes.KEY_ENTER, 0)
    ui.syn()
    return True


class WechatDictation:
    """One live Ctrl+Alt speech input per press; no offline STT or paste.

    Native input-method speech indicator and near-real-time character output
    come from the first working shortcut. Release only releases both keys.
    """

    SETTLE_SECONDS = 0.85

    def __init__(self) -> None:
        self.pending_window: tuple[str, str, str] | None = None
        self.draft_at = 0.0
        self.finish_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._shortcut_held = False
        self._shortcut_watchdog: asyncio.Task | None = None
        self._target: tuple[str, str, str] | None = None
        self._session = 0

    def busy(self) -> bool:
        return (self._shortcut_held or
                bool(self.finish_task and not self.finish_task.done()))

    @staticmethod
    def _same_app(a: tuple[str, str, str] | None,
                  b: tuple[str, str, str] | None) -> bool:
        return bool(a and b and a[:2] == b[:2])

    def draft_ready(self) -> bool:
        return (not self.busy()
                and self._same_app(wechat_window(), self.pending_window)
                and 0 < time.monotonic() - self.draft_at <= DRAFT_TTL
                and wechat_editor_focused())

    async def start(self) -> None:
        async with self._lock:
            if self.busy():
                return
            target = await asyncio.to_thread(wechat_window)
            if target is None or not load_settings()['enabled']:
                return
            # Validate the chat composer (never search/settings), with a
            # bounded fallback rather than a whole-application AT-SPI scan.
            lookup_started = time.monotonic()
            settings = load_settings()
            focus_ready = await asyncio.to_thread(
                focus_wechat_chat_editor if settings['auto_focus_composer']
                else wechat_editor_focused
            )
            if not focus_ready:
                LOG.info('WeChat chat editor unavailable after %.0fms; no hotkey',
                         (time.monotonic() - lookup_started) * 1000)
                return
            self.pending_window = None
            self.draft_at = 0.0
            self._target = target
            self._session += 1
            try:
                if await asyncio.to_thread(hold_wechat_ctrl_alt, True):
                    self._shortcut_held = True
                    self._shortcut_watchdog = asyncio.create_task(self._release_stuck_shortcut())
                    LOG.info('WeChat LIVE Ctrl+Alt dictation activated; editor_lookup_ms=%.0f',
                             (time.monotonic() - lookup_started) * 1000)
                else:
                    self._target = None
            except Exception:
                self._target = None
                LOG.exception('WeChat native live dictation shortcut failed')

    async def _release_stuck_shortcut(self) -> None:
        try:
            await asyncio.sleep(MAX_DURATION + 3)
            if self._shortcut_held:
                LOG.warning('WeChat Ctrl+Alt watchdog releasing held shortcut')
                await self._release_ctrl_alt()
        except asyncio.CancelledError:
            pass

    async def _release_ctrl_alt(self) -> None:
        if self._shortcut_held:
            self._shortcut_held = False
            await asyncio.to_thread(hold_wechat_ctrl_alt, False)

    async def stop(self) -> None:
        async with self._lock:
            if self._shortcut_watchdog:
                self._shortcut_watchdog.cancel()
                self._shortcut_watchdog = None
            if not self._shortcut_held:
                return
            target = self._target
            session = self._session
            self._target = None
            await self._release_ctrl_alt()
            # No whisper, clipboard, or second writer after release. Give the
            # live recognizer a moment to finalize its last partial syllable.
            if target is not None:
                self.finish_task = asyncio.create_task(self._finalize(target, session))
            LOG.info('WeChat live voice released; text retained, no second paste')

    async def _finalize(self, target: tuple[str, str, str], session: int) -> None:
        await asyncio.sleep(
            load_settings()['preview_settle_ms'] / 1000.0
            if self.SETTLE_SECONDS == .85 else self.SETTLE_SECONDS
        )
        if session != self._session:
            return
        current = await asyncio.to_thread(wechat_window)
        if not self._same_app(current, target):
            return
        # Pending means the user's physical OK can send the current visible
        # draft. It does NOT cause any text mutation or automatic submission.
        self.pending_window = current
        self.draft_at = time.monotonic()
        LOG.info('WeChat live text can be reviewed; remote OK available')

    async def send(self) -> bool:
        if not await asyncio.to_thread(self.draft_ready):
            return False
        if await asyncio.to_thread(paste_or_send, 'send'):
            self.pending_window = None
            self.draft_at = 0.0
            LOG.info('WeChat remote OK dispatched native Enter')
            return True
        return False
