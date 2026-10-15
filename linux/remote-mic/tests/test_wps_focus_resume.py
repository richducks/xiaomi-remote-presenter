"""WPS focus repair without stealing key events from other apps."""
import asyncio
import unittest
from unittest.mock import patch
from evdev import ecodes

import video_only_hid as hid
import wps_focus_recovery as focus

from test_chatgpt_navigation_rules import FakeRemote, FakeUI


class WPSFocusResumeTests(unittest.IsolatedAsyncioTestCase):
    async def run_events(self, keys, *, focused, safe=True, restored=True, browser=False):
        ui = FakeUI()
        with patch.object(hid.UInput, "from_device", return_value=ui), \
             patch.object(hid, "wps_presentation_focused", side_effect=focused), \
             patch.object(hid, "safe_to_resume_wps", return_value=safe) as safe_probe, \
             patch.object(hid, "ensure_wps_editor_focus", return_value=restored) as recover, \
             patch.object(hid, "browser_window_focused", return_value=browser), \
             patch.object(hid, "chatgpt_window_focused", return_value=False), \
             patch.object(hid, "browser_media_tab_focused", return_value=False), \
             patch.object(hid, "firefox_pip_focused", return_value=False), \
             patch.object(hid, "chatgpt_draft_ready", return_value=False), \
             patch.object(hid, "wechat_draft_state", return_value=(False,False)), \
             patch.object(hid, "toggle_browser_play_pause", return_value=False), \
             patch.object(hid, "youtube_video_tab_focused", return_value=False), \
             patch.object(hid, "key_sleep", return_value=None):
            await hid.forward_device(FakeRemote(keys))
        return ui, safe_probe, recover

    async def test_wps_ok_back_ok_refocuses_editor_before_second_f5(self):
        keys=[(ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,0),
              (ecodes.KEY_BACK,1),(ecodes.KEY_BACK,0),
              (ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,0)]
        ui,safe,recover=await self.run_events(keys,focused=[True,True,False])
        expected=[
            (ecodes.EV_KEY,ecodes.KEY_F5,1),(ecodes.EV_KEY,ecodes.KEY_F5,0),
            (ecodes.EV_KEY,ecodes.KEY_ESC,1),(ecodes.EV_KEY,ecodes.KEY_ESC,0),
            (ecodes.EV_KEY,ecodes.KEY_F5,1),(ecodes.EV_KEY,ecodes.KEY_F5,0)]
        self.assertEqual(ui.writes,expected)
        safe.assert_called_once_with()
        recover.assert_called_once_with()

    async def test_no_focus_hijack_after_switching_to_browser(self):
        keys=[(ecodes.KEY_BACK,1),(ecodes.KEY_BACK,0),
              (ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,0)]
        ui,safe,recover=await self.run_events(keys,focused=[True,False],
                                              safe=False,browser=True)
        recover.assert_not_called()
        self.assertEqual(ui.writes,[
            (ecodes.EV_KEY,ecodes.KEY_ESC,1),
            (ecodes.EV_KEY,ecodes.KEY_ESC,0)])
        self.assertEqual(ui.forwarded,[
            (ecodes.EV_KEY,ecodes.KEY_ENTER,1),
            (ecodes.EV_KEY,ecodes.KEY_ENTER,0)])

    async def test_recovery_failure_cannot_send_f5_to_desktop(self):
        keys=[(ecodes.KEY_BACK,1),(ecodes.KEY_BACK,0),
              (ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,0)]
        ui,safe,recover=await self.run_events(keys,focused=[True,False],
                                              safe=True,restored=False)
        recover.assert_called_once()
        self.assertEqual(ui.writes,[
            (ecodes.EV_KEY,ecodes.KEY_ESC,1),
            (ecodes.EV_KEY,ecodes.KEY_ESC,0)])

    async def test_repair_after_short_window_if_wps_remains_foreground(self):
        keys=[(ecodes.KEY_BACK,1),(ecodes.KEY_BACK,0),
              (ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,0)]
        with patch.object(hid, "WPS_RESUME_SECONDS", -1.0):
            ui,safe,recover=await self.run_events(keys,focused=[True,True],
                                                  safe=False,restored=True)
        recover.assert_called_once_with()
        self.assertEqual(ui.writes[-2:],[
            (ecodes.EV_KEY,ecodes.KEY_F5,1),
            (ecodes.EV_KEY,ecodes.KEY_F5,0)])

    def test_resume_window_must_be_gnome_wps_or_desktop_icons(self):
        samples=[
            (("wpp.desktop","wpp","example.pptx"),True),
            (("window:10","gjs","Desktop Icons 1"),True),
            (("org.mozilla.firefox.desktop","firefox","example.pptx"),False),
            (("com.awesun.desktop","awesun","example.pptx"),False),
            (("org.gnome.Terminal.desktop","Gnome-terminal","example.pptx"),False),
            (("window:10","gjs","Search"),False),
        ]
        for window,result in samples:
            with self.subTest(window=window),patch.object(focus,"_compositor_window",return_value=window):
                self.assertEqual(focus.safe_to_resume_wps(),result)


if __name__=="__main__":
    unittest.main()
