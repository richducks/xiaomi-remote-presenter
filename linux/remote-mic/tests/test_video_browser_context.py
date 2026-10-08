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

    def test_home_close_supported_standalone_browsers(self):
        for app in (
            "Firefox", "Mozilla Firefox", "Firefox Nightly",
            "Google Chrome", "Chromium", "Microsoft Edge",
            "Brave Browser", "Opera", "Opera GX", "Vivaldi",
            "LibreWolf", "Waterfox", "Floorp", "Zen Browser",
            "Tor Browser", "GNOME Web", "Epiphany", "Falkon",
            "qutebrowser", "Midori",
        ):
            with self.subTest(app=app):
                self.assertTrue(ctx.is_browser_application(app))
        for other in ("wechat", "Codex", "WPS Office", "Files", "GNOME Terminal",
                      "Firefox Issue - Terminal", "Browser Downloader",
                      "Web Browser Demo"):
            with self.subTest(non_browser=other):
                self.assertFalse(ctx.is_browser_application(other))

    def test_home_close_browser_detection_requires_active_frame(self):
        import sys
        from unittest.mock import patch
        desktop=MagicMock()
        atspi=MagicMock()
        atspi.StateType.ACTIVE=999
        active=MagicMock()
        active.get_role_name.return_value='frame'
        active.get_state_set.return_value.contains.return_value=True
        browser=MagicMock()
        browser.get_name.return_value='Microsoft Edge'
        browser.get_child_count.return_value=1
        browser.get_child_at_index.return_value=active
        desktop.get_child_count.return_value=1
        desktop.get_child_at_index.return_value=browser
        gi=MagicMock()
        gi.repository.Atspi=atspi
        atspi.get_desktop.return_value=desktop
        with patch.dict(sys.modules,{"gi":gi,"gi.repository":gi.repository}):
            self.assertTrue(ctx.browser_window_focused())
            active.get_state_set.return_value.contains.return_value=False
            self.assertFalse(ctx.browser_window_focused())
            active.get_state_set.return_value.contains.return_value=True
            browser.get_name.return_value='wechat'
            self.assertFalse(ctx.browser_window_focused())

    def test_youtube_fallback_requires_foreground_watch_title_not_userscript(self):
        import sys
        from unittest.mock import patch
        desktop=MagicMock()
        atspi=MagicMock()
        atspi.StateType.ACTIVE=5
        atspi.StateType.FOCUSED=6
        atspi.StateType.EDITABLE=7
        frame=MagicMock()
        frame.get_role_name.return_value='frame'
        frame.get_state_set.return_value.contains.side_effect = (
            lambda state: state == atspi.StateType.ACTIVE
        )
        frame.get_child_count.return_value=0
        app=MagicMock()
        app.get_name.return_value='Firefox'
        app.get_child_count.return_value=1
        app.get_child_at_index.return_value=frame
        desktop.get_child_count.return_value=1
        desktop.get_child_at_index.return_value=app
        atspi.get_desktop.return_value=desktop
        gi=MagicMock()
        gi.repository.Atspi=atspi
        youtube=('firefox','【全集】中文标题 - YouTube — Mozilla Firefox')
        with patch.dict(sys.modules,{'gi':gi,'gi.repository':gi.repository}),\
             patch.object(ctx,'active_browser_window',return_value=youtube),\
             patch.object(ctx,'browser_media_tab_focused',return_value=True):
            self.assertTrue(ctx.youtube_video_tab_focused())
            # Chrome and Firefox both work even without the optional
            # video userscript, and when translated titles mismatch MPRIS.
            with patch.object(ctx,'browser_media_tab_focused',return_value=False):
                self.assertTrue(ctx.youtube_video_tab_focused())
            with patch.object(ctx,'active_browser_window',
                              return_value=('firefox','YouTube — Mozilla Firefox')):
                self.assertFalse(ctx.youtube_video_tab_focused())
            with patch.object(ctx,'active_browser_window',
                              return_value=('firefox','Settings — Mozilla Firefox')):
                self.assertFalse(ctx.youtube_video_tab_focused())
            with patch.object(ctx,'active_browser_window',
                              return_value=('firefox','YouTube Music — Mozilla Firefox')):
                self.assertFalse(ctx.youtube_video_tab_focused())
            with patch.object(ctx,'active_browser_window',
                              return_value=('firefox','Song - YouTube Music — Mozilla Firefox')):
                self.assertFalse(ctx.youtube_video_tab_focused())
            with patch.object(ctx,'active_browser_window',
                              return_value=('chromium','Video - YouTube - Google Chrome')):
                self.assertTrue(ctx.youtube_video_tab_focused())

    def test_youtube_fallback_never_types_k_in_focused_search(self):
        import sys
        from unittest.mock import patch
        desktop=MagicMock()
        atspi=MagicMock()
        atspi.StateType.ACTIVE=5
        atspi.StateType.FOCUSED=6
        atspi.StateType.EDITABLE=7
        focused=MagicMock()
        focused.get_role_name.return_value='entry'
        focused.get_state_set.return_value.contains.return_value=True
        focused.get_child_count.return_value=0
        frame=MagicMock()
        frame.get_role_name.return_value='frame'
        frame.get_state_set.return_value.contains.return_value=True
        frame.get_child_count.return_value=1
        frame.get_child_at_index.return_value=focused
        app=MagicMock()
        app.get_name.return_value='Firefox'
        app.get_child_count.return_value=1
        app.get_child_at_index.return_value=frame
        desktop.get_child_count.return_value=1
        desktop.get_child_at_index.return_value=app
        atspi.get_desktop.return_value=desktop
        gi=MagicMock()
        gi.repository.Atspi=atspi
        with patch.dict(sys.modules,{'gi':gi,'gi.repository':gi.repository}),\
             patch.object(ctx,'active_browser_window',
                          return_value=('firefox','Video - YouTube — Mozilla Firefox')),\
             patch.object(ctx,'browser_media_tab_focused',return_value=True):
            self.assertFalse(ctx.youtube_video_tab_focused())

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
