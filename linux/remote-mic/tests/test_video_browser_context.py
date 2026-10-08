import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock

P = pathlib.Path(__file__).resolve().parents[1] / "video_browser_context.py"
spec = importlib.util.spec_from_file_location("video_browser_context", P)
ctx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctx)


class VideoBrowserContextTests(unittest.TestCase):
    def test_playing_video_title_matches_current_browser_tab(self):
        self.assertTrue(ctx.media_title_matches_window(
            "夸克网盘 - 正在播放音频 - Google Chrome", "夸克网盘", "Playing"))
        self.assertTrue(ctx.media_title_matches_window(
            "Some Video - YouTube — Mozilla Firefox", "Some Video", "Paused"))
    def test_background_player_is_not_current_tab(self):
        self.assertFalse(ctx.media_title_matches_window(
            "修改音量键功能 - Google Chrome", "夸克网盘", "Playing"))
    def test_stopped_and_short_title_leave_volume_intact(self):
        self.assertFalse(ctx.media_title_matches_window(
            "Example Video - Google Chrome", "Example Video", "Stopped"))
        self.assertFalse(ctx.media_title_matches_window(
            "DJ - Google Chrome", "DJ", "Playing"))
    def test_firefox_pip_window_titles(self):
        self.assertTrue(ctx.is_firefox_pip_window('firefox','画中画'))
        self.assertTrue(ctx.is_firefox_pip_window('firefox','Picture-in-Picture'))
        self.assertFalse(ctx.is_firefox_pip_window('firefox','夸克网盘 — Mozilla Firefox'))
        self.assertFalse(ctx.is_firefox_pip_window('chromium','画中画'))

    def test_active_browser_selection(self):
        states = MagicMock()
        atspi = MagicMock()
        atspi.StateType.ACTIVE = 1
        frame = MagicMock()
        frame.get_role_name.return_value = "frame"
        frame.get_name.return_value = "Video - Firefox"
        frame.get_state_set.return_value.contains.return_value = True
        app = MagicMock()
        app.get_name.return_value = "Firefox"
        app.get_child_count.return_value = 1
        app.get_child_at_index.return_value = frame
        desktop = MagicMock()
        desktop.get_child_count.return_value = 1
        desktop.get_child_at_index.return_value = app
        self.assertEqual(ctx.active_browser_window(desktop, atspi),
                         ("firefox", "Video - Firefox"))
        frame.get_state_set.return_value.contains.return_value = False
        self.assertIsNone(ctx.active_browser_window(desktop, atspi))


if __name__ == "__main__":
    unittest.main()
