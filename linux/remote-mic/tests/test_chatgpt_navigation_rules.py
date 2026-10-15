"""App-scoped RC003 home/back behavior in the active HID implementation."""
import importlib
import json
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from evdev import ecodes

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
hid = importlib.import_module('video_only_hid')
rules = importlib.import_module('remote_rules')


class FakeRemote:
    path = '/dev/input/test-rc003'
    name = 'Xiaomi RC003'
    info = SimpleNamespace(bustype=5, vendor=hid.VID, product=hid.PID, version=1)

    def __init__(self, keys):
        self.keys = keys

    async def async_read_loop(self):
        for code, value in self.keys:
            yield SimpleNamespace(type=ecodes.EV_KEY, code=code, value=value)

    def grab(self): pass
    def ungrab(self): pass
    def close(self): pass


class FakeUI:
    def __init__(self):
        self.writes = []
        self.forwarded = []

    def write(self, kind, key, value):
        self.writes.append((kind, key, value))

    def syn(self): pass

    def write_event(self, event):
        self.forwarded.append((event.type, event.code, event.value))

    def close(self): pass


def chord(modifier, key):
    return [
        (ecodes.EV_KEY, modifier, 1),
        (ecodes.EV_KEY, key, 1),
        (ecodes.EV_KEY, key, 0),
        (ecodes.EV_KEY, modifier, 0),
    ]


class ChatGPTNavigationRules(unittest.IsolatedAsyncioTestCase):
    async def run_keys(self, keys, *, chatgpt=False, browser=True, wps=False):
        ui = FakeUI()
        actions = []

        def emit(name):
            actions.append(name)
            return True

        with patch.object(hid.UInput, 'from_device', return_value=ui), \
             patch.object(hid, 'chatgpt_window_focused', return_value=chatgpt), \
             patch.object(hid, 'browser_window_focused', return_value=browser), \
             patch.object(hid, 'wps_presentation_focused', return_value=wps), \
             patch.object(hid, 'browser_media_tab_focused', return_value=False), \
             patch.object(hid, 'firefox_pip_focused', return_value=False), \
             patch.object(hid, 'chatgpt_draft_ready', return_value=False), \
             patch.object(hid, 'toggle_browser_play_pause', return_value=False), \
             patch.object(hid, 'youtube_video_tab_focused', return_value=False), \
             patch.object(hid, 'key_sleep', return_value=None), \
             patch.object(hid, 'emit_chatgpt_action', side_effect=emit):
            await hid.forward_device(FakeRemote(keys))
        return ui, actions

    def test_default_and_live_rules_match(self):
        config = json.loads((ROOT / 'remote_rules.json').read_text())
        loaded = rules.validate(config)
        for home in (ecodes.KEY_HOME, ecodes.KEY_HOMEPAGE, ecodes.KEY_WWW):
            self.assertEqual([r.scope for r in loaded[home]], ['browser'])
            self.assertEqual(loaded[home][0].key_code, ecodes.KEY_T)
        back = loaded[ecodes.KEY_BACK]
        self.assertEqual([r.scope for r in back], ['wps', 'chatgpt', 'browser'])
        self.assertEqual(back[1].action, 'new_chat')
        self.assertEqual(back[2].key_code, ecodes.KEY_LEFT)
        self.assertEqual(rules.validate({'version': 1, 'rules': rules.DEFAULT_RULES}), loaded)

    async def test_system_layer_events_never_consult_application_focus(self):
        for profile in (dict(chatgpt=True),dict(browser=True),dict(wps=True)):
            keys=[]
            for code in (ecodes.KEY_POWER,ecodes.KEY_SLEEP,
                         ecodes.KEY_VOLUMEUP,ecodes.KEY_VOLUMEDOWN,
                         ecodes.KEY_MUTE,ecodes.KEY_BRIGHTNESSUP,
                         ecodes.KEY_BRIGHTNESSDOWN):
                keys += [(code,1),(code,2),(code,0)]
            ui, actions=await self.run_keys(keys,**profile)
            self.assertEqual(ui.writes,[])
            self.assertEqual(ui.forwarded,[(ecodes.EV_KEY,key,value) for key,value in keys])
            self.assertEqual(actions,[])

    async def test_home_in_chatgpt_opens_exactly_one_tab(self):
        for home in (ecodes.KEY_HOME, ecodes.KEY_HOMEPAGE, ecodes.KEY_WWW):
            with self.subTest(home=home):
                ui, actions = await self.run_keys([(home, 1), (home, 2), (home, 0)], chatgpt=True)
                self.assertEqual(ui.writes, chord(ecodes.KEY_LEFTCTRL, ecodes.KEY_T))
                self.assertEqual(ui.forwarded, [])
                self.assertEqual(actions, [])

    async def test_home_and_www_dual_event_creates_one_tab(self):
        ui, actions = await self.run_keys([
            (ecodes.KEY_HOME, 1), (ecodes.KEY_WWW, 1),
            (ecodes.KEY_HOME, 0), (ecodes.KEY_WWW, 0),
        ], chatgpt=True)
        self.assertEqual(ui.writes, chord(ecodes.KEY_LEFTCTRL, ecodes.KEY_T))
        self.assertEqual(actions, [])

    async def test_back_in_chatgpt_queues_one_new_chat(self):
        ui, actions = await self.run_keys([
            (ecodes.KEY_BACK, 1), (ecodes.KEY_BACK, 2),
            (ecodes.KEY_BACK, 2), (ecodes.KEY_BACK, 0),
        ], chatgpt=True)
        self.assertEqual(ui.writes, [])
        self.assertEqual(ui.forwarded, [])
        self.assertEqual(actions, ['new_chat'])

    async def test_back_in_other_browser_remains_history_back(self):
        ui, actions = await self.run_keys([
            (ecodes.KEY_BACK, 1), (ecodes.KEY_BACK, 0),
        ], browser=True)
        self.assertEqual(ui.writes, chord(ecodes.KEY_LEFTALT, ecodes.KEY_LEFT))
        self.assertEqual(actions, [])

    async def test_back_in_wps_remains_escape(self):
        ui, actions = await self.run_keys([
            (ecodes.KEY_BACK, 1), (ecodes.KEY_BACK, 0),
        ], browser=False, wps=True)
        self.assertEqual(ui.writes, [
            (ecodes.EV_KEY, ecodes.KEY_ESC, 1),
            (ecodes.EV_KEY, ecodes.KEY_ESC, 0),
        ])
        self.assertEqual(actions, [])

    async def test_other_app_receives_original_keys(self):
        keys = [
            (ecodes.KEY_BACK, 1), (ecodes.KEY_BACK, 0),
            (ecodes.KEY_HOME, 1), (ecodes.KEY_HOME, 0),
        ]
        ui, actions = await self.run_keys(keys, browser=False)
        self.assertEqual(ui.writes, [])
        self.assertEqual(ui.forwarded, [(ecodes.EV_KEY, *pair) for pair in keys])
        self.assertEqual(actions, [])


if __name__ == '__main__':
    unittest.main()
