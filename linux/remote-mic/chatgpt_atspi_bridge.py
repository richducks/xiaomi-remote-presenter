#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import logging
import signal
import subprocess
import time
from contextlib import suppress

import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi

LOG = logging.getLogger('xiaomi-chatgpt-atspi')
REMOTE_SOURCE = 'xiaomi_remote_mic_sink.monitor'
START_NAMES = {'听写', 'Start dictation', 'Dictate', 'Dictate button'}
STOP_NAMES = {'停止听写', 'Stop dictation', 'Stop recording'}
TARGET_TAB_HINT = '制作Linux版本需买硬件吗'


def chrome_app():
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        with suppress(Exception):
            if app.get_name() == 'Google Chrome':
                return app
    return None


def _walk(node, visitor, *, max_nodes=7000):
    stack = [node]
    seen = 0
    while stack and seen < max_nodes:
        current = stack.pop()
        seen += 1
        try:
            if visitor(current):
                return current
            count = current.get_child_count()
        except Exception:
            continue
        for i in range(min(count, 350) - 1, -1, -1):
            with suppress(Exception):
                stack.append(current.get_child_at_index(i))
    return None


def find_button(names: set[str]):
    app = chrome_app()
    if app is None:
        return None
    def match(node):
        try:
            return node.get_role_name() in ('button', 'toggle button') and (node.get_name() or '').strip() in names
        except Exception:
            return False
    return _walk(app, match)


def find_target_tab():
    app = chrome_app()
    if app is None:
        return None
    def match(node):
        try:
            return node.get_role_name() == 'page tab' and TARGET_TAB_HINT in (node.get_name() or '')
        except Exception:
            return False
    return _walk(app, match)


def invoke(node) -> tuple[bool, str | None]:
    if node is None:
        return False, None
    try:
        action = node.get_action_iface()
        for desired in ('press', 'click', 'activate', 'doDefault'):
            for i in range(action.get_n_actions()):
                name = action.get_action_name(i)
                if name == desired:
                    ok = bool(action.do_action(i))
                    return ok, name
    except Exception as exc:
        LOG.warning('AT-SPI action failed: %s', exc)
    return False, None


def activate_target_tab() -> bool:
    tab = find_target_tab()
    if tab is None:
        return False
    ok, action = invoke(tab)
    if ok:
        LOG.debug('activated ChatGPT target tab action=%s', action)
    return ok


def button_state() -> dict[str, object]:
    app = chrome_app()
    if app is None:
        return {'chrome': False, 'start': False, 'stop': False, 'title': None}
    title = None
    with suppress(Exception):
        for i in range(app.get_child_count()):
            child = app.get_child_at_index(i)
            if child.get_role_name() == 'frame' and child.get_name():
                title = child.get_name()
                break
    return {
        'chrome': True,
        'start': find_button(START_NAMES) is not None,
        'stop': find_button(STOP_NAMES) is not None,
        'title': title,
    }


class Bridge:
    def __init__(self):
        self.previous_source: str | None = None
        self.restore_task: asyncio.Task | None = None
        self.start_task: asyncio.Task | None = None
        self.stop_task: asyncio.Task | None = None
        self.button_held = False
        self.start_clicked = False

    @staticmethod
    def pactl(*args: str) -> str:
        p = subprocess.run(['pactl', *args], text=True, capture_output=True, check=False)
        if p.returncode:
            LOG.warning('pactl %s failed: %s', ' '.join(args), p.stderr.strip())
            return ''
        return p.stdout.strip()

    async def select_remote(self):
        if self.restore_task:
            self.restore_task.cancel()
            self.restore_task = None
        current = await asyncio.to_thread(self.pactl, 'get-default-source')
        if current and current != REMOTE_SOURCE and not self.previous_source:
            self.previous_source = current
        await asyncio.to_thread(self.pactl, 'set-default-source', REMOTE_SOURCE)
        LOG.info('default source -> %s previous=%s', REMOTE_SOURCE, self.previous_source or 'same')

    async def restore_later(self, delay=2.5):
        if self.restore_task:
            self.restore_task.cancel()
        self.restore_task = asyncio.create_task(self._restore(delay))

    async def _restore(self, delay):
        try:
            await asyncio.sleep(delay)
            if self.previous_source:
                src = self.previous_source
                self.previous_source = None
                await asyncio.to_thread(self.pactl, 'set-default-source', src)
                LOG.info('default source restored -> %s', src)
        except asyncio.CancelledError:
            raise
        finally:
            self.restore_task = None

    async def start_when_ready(self):
        deadline = time.monotonic() + 12
        try:
            while self.button_held and time.monotonic() < deadline:
                # The target ChatGPT tab can be inactive after setup pages; activate it if visible.
                await asyncio.to_thread(activate_target_tab)
                button = await asyncio.to_thread(find_button, START_NAMES)
                if button is not None:
                    ok, action = await asyncio.to_thread(invoke, button)
                    if ok:
                        self.start_clicked = True
                        LOG.info('ChatGPT dictation START action=%s', action)
                        return
                await asyncio.sleep(0.20)
            if self.button_held:
                LOG.warning('ChatGPT dictation START button not found before timeout state=%s', await asyncio.to_thread(button_state))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.exception('start_when_ready failed: %s', exc)

    async def stop_when_ready(self):
        deadline = time.monotonic() + 8
        try:
            while time.monotonic() < deadline:
                button = await asyncio.to_thread(find_button, STOP_NAMES)
                if button is not None:
                    ok, action = await asyncio.to_thread(invoke, button)
                    if ok:
                        LOG.info('ChatGPT dictation STOP action=%s', action)
                        self.start_clicked = False
                        await self.restore_later()
                        return
                # If start never happened and the mic button is visible again, there is nothing to stop.
                if not self.start_clicked and await asyncio.to_thread(find_button, START_NAMES) is not None:
                    LOG.info('dictation never entered recording state; nothing to stop')
                    await self.restore_later(0.2)
                    return
                await asyncio.sleep(0.15)
            LOG.warning('ChatGPT dictation STOP button not found before timeout state=%s', await asyncio.to_thread(button_state))
            self.start_clicked = False
            await self.restore_later()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.exception('stop_when_ready failed: %s', exc)
            await self.restore_later()

    async def voice_start(self):
        self.button_held = True
        await self.select_remote()
        if self.stop_task and not self.stop_task.done():
            self.stop_task.cancel()
        if self.start_task and not self.start_task.done():
            self.start_task.cancel()
        self.start_task = asyncio.create_task(self.start_when_ready())
        LOG.info('remote voice_start')

    async def voice_stop(self):
        self.button_held = False
        # If the click hasn't happened yet, stop it from firing late after release.
        if self.start_task and not self.start_task.done() and not self.start_clicked:
            self.start_task.cancel()
        if self.start_clicked:
            if self.stop_task and not self.stop_task.done():
                self.stop_task.cancel()
            self.stop_task = asyncio.create_task(self.stop_when_ready())
        else:
            await self.restore_later(0.2)
        LOG.info('remote voice_stop start_clicked=%s', self.start_clicked)

    async def follow(self):
        proc = await asyncio.create_subprocess_exec(
            'journalctl', '--user', '-fu', 'xiaomi-remote-mic.service', '-o', 'cat', '--since', 'now',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        LOG.info('following xiaomi-remote-mic.service')
        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    if proc.returncode is not None:
                        raise RuntimeError(f'journalctl exited {proc.returncode}')
                    await asyncio.sleep(.1)
                    continue
                line = raw.decode('utf-8', 'replace')
                if 'ATVV control: audio_start' in line:
                    await self.voice_start()
                elif 'ATVV control: audio_stop' in line:
                    await self.voice_stop()
        finally:
            proc.terminate()
            with suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=2)


async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    LOG.info('AT-SPI bridge starting state=%s', await asyncio.to_thread(button_state))
    bridge = Bridge()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    task = asyncio.create_task(bridge.follow())
    await stop.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

if __name__ == '__main__':
    asyncio.run(main())
