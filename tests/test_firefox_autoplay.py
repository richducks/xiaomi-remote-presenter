"""Firefox autoplay helper must be opt-in and preserve unrelated settings."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "linux/remote-mic/firefox-autoplay.py"
spec = importlib.util.spec_from_file_location("firefox_autoplay", SOURCE)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class FirefoxAutoplayTests(unittest.TestCase):
    def test_select_snap_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "snap/firefox/common/.mozilla/firefox"
            prof = root / "demo.default"
            prof.mkdir(parents=True)
            (root / "profiles.ini").write_text(
                '[Profile0]\nName=default\nIsRelative=1\nPath=demo.default\nDefault=1\n',
                encoding="utf-8",
            )
            self.assertEqual(helper.select_profile(None, Path(tmp)), prof.resolve())

    def test_ambiguous_profiles_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".mozilla/firefox"
            root.mkdir(parents=True)
            (root / "profiles.ini").write_text(
                '[Profile0]\nPath=a\n[Profile1]\nPath=b\n', encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                helper.select_profile(None, Path(tmp))

    def test_preserves_unrelated_and_backup_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            userjs = profile / "user.js"
            initial = (
                '// preserve this comment\n'
                'user_pref("browser.tabs.warnOnClose", true);\n'
                'user_pref("media.autoplay.default", 1);\n'
            )
            userjs.write_text(initial, encoding="utf-8")
            changed, backup = helper.apply(profile)
            self.assertTrue(changed)
            self.assertIsNotNone(backup)
            self.assertEqual(backup.read_text(encoding="utf-8"), initial)
            after = userjs.read_text(encoding="utf-8")
            self.assertIn('user_pref("browser.tabs.warnOnClose", true)', after)
            self.assertEqual(after.count('user_pref("media.autoplay.default", 0);'), 1)
            self.assertEqual(helper.read_prefs(userjs), helper.PREFERENCES)
            self.assertEqual(userjs.stat().st_mode & 0o777, 0o600)
            self.assertEqual(helper.apply(profile), (False, None))
            self.assertEqual(len(list(profile.glob("user.js.xiaomi-backup-*"))), 1)

    def test_no_existing_userjs(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            self.assertEqual(helper.apply(profile), (True, None))
            self.assertEqual(helper.read_prefs(profile / "user.js"), helper.PREFERENCES)

    def test_no_write_on_readonly_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            self.assertEqual(helper.main(["--profile", str(profile)]), 0)
            self.assertFalse((profile / "user.js").exists())


if __name__ == "__main__":
    unittest.main()
