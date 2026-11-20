"""Regressions: fast compositor path must never allocate an AT-SPI tree."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

SOURCE = Path(__file__).resolve().parents[1] / "video_browser_context.py"
spec = importlib.util.spec_from_file_location("focus_fastpath_under_test", SOURCE)
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class MemorySafeFocusTests(unittest.TestCase):
    def test_compositor_focus_does_not_initialize_accessibility(self):
        with patch.object(context, "_compositor_window", return_value=(
            "firefox_firefox.desktop", "firefox", "画中画"
        )), patch.object(context, "_foreground_frame",
                        side_effect=AssertionError("AT-SPI walked")):
            self.assertEqual(context.active_browser_window(), ("firefox", "画中画"))
            self.assertTrue(context.firefox_pip_focused())

    def test_non_youtube_does_not_walk_large_accessibility_tree(self):
        gi = MagicMock()
        gi.repository.Atspi.get_desktop.side_effect = AssertionError(
            "Unexpected AT-SPI desktop traversal"
        )
        with patch.dict(sys.modules, {"gi": gi, "gi.repository": gi.repository}), \
             patch.object(context, "_compositor_window", return_value=(
                 "firefox_firefox.desktop", "firefox", "Quark — Mozilla Firefox"
             )):
            self.assertFalse(context.youtube_video_tab_focused())
            self.assertFalse(context.firefox_pip_focused())
            gi.repository.Atspi.get_desktop.assert_not_called()

    def test_media_lookup_uses_compositor_without_atspi(self):
        gi = MagicMock()
        gi.repository.Atspi.get_desktop.side_effect = AssertionError(
            "MPRIS must not open AT-SPI when compositor is available"
        )
        gi.repository.Gio.bus_get_sync.return_value.call_sync.return_value.unpack.return_value = ([],)
        with patch.dict(sys.modules, {"gi": gi, "gi.repository": gi.repository}), \
             patch.object(context, "_compositor_window", return_value=(
                 "firefox_firefox.desktop", "firefox",
                 "Example - YouTube — Mozilla Firefox"
             )):
            self.assertIsNone(context.active_browser_media_session())
            gi.repository.Atspi.get_desktop.assert_not_called()

    def test_unavailable_compositor_keeps_legacy_fail_closed_fallback(self):
        gi = MagicMock()
        gi.repository.Atspi.get_desktop.return_value.get_child_count.return_value = 0
        with patch.dict(sys.modules, {"gi": gi, "gi.repository": gi.repository}), \
             patch.object(context, "_compositor_window", return_value=None):
            self.assertIsNone(context.active_browser_window())
            gi.repository.Atspi.get_desktop.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
