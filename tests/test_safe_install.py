"""Mac SAFE profile auto-install: preserve existing settings and remain idempotent."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "macos"))
import enable_safe
import build_rules


class MacSafeInstallTests(unittest.TestCase):
    def test_safe_profile_has_browser_only_device_guard(self):
        data=build_rules.build_safe()
        self.assertEqual(len(data["rules"]),3)
        for rule in data["rules"]:
            for manip in rule["manipulators"]:
                types=[c["type"] for c in manip["conditions"]]
                self.assertIn("device_if",types)
                self.assertIn("frontmost_application_if",types)
                self.assertNotIn("return_or_enter",json.dumps(manip))
        keys=json.dumps(data)
        for code in ("home","grave_accent_and_tilde","application"):
            self.assertIn(code,keys)

    def test_install_safe_preserves_other_rules_and_backups_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            config=folder/"karabiner.json"
            source=folder/"safe.json"
            source.write_text(json.dumps(build_rules.build_safe()),encoding="utf-8")
            original={"global":{"check_for_updates_on_startup":True},
                     "profiles":[{"selected":True,
                                  "complex_modifications":{"rules":[
                                      {"description":"Unrelated custom rule","manipulators":[]}
                                  ]}},
                                 {"selected":False,"complex_modifications":{"rules":[]}}]}
            config.write_text(json.dumps(original),encoding="utf-8")
            backup,count=enable_safe.apply_safe(config,source)
            self.assertEqual(count,3)
            self.assertEqual(json.loads(backup.read_text()),original)
            updated=json.loads(config.read_text())
            rules=updated["profiles"][0]["complex_modifications"]["rules"]
            self.assertEqual(len(rules),4)
            self.assertEqual(rules[0]["description"],"Unrelated custom rule")
            self.assertEqual(updated["profiles"][1],original["profiles"][1])
            again,count=enable_safe.apply_safe(config,source)
            self.assertEqual(count,0)
            self.assertEqual(again,config)
            self.assertEqual(len(list(folder.glob("karabiner.json.xiaomi-backup-*"))),1)

    def test_install_no_profiles_fails_without_changing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/"karabiner.json"
            config.write_text('{"profiles":[]}')
            with self.assertRaises(ValueError):
                enable_safe.apply_safe(config)
            self.assertEqual(config.read_text(),'{"profiles":[]}')


if __name__=="__main__":
    unittest.main()
