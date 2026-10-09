"""Ensure the new video-only service cannot change Enter/ordinary apps."""
import importlib
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from evdev import ecodes

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
video = importlib.import_module("video_only_hid")


class FakeRemote:
    path = "/dev/input/TEST-XIAOMI"
    name = "小米蓝牙语音遥控器"
    info = SimpleNamespace(bustype=5, vendor=video.VID,
                           product=video.PID, version=0x100)

    def __init__(self, events):
        self.events = events
        self.grabbed = False
        self.closed = False

    async def async_read_loop(self):
        for code, value in self.events:
            yield SimpleNamespace(type=ecodes.EV_KEY,
                                  code=code, value=value)

    def grab(self):
        self.grabbed = True

    def ungrab(self):
        self.grabbed = False

    def close(self):
        self.closed = True


class FakeUInput:
    def __init__(self):
        self.forwarded = []
        self.written = []
        self.syn_count = 0
        self.closed = False

    def write_event(self, event):
        self.forwarded.append((event.code, event.value))

    def write(self, kind, code, value):
        self.written.append((kind, code, value))

    def syn(self):
        self.syn_count += 1

    def close(self):
        self.closed = True


class VideoOnlyIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def run_remote(self, events, *, video_tab=False, pip=False,
                         helper=False, mpris=False, youtube=False,
                         browser_focused=False):
        dev = FakeRemote(events)
        ui = FakeUInput()
        with patch.object(video.UInput, "from_device", return_value=ui), \
             patch.object(video, "browser_media_tab_focused", return_value=video_tab), \
             patch.object(video, "firefox_pip_focused", return_value=pip), \
             patch.object(video, "pip_global_speed", return_value=helper), \
             patch.object(video, "toggle_browser_play_pause", return_value=mpris), \
             patch.object(video, "youtube_video_tab_focused", return_value=youtube), \
             patch.object(video, "browser_window_focused", return_value=browser_focused):
            await video.forward_device(dev)
        self.assertFalse(dev.grabbed)
        self.assertTrue(dev.closed)
        self.assertTrue(ui.closed)
        return ui

    async def test_normal_enter_physical_down_repeat_up_untouched(self):
        keys = [(ecodes.KEY_ENTER, 1),(ecodes.KEY_ENTER, 2),
                (ecodes.KEY_ENTER, 2),(ecodes.KEY_ENTER, 0),
                (ecodes.KEY_KPENTER, 1),(ecodes.KEY_KPENTER, 0)]
        ui = await self.run_remote(keys)
        self.assertEqual(ui.forwarded, keys)
        self.assertEqual(ui.written, [])

    async def test_dingtalk_wps_other_remote_buttons_are_verbatim(self):
        keys = [(code, val)
                for code in (ecodes.KEY_ENTER, ecodes.KEY_BACK,
                             ecodes.KEY_COMPOSE, ecodes.KEY_HOME,
                             ecodes.KEY_GRAVE, ecodes.KEY_F5,
                             ecodes.KEY_LEFTCTRL, ecodes.KEY_TAB,
                             ecodes.KEY_VOLUMEUP, ecodes.KEY_VOLUMEDOWN)
                for val in (1,0)]
        ui = await self.run_remote(keys)
        self.assertEqual(ui.forwarded, keys)
        self.assertEqual(ui.written, [])

    async def test_browser_home_opens_one_tab_even_if_held(self):
        keys = [(ecodes.KEY_HOME,1),(ecodes.KEY_HOME,2),
                (ecodes.KEY_HOME,1),(ecodes.KEY_HOME,0)]
        ui = await self.run_remote(keys,browser_focused=True)
        self.assertEqual(ui.written,[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_T,1),
            (ecodes.EV_KEY,ecodes.KEY_T,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0)])
        self.assertEqual(ui.syn_count,2)
        self.assertEqual(ui.forwarded,[])

    async def test_browser_home_and_www_duplicate_only_one_tab(self):
        keys=[(ecodes.KEY_HOME,1),(ecodes.KEY_WWW,1),
              (ecodes.KEY_HOME,0),(ecodes.KEY_WWW,0)]
        ui=await self.run_remote(keys,browser_focused=True)
        self.assertEqual(ui.written,[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_T,1),
            (ecodes.EV_KEY,ecodes.KEY_T,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0)])
        self.assertEqual(ui.forwarded,[])

    async def test_browser_menu_next_tab_no_repeat(self):
        keys=[(ecodes.KEY_COMPOSE,1),(ecodes.KEY_COMPOSE,2),
              (ecodes.KEY_COMPOSE,0)]
        ui=await self.run_remote(keys,browser_focused=True)
        self.assertEqual(ui.written,[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_TAB,1),
            (ecodes.EV_KEY,ecodes.KEY_TAB,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0)])
        self.assertEqual(ui.syn_count,2)
        self.assertEqual(ui.forwarded,[])

    async def test_browser_tv_closes_single_tab(self):
        keys=[(ecodes.KEY_GRAVE,1),(ecodes.KEY_GRAVE,2),
              (ecodes.KEY_GRAVE,0)]
        ui=await self.run_remote(keys,browser_focused=True)
        self.assertEqual(ui.written,[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_W,1),
            (ecodes.EV_KEY,ecodes.KEY_W,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0)])
        self.assertEqual(ui.syn_count,2)
        self.assertEqual(ui.forwarded,[])

    async def test_browser_enter_still_passes_down_repeat_up(self):
        keys=[(ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,2),
              (ecodes.KEY_ENTER,0),(ecodes.KEY_KPENTER,1),
              (ecodes.KEY_KPENTER,0)]
        ui=await self.run_remote(keys,browser_focused=True)
        self.assertEqual(ui.forwarded,keys)
        self.assertEqual(ui.written,[])

    async def test_browser_shortcuts_do_not_remap_back_or_volume(self):
        keys=[(ecodes.KEY_BACK,1),(ecodes.KEY_BACK,0),
              (ecodes.KEY_VOLUMEUP,1),(ecodes.KEY_VOLUMEUP,0)]
        ui=await self.run_remote(keys,browser_focused=True)
        self.assertEqual(ui.forwarded,keys)
        self.assertEqual(ui.written,[])

    async def test_browser_tab_release_swallowed_after_focus_loss(self):
        keys=[(ecodes.KEY_GRAVE,1),(ecodes.KEY_GRAVE,2),
              (ecodes.KEY_GRAVE,0)]
        dev=FakeRemote(keys); ui=FakeUInput()
        with patch.object(video.UInput,"from_device",return_value=ui), \
             patch.object(video,"browser_window_focused",
                          side_effect=[True,False]) as focus:
            await video.forward_device(dev)
        self.assertEqual(focus.call_count,1)
        self.assertEqual(ui.forwarded,[])
        self.assertEqual(ui.written,[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_W,1),
            (ecodes.EV_KEY,ecodes.KEY_W,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0)])

    async def test_home_separate_press_creates_separate_tabs(self):
        keys=[(ecodes.KEY_HOME,1),(ecodes.KEY_HOME,0),
              (ecodes.KEY_HOME,1),(ecodes.KEY_HOME,0)]
        moments=iter([2.0,3.0])
        with patch.object(video,"time",SimpleNamespace(monotonic=lambda: next(moments))):
            ui=await self.run_remote(keys,browser_focused=True)
        shortcut=[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_T,1),
            (ecodes.EV_KEY,ecodes.KEY_T,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0)]
        self.assertEqual(ui.written,shortcut+shortcut)
        self.assertEqual(ui.syn_count,4)
        self.assertEqual(ui.forwarded,[])

    async def test_menu_bounce_cannot_cycle_many_tabs(self):
        keys = [(ecodes.KEY_COMPOSE, x) for x in (1, 0, 1, 0, 1, 0)]
        moments = iter([1.0, 1.12, 1.32])
        with patch.object(video, "time", SimpleNamespace(monotonic=lambda: next(moments))):
            ui = await self.run_remote(keys, browser_focused=True)
        self.assertEqual(ui.written, [
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
            (ecodes.EV_KEY, ecodes.KEY_TAB, 1),
            (ecodes.EV_KEY, ecodes.KEY_TAB, 0),
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
        ])
        self.assertEqual(ui.forwarded, [])

    async def test_tv_bounce_cannot_close_multiple_tabs(self):
        keys = [(ecodes.KEY_GRAVE, x) for x in (1, 0, 1, 0, 1, 0)]
        moments = iter([1.0, 1.22, 1.60])
        with patch.object(video, "time", SimpleNamespace(monotonic=lambda: next(moments))):
            ui = await self.run_remote(keys, browser_focused=True)
        self.assertEqual(ui.written, [
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
            (ecodes.EV_KEY, ecodes.KEY_W, 1),
            (ecodes.EV_KEY, ecodes.KEY_W, 0),
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
        ])
        self.assertEqual(ui.forwarded, [])

    async def test_deliberate_second_tv_press_after_cooldown(self):
        keys = [(ecodes.KEY_GRAVE, x) for x in (1, 0, 1, 0)]
        moments = iter([1.0, 2.0])
        with patch.object(video, "time", SimpleNamespace(monotonic=lambda: next(moments))):
            ui = await self.run_remote(keys, browser_focused=True)
        shortcut = [
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
            (ecodes.EV_KEY, ecodes.KEY_W, 1),
            (ecodes.EV_KEY, ecodes.KEY_W, 0),
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
        ]
        self.assertEqual(ui.written, shortcut + shortcut)
        self.assertEqual(ui.forwarded, [])

    async def test_video_speed_maps_only_arrows_one_step_each(self):
        keys = [(ecodes.KEY_UP,1),(ecodes.KEY_UP,2),(ecodes.KEY_UP,0),
                (ecodes.KEY_DOWN,1),(ecodes.KEY_DOWN,0),
                (ecodes.KEY_VOLUMEUP,1),(ecodes.KEY_VOLUMEUP,0)]
        ui = await self.run_remote(keys,video_tab=True)
        self.assertEqual(ui.written, [
            (ecodes.EV_KEY,ecodes.KEY_D,1),(ecodes.EV_KEY,ecodes.KEY_D,0),
            (ecodes.EV_KEY,ecodes.KEY_A,1),(ecodes.EV_KEY,ecodes.KEY_A,0)])
        self.assertEqual(ui.syn_count,4)
        self.assertEqual(ui.forwarded, [
            (ecodes.KEY_VOLUMEUP,1),(ecodes.KEY_VOLUMEUP,0)])

    async def test_no_active_video_arrows_unchanged(self):
        keys=[(ecodes.KEY_UP,1),(ecodes.KEY_UP,2),(ecodes.KEY_UP,0)]
        ui=await self.run_remote(keys)
        self.assertEqual(ui.forwarded,keys)
        self.assertEqual(ui.written,[])

    async def test_browser_ok_mpris_consumes_only_video_press(self):
        keys=[(ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,2),
              (ecodes.KEY_ENTER,0)]
        ui=await self.run_remote(keys,mpris=True)
        self.assertEqual(ui.forwarded,[])
        self.assertEqual(ui.written,[])

    async def test_video_ok_can_be_used_again_after_release(self):
        keys=[(ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,0),
              (ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,0)]
        ui=await self.run_remote(keys,mpris=True)
        self.assertEqual(ui.forwarded,[])
        self.assertEqual(ui.written,[])

    async def test_youtube_fallback_single_k_tap(self):
        keys=[(ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,2),
              (ecodes.KEY_ENTER,0)]
        ui=await self.run_remote(keys,youtube=True)
        self.assertEqual(ui.forwarded,[])
        self.assertEqual(ui.written,[
            (ecodes.EV_KEY,ecodes.KEY_K,1),
            (ecodes.EV_KEY,ecodes.KEY_K,0)])
        self.assertEqual(ui.syn_count,2)

    async def test_pip_success_consumes_arrows(self):
        keys=[(ecodes.KEY_UP,1),(ecodes.KEY_UP,0)]
        ui=await self.run_remote(keys,pip=True,helper=True,video_tab=True)
        self.assertEqual(ui.forwarded,[])
        self.assertEqual(ui.written,[])

    async def test_pip_missing_helper_keeps_arrows_unchanged(self):
        keys=[(ecodes.KEY_UP,1),(ecodes.KEY_UP,0)]
        ui=await self.run_remote(keys,pip=True,helper=False,video_tab=True)
        self.assertEqual(ui.forwarded,keys)
        self.assertEqual(ui.written,[])

    async def test_video_enter_success_does_not_change_nonvideo_enter(self):
        keys=[(ecodes.KEY_ENTER,1),(ecodes.KEY_ENTER,0)]
        ui=await self.run_remote(keys)
        self.assertEqual(ui.forwarded,keys)
        self.assertEqual(ui.written,[])

    def test_only_original_xiaomi_is_selected(self):
        original=FakeRemote([])
        virtual=FakeRemote([]);virtual.name=video.VIRTUAL_NAME
        keyboard=FakeRemote([]);keyboard.info=SimpleNamespace(
            bustype=3,vendor=0x001,product=1,version=0)
        with patch.object(video, "list_devices",
                          return_value=["/dev/virt","/dev/kb","/dev/remote"]), \
             patch.object(video, "InputDevice",
                          side_effect=[virtual,keyboard,original]):
            self.assertIs(video.find_remote(), original)


if __name__ == "__main__":
    unittest.main()
