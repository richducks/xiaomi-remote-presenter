"""Safety and hot-reload regression tests for JSON remote rules."""
import json
import pathlib
import tempfile
import unittest
import sys
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from evdev import ecodes

from remote_rules import DEFAULT_RULES, RuleBook, validate, check
import video_only_hid as video

from test_video_only_hid import FakeRemote, FakeUInput


class RulesValidationTests(unittest.TestCase):
    def test_checked_in_configuration_matches_stable_fallback(self):
        path = pathlib.Path(__file__).parents[1] / "remote_rules.json"
        contents = json.loads(path.read_text())
        self.assertEqual(contents, {"version": 1, "rules": DEFAULT_RULES})
        self.assertEqual(check(path), 0)

    def test_app_isolation_and_default_rule_count(self):
        rules = validate({"version": 1, "rules": DEFAULT_RULES})
        self.assertEqual(sum(map(len, rules.values())), 13)
        self.assertEqual(rules[ecodes.KEY_ENTER][0].scope, "wps")
        self.assertEqual(rules[ecodes.KEY_BACK][0].scope, "wps")
        self.assertEqual(rules[ecodes.KEY_BACK][1].scope, "browser")
        self.assertEqual(rules[ecodes.KEY_HOME][0].scope, "chatgpt")
        self.assertEqual(rules[ecodes.KEY_HOME][1].scope, "browser")
        self.assertEqual(rules[ecodes.KEY_GRAVE][0].action, "send")

    def test_rejects_global_and_browser_enter(self):
        for rule in [
            {"id": "oops", "scope": "global", "input": "KEY_ENTER", "tap": "KEY_F5"},
            {"id": "oops", "scope": "browser", "input": "KEY_ENTER", "tap": "KEY_F5"},
            {"id": "oops", "scope": "browser", "input": "KEY_F5", "tap": "KEY_ENTER"},
        ]:
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                validate({"version": 1, "rules": [rule]})

    def test_system_volume_cannot_be_stolen_by_app_rules(self):
        for volume_key in ("KEY_VOLUMEUP", "KEY_VOLUMEDOWN", "KEY_MUTE"):
            for scope in ("wps", "browser", "chatgpt"):
                with self.subTest(volume=volume_key, scope=scope):
                    rule = {"id": "bad-volume", "scope": scope,
                            "input": volume_key,
                            "action": "voice_toggle"} if scope == "chatgpt" else {
                                "id": "bad-volume", "scope": scope,
                                "input": volume_key, "tap": "KEY_SPACE"}
                    with self.assertRaises(ValueError):
                        validate({"version": 1, "rules": [rule]})

    def test_rejects_bad_schema_unsafe_execution_and_duplicate(self):
        existing = dict(DEFAULT_RULES[0])
        bad = [
            {"version": 2, "rules": []},
            {"version": 1, "rules": [existing, existing]},
            {"version": 1, "rules": [{**existing, "shell": "rm -rf /"}]},
            {"version": 1, "rules": [{**existing, "tap": "KEY_DOES_NOT_EXIST"}]},
            {"version": 1, "rules": [{**existing, "cooldown_ms": -1}]},
            {"version": 1, "rules": [{**existing, "cooldown_ms": True}]},
        ]
        for config in bad:
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate(config)

    def test_rejects_arbitrary_web_actions(self):
        cases = [
            {"id":"bad", "scope":"chatgpt", "input":"KEY_HOME", "action":"arbitrary_command"},
            {"id":"bad", "scope":"browser", "input":"KEY_HOME", "action":"send"},
            {"id":"bad", "scope":"chatgpt", "input":"KEY_HOME", "shortcut":["KEY_LEFTCTRL","KEY_T"]},
        ]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate({"version":1, "rules":[bad]})

    def test_file_hot_reload_keeps_last_good_on_invalid_edit(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "rules.json"
            book = RuleBook(path)
            self.assertTrue(book.candidates(ecodes.KEY_HOME))
            path.write_text('{"version":1,"rules":[]}')
            book.refresh(force=True)
            self.assertFalse(book.candidates(ecodes.KEY_HOME))
            path.write_text('{"version":1,broken')
            book.refresh(force=True)
            self.assertFalse(book.candidates(ecodes.KEY_HOME))
            path.write_text(json.dumps({"version": 1, "rules": [DEFAULT_RULES[4]]}))
            book.refresh(force=True)
            self.assertEqual(book.candidates(ecodes.KEY_HOME)[0].id, "browser-home")
            path.unlink()
            book.refresh(force=True)
            self.assertEqual(book.candidates(ecodes.KEY_HOME)[0].id, "browser-home")


class RulesRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_chatgpt_rules_take_priority_without_using_system_enter(self):
        dev = FakeRemote([(ecodes.KEY_HOME,1),(ecodes.KEY_HOME,0),
                          (ecodes.KEY_COMPOSE,1),(ecodes.KEY_COMPOSE,0),
                          (ecodes.KEY_GRAVE,1),(ecodes.KEY_GRAVE,0)])
        ui = FakeUInput()
        queued=[]
        with patch.object(video.UInput, "from_device", return_value=ui), \
             patch.object(video, "browser_window_focused", return_value=True), \
             patch.object(video, "wps_presentation_focused", return_value=False), \
             patch.object(video, "chatgpt_window_focused", return_value=True), \
             patch.object(video, "emit_chatgpt_action", side_effect=lambda x: queued.append(x) or True):
            await video.forward_device(dev)
        # Menu must navigate tabs, never launch voice dictation.
        self.assertEqual(queued, ["new_chat", "send"])
        self.assertEqual(ui.written, [
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
            (ecodes.EV_KEY, ecodes.KEY_TAB, 1),
            (ecodes.EV_KEY, ecodes.KEY_TAB, 0),
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
        ])
        self.assertEqual(ui.forwarded, [])

    async def test_non_chatgpt_browser_shortcuts_still_work(self):
        dev=FakeRemote([(ecodes.KEY_HOME,1),(ecodes.KEY_HOME,0)])
        ui=FakeUInput()
        with patch.object(video.UInput, "from_device", return_value=ui), \
             patch.object(video, "browser_window_focused", return_value=True), \
             patch.object(video, "wps_presentation_focused", return_value=False), \
             patch.object(video, "chatgpt_window_focused", return_value=False), \
             patch.object(video, "emit_chatgpt_action", side_effect=AssertionError("must not send")):
            await video.forward_device(dev)
        self.assertEqual(ui.written[1],(ecodes.EV_KEY,ecodes.KEY_T,1))
        self.assertEqual(ui.forwarded, [])

    async def test_failed_web_action_does_not_fallback_to_close_tab(self):
        dev=FakeRemote([(ecodes.KEY_GRAVE,1),(ecodes.KEY_GRAVE,0)])
        ui=FakeUInput()
        with patch.object(video.UInput, "from_device", return_value=ui), \
             patch.object(video, "chatgpt_window_focused", return_value=True), \
             patch.object(video, "emit_chatgpt_action", return_value=False):
            await video.forward_device(dev)
        self.assertEqual(ui.written, [])
        self.assertEqual(ui.forwarded, [])

    async def test_json_changes_browser_home_and_wps_without_other_keys(self):
        custom = {"version": 1, "rules": [
            {"id": "browser-home-custom", "scope": "browser", "input": "KEY_HOME", "shortcut": ["KEY_LEFTCTRL", "KEY_W"]},
            {"id": "wps-ok-custom", "scope": "wps", "input": "KEY_ENTER", "tap": "KEY_ESC"},
        ]}
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "my-rules.json"
            p.write_text(json.dumps(custom))
            book = RuleBook(p)
            keys = [(ecodes.KEY_HOME, 1), (ecodes.KEY_HOME, 2), (ecodes.KEY_HOME, 0),
                    (ecodes.KEY_ENTER, 1), (ecodes.KEY_ENTER, 0)]
            dev = FakeRemote(keys)
            ui = FakeUInput()
            with patch.object(video, "RuleBook", return_value=book), \
                 patch.object(video.UInput, "from_device", return_value=ui), \
                 patch.object(video, "browser_window_focused", return_value=True), \
                 patch.object(video, "wps_presentation_focused", return_value=False), \
                 patch.object(video, "toggle_browser_play_pause", return_value=False), \
                 patch.object(video, "youtube_video_tab_focused", return_value=False):
                await video.forward_device(dev)
            self.assertEqual(ui.written, [
                (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
                (ecodes.EV_KEY, ecodes.KEY_W, 1),
                (ecodes.EV_KEY, ecodes.KEY_W, 0),
                (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
            ])
            self.assertEqual(ui.forwarded, [(ecodes.KEY_ENTER, 1), (ecodes.KEY_ENTER, 0)])
            self.assertTrue(ui.closed)

    async def test_empty_rules_disable_shortcuts_without_disabling_video(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "empty.json"
            p.write_text('{"version":1,"rules":[]}')
            dev = FakeRemote([(ecodes.KEY_HOME, 1), (ecodes.KEY_HOME, 0),
                              (ecodes.KEY_ENTER, 1), (ecodes.KEY_ENTER, 0)])
            ui = FakeUInput()
            with patch.object(video, "RuleBook", return_value=RuleBook(p)), \
                 patch.object(video.UInput, "from_device", return_value=ui), \
                 patch.object(video, "browser_window_focused", return_value=True), \
                 patch.object(video, "toggle_browser_play_pause", return_value=True):
                await video.forward_device(dev)
            self.assertEqual(ui.forwarded, [(ecodes.KEY_HOME, 1), (ecodes.KEY_HOME, 0)])
            self.assertEqual(ui.written, [])


if __name__ == "__main__":
    unittest.main()
