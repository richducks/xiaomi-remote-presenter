"""Cross-platform Xiaomi HID mapping contract (static, machine-independent).

Linux input has been tested on Ubuntu; this test does NOT claim actual
Windows/macOS Bluetooth or input-injection validation.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "macos"))
import build_rules


class CrossPlatformMappings(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.windows = (ROOT / "windows/xiaomi_remote_presenter.ahk").read_text()
        cls.win_safe = (ROOT / "windows/xiaomi_remote_safe.ahk").read_text()
        cls.linux = (ROOT / "linux/remote-mic/remote_hid_filter.py").read_text()
        cls.linux_safe = (ROOT / "linux/remote-mic/video_only_hid.py").read_text()
        cls.core = json.loads((ROOT / "macos/xiaomi-remote-presenter.json").read_text())
        cls.safe = json.loads((ROOT / "macos/xiaomi-remote-safe.json").read_text())
        cls.video_ok = json.loads((ROOT / "macos/xiaomi-remote-video-ok.json").read_text())
        cls.speed = json.loads((ROOT / "macos/xiaomi-remote-video-speed.json").read_text())
        cls.browser_script = (ROOT / "browser/xiaomi-remote-video.user.js").read_text()
        cls.manual = (ROOT / "docs/中文使用手册.md").read_text()

    def test_mac_json_is_reproducible_not_hand_drifted(self):
        self.assertEqual(self.core, build_rules.build_core())
        self.assertEqual(self.safe, build_rules.build_safe())
        self.assertEqual(self.video_ok, build_rules.build_optional_video_ok())
        self.assertEqual(self.speed, build_rules.build_optional_speed())

    def test_mac_all_mappings_are_xiaomi_only(self):
        for data in (self.core, self.safe, self.video_ok, self.speed):
            for rule in data["rules"]:
                for item in rule["manipulators"]:
                    devices = [condition for condition in item.get("conditions", [])
                               if condition["type"] == "device_if"]
                    self.assertEqual(len(devices), 1, rule["description"])
                    self.assertEqual(devices[0]["identifiers"],
                                     [{"vendor_id": 0x2717, "product_id": 0x32B8}])
                    if "to" in item:
                        self.assertTrue(all(action.get("repeat") is False
                                            for action in item["to"]))

    def mac_mapping(self, description_substring, input_key):
        matches = [rule for rule in self.core["rules"]
                   if description_substring in rule["description"]]
        self.assertEqual(len(matches), 1, description_substring)
        rule = matches[0]
        candidate = [item for item in rule["manipulators"]
                     if input_key in item["from"].values()]
        self.assertEqual(len(candidate), 1, (description_substring, input_key))
        item = candidate[0]
        self.assertTrue(any(c["type"] == "frontmost_application_if"
                            for c in item["conditions"]))
        return item["to"][0]

    def test_safe_macos_only_three_browser_shortcuts(self):
        self.assertEqual(len(self.safe["rules"]), 3)
        for rule in self.safe["rules"]:
            for item in rule["manipulators"]:
                self.assertTrue(any(c["type"] == "frontmost_application_if"
                                    for c in item["conditions"]))
        s = json.dumps(self.safe)
        for forbidden in ('"return_or_enter"', '"ac_back"', '"f5"', '"up_arrow"'):
            self.assertNotIn(forbidden, s)
        for key, target in (("home", "t"), ("grave_accent_and_tilde", "w"),
                            ("application", "tab")):
            result = [r["to"][0] for rule in self.safe["rules"]
                      for r in rule["manipulators"]
                      if r["from"].get("key_code") == key]
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["key_code"], target)

    def test_safe_windows_limits_enter_to_video_page_and_not_wps(self):
        for marker in (
            "#HotIf RemoteContext.IsActive && IsBrowser()",
            "#HotIf RemoteContext.IsActive && IsVideoPage()",
            'Home::SendOnce("Home", "^t")',
            'SC029::SendOnce("SC029", "^w")',
            'AppsKey::SendOnce("AppsKey", "^{Tab}")',
            'Enter::SendOnce("Enter", "{F13}")',
        ):
            self.assertIn(marker, self.win_safe)
        self.assertNotIn("IsPresentationEditor()", self.win_safe)
        self.assertNotIn("Browser_Back::", self.win_safe)
        self.assertNotIn('Enter::SendOnce("Enter", "{F5}")', self.win_safe)
        installer = (ROOT / "windows/install.ps1").read_text()
        self.assertIn("xiaomi_remote_safe.ahk", installer)
        self.assertIn("[switch]$FullMode", installer)

    def test_linux_safe_has_browser_mapping_without_enter_override(self):
        self.assertIn("BROWSER_TAB_KEYS", self.linux_safe)
        self.assertIn("browser_window_focused", self.linux_safe)
        self.assertIn("ui.write_event(event)", self.linux_safe)
        self.assertNotIn("ensure_wps_editor_focus", self.linux_safe)

    def test_mac_browser_shortcuts(self):
        self.assertEqual(self.mac_mapping("小房子新建", "home")["key_code"], "t")
        self.assertEqual(self.mac_mapping("小房子新建", "home")["modifiers"], ["left_command"])
        self.assertEqual(self.mac_mapping("小房子新建", "ac_home")["key_code"], "t")
        self.assertEqual(self.mac_mapping("TV 关闭", "grave_accent_and_tilde")["key_code"], "w")
        self.assertEqual(self.mac_mapping("TV 关闭", "grave_accent_and_tilde")["modifiers"], ["left_command"])
        self.assertEqual(self.mac_mapping("三横杠菜单", "application")["key_code"], "tab")
        self.assertEqual(self.mac_mapping("三横杠菜单", "application")["modifiers"], ["left_control"])
        self.assertEqual(self.mac_mapping("返回键访问上一页", "ac_back")["key_code"], "open_bracket")
        self.assertEqual(self.mac_mapping("返回键访问上一页", "ac_back")["modifiers"], ["left_command"])
        self.assertEqual(self.mac_mapping("OK -> F13", "return_or_enter")["key_code"], "f13")

    def test_mac_presentation_and_speed_are_independent(self):
        rules = self.core["rules"]
        self.assertEqual(self.mac_mapping("返回键退出放映", "ac_back")["key_code"], "escape")
        self.assertEqual(self.mac_mapping("WPS: OK", "return_or_enter")["key_code"], "f5")
        core_text = json.dumps(self.core)
        self.assertNotIn('"up_arrow"', core_text)
        self.assertNotIn('"down_arrow"', core_text)
        assert len(self.speed["rules"]) == 2
        speed_targets = {item["to"][0]["key_code"]
                         for rule in self.speed["rules"]
                         for item in rule["manipulators"]}
        self.assertEqual(speed_targets, {"d", "a"})

    def test_windows_context_and_shortcuts(self):
        self.assertIn("AHI.GetKeyboardId(VID, PID, 1)", self.windows)
        self.assertIn("AHI.CreateContextManager(KeyboardId)", self.windows)
        self.assertIn("#HotIf RemoteContext.IsActive && IsBrowser()", self.windows)
        self.assertIn("#HotIf RemoteContext.IsActive && IsPresentationEditor()", self.windows)
        for binding in (
            'Home::SendOnce("Home", "^t")',
            'Browser_Home::SendOnce("Browser_Home", "^t")',
            'SC029::SendOnce("SC029", "^w")',
            'AppsKey::SendOnce("AppsKey", "^{Tab}")',
            'Browser_Back::SendOnce("Browser_Back", "!{Left}")',
            'Browser_Back::SendOnce("Browser_Back", "{Esc}")',
            'Enter::SendOnce("Enter", "{F13}")',
            'Enter::SendOnce("Enter", "{F5}")',
            'Up::SendOnce("Up", "d")',
            'Down::SendOnce("Down", "a")',
        ):
            self.assertIn(binding, self.windows)
        self.assertIn("KeyWait(keyName)", self.windows)
        self.assertIn("#HotIf RemoteContext.IsActive && IsVideoPage()", self.windows)

    def test_linux_original_mappings_remain_unchanged(self):
        for expected in (
            "BACK_KEYS = {ecodes.KEY_BACK}",
            "NEW_TAB_KEYS = HOME_KEYS",
            "CLOSE_TAB_KEYS = TV_KEYS",
            "MENU_KEYS = {ecodes.KEY_COMPOSE}",
            "ecodes.KEY_LEFTALT",
            "ecodes.KEY_LEFT",
            "ecodes.KEY_T",
            "ecodes.KEY_W",
            "ecodes.KEY_D",
            "ecodes.KEY_A",
        ):
            self.assertIn(expected, self.linux)

    def test_browser_ok_is_device_scoped_and_not_a_speed_engine(self):
        self.assertIn("event.code !== \"F13\"", self.browser_script)
        self.assertIn("event.isTrusted", self.browser_script)
        self.assertIn("focusIsEditable()", self.browser_script)
        self.assertIn("video.play()", self.browser_script)
        self.assertIn("video.pause()", self.browser_script)
        self.assertNotRegex(self.browser_script, r"\bplaybackRate\s*=")
        self.assertTrue((ROOT / "browser/tests/video-ok.test.cjs").is_file())

    def test_docs_are_chinese_and_cover_all_platforms(self):
        for phrase in ("Windows", "macOS", "Linux", "小房子", "Global Speed",
                       "TV", "菜单", "返回", "两轮验收", "未", "GitHub"):
            self.assertIn(phrase, self.manual)
        for target in ("windows/README.md", "macos/README.md", "linux/remote-mic/README.md"):
            self.assertTrue((ROOT / target).is_file())


if __name__ == "__main__":
    unittest.main()
