"""Integration checks for the actual Xiaomi HID event-forwarding loop."""
import importlib
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from evdev import ecodes

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
hid=importlib.import_module('remote_hid_filter')


class FakeRemote:
    path='/dev/input/TEST-XIAOMI'
    name='Xiaomi Remote 2 Pro'
    info=SimpleNamespace(
        bustype=0x05,vendor=hid.VID,product=hid.PID,version=0x0100)
    def __init__(self, events):
        self.events=events; self.grabbed=False;self.closed=False
    async def async_read_loop(self):
        for code,value in self.events:
            yield SimpleNamespace(type=ecodes.EV_KEY,code=code,value=value)
    def grab(self):self.grabbed=True
    def ungrab(self):self.grabbed=False
    def close(self):self.closed=True


class FakeUInput:
    def __init__(self):self.writes=[];self.fwd=[];self.syn_count=0;self.closed=False
    def write(self,ev_type,code,value):self.writes.append((ev_type,code,value))
    def write_event(self,ev):self.fwd.append((ev.type,ev.code,ev.value))
    def syn(self):self.syn_count+=1
    def close(self):self.closed=True


class HIDEventPipelineRegression(unittest.IsolatedAsyncioTestCase):
    async def run_device(self,keys,pip=False,bridge=False):
        remote=FakeRemote(keys)
        ui=FakeUInput()
        with patch.object(hid.UInput,'from_device',return_value=ui),\
             patch.object(hid,'browser_media_tab_focused',return_value=True),\
             patch.object(hid,'firefox_pip_focused',return_value=pip),\
             patch.object(hid,'route_firefox_pip_to_global_speed',return_value=bridge),\
             patch.object(hid,'toggle_browser_play_pause',return_value=False),\
             patch.object(hid,'wps_presentation_is_focused',return_value=False),\
             patch.object(hid,'browser_window_focused',return_value=True):
            await hid.forward_device(remote)
        self.assertTrue(remote.closed)
        self.assertTrue(ui.closed)
        return ui

    async def test_ordinary_media_uses_original_global_speed_d_a_hotkeys(self):
        k=[(ecodes.KEY_UP,1),(ecodes.KEY_UP,0),
           (ecodes.KEY_DOWN,1),(ecodes.KEY_DOWN,0),
           (ecodes.KEY_VOLUMEUP,1),(ecodes.KEY_VOLUMEUP,0),
           (ecodes.KEY_VOLUMEDOWN,1),(ecodes.KEY_VOLUMEDOWN,0)]
        ui=await self.run_device(k)
        self.assertEqual(ui.writes,[
            (ecodes.EV_KEY,ecodes.KEY_D,1),
            (ecodes.EV_KEY,ecodes.KEY_D,0),
            (ecodes.EV_KEY,ecodes.KEY_A,1),
            (ecodes.EV_KEY,ecodes.KEY_A,0),
        ])
        self.assertEqual(ui.fwd,[
            (ecodes.EV_KEY,ecodes.KEY_VOLUMEUP,1),
            (ecodes.EV_KEY,ecodes.KEY_VOLUMEUP,0),
            (ecodes.EV_KEY,ecodes.KEY_VOLUMEDOWN,1),
            (ecodes.EV_KEY,ecodes.KEY_VOLUMEDOWN,0),
        ])

    async def test_pip_without_connected_helper_never_sends_d_a(self):
        k=[(ecodes.KEY_UP,1),(ecodes.KEY_UP,0),
           (ecodes.KEY_DOWN,1),(ecodes.KEY_DOWN,0),
           (ecodes.KEY_VOLUMEUP,1),(ecodes.KEY_VOLUMEUP,0)]
        ui=await self.run_device(k,pip=True,bridge=False)
        self.assertEqual(ui.writes,[])
        self.assertEqual(ui.fwd,[
            (ecodes.EV_KEY,c,v) for c,v in k
        ])

    async def test_pip_with_connected_gs_helper_swallow_only_dpad(self):
        k=[(ecodes.KEY_UP,1),(ecodes.KEY_UP,0),
           (ecodes.KEY_DOWN,1),(ecodes.KEY_DOWN,0),
           (ecodes.KEY_VOLUMEUP,1),(ecodes.KEY_VOLUMEUP,0)]
        ui=await self.run_device(k,pip=True,bridge=True)
        self.assertEqual(ui.writes,[])
        self.assertEqual(ui.fwd,[
            (ecodes.EV_KEY,ecodes.KEY_VOLUMEUP,1),
            (ecodes.EV_KEY,ecodes.KEY_VOLUMEUP,0),
        ])

    async def test_exit_pip_then_normal_video_still_maps_d_a(self):
        # A PiP key press may finish after PiP was closed. Its release
        # must be swallowed without writing keycode=0. The next ordinary
        # browser key must still map to Global Speed, not get stuck.
        keys=[(ecodes.KEY_UP,1),(ecodes.KEY_UP,0),
              (ecodes.KEY_DOWN,1),(ecodes.KEY_DOWN,0)]
        remote=FakeRemote(keys)
        ui=FakeUInput()
        with patch.object(hid.UInput,'from_device',return_value=ui),\
             patch.object(hid,'browser_media_tab_focused',return_value=True),\
             patch.object(hid,'firefox_pip_focused',side_effect=[True,False]),\
             patch.object(hid,'route_firefox_pip_to_global_speed',return_value=True),\
             patch.object(hid,'toggle_browser_play_pause',return_value=False),\
             patch.object(hid,'wps_presentation_is_focused',return_value=False),\
             patch.object(hid,'browser_window_focused',return_value=True):
            await hid.forward_device(remote)
        self.assertEqual(ui.writes,[
            (ecodes.EV_KEY,ecodes.KEY_A,1),
            (ecodes.EV_KEY,ecodes.KEY_A,0),
        ])
        self.assertEqual(ui.fwd,[])

    async def test_home_closes_one_foreground_browser_tab(self):
        for home in (ecodes.KEY_HOME, ecodes.KEY_HOMEPAGE, ecodes.KEY_WWW):
            with self.subTest(home=home):
                keys=[(home,1),(home,2),(home,2),(home,0)]
                ui=await self.run_device(keys)
                self.assertEqual(ui.writes,[
                    (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
                    (ecodes.EV_KEY,ecodes.KEY_W,1),
                    (ecodes.EV_KEY,ecodes.KEY_W,0),
                    (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0),
                ])
                self.assertEqual(ui.syn_count,2)
                self.assertEqual(ui.fwd,[])

    async def test_home_outside_browser_passes_through(self):
        keys=[(ecodes.KEY_HOME,1),(ecodes.KEY_HOME,2),
              (ecodes.KEY_HOME,0)]
        remote=FakeRemote(keys);ui=FakeUInput()
        with patch.object(hid.UInput,'from_device',return_value=ui),\
             patch.object(hid,'browser_window_focused',return_value=False),\
             patch.object(hid,'firefox_pip_focused',return_value=False),\
             patch.object(hid,'browser_media_tab_focused',return_value=False),\
             patch.object(hid,'toggle_browser_play_pause',return_value=False),\
             patch.object(hid,'wps_presentation_is_focused',return_value=False):
            await hid.forward_device(remote)
        self.assertEqual(ui.writes,[])
        self.assertEqual(ui.fwd,[(ecodes.EV_KEY,c,v) for c,v in keys])

    async def test_home_does_not_double_close_after_focus_change(self):
        # The tab may disappear before the physical Home key is released.
        # In that case the driver must swallow the release and any repeats
        # without querying focus again or sending an unpaired key-up event.
        keys=[(ecodes.KEY_HOME,1),(ecodes.KEY_HOME,2),
              (ecodes.KEY_HOME,0),
              (ecodes.KEY_HOME,1),(ecodes.KEY_HOME,0)]
        remote=FakeRemote(keys);ui=FakeUInput()
        with patch.object(hid.UInput,'from_device',return_value=ui),\
             patch.object(hid,'browser_window_focused',
                          side_effect=[True,False]) as is_browser,\
             patch.object(hid,'firefox_pip_focused',return_value=False),\
             patch.object(hid,'browser_media_tab_focused',return_value=False),\
             patch.object(hid,'toggle_browser_play_pause',return_value=False),\
             patch.object(hid,'wps_presentation_is_focused',return_value=False):
            await hid.forward_device(remote)
        self.assertEqual(is_browser.call_count,2)
        self.assertEqual(ui.writes,[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_W,1),
            (ecodes.EV_KEY,ecodes.KEY_W,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0),
        ])
        self.assertEqual(ui.fwd,[
            (ecodes.EV_KEY,ecodes.KEY_HOME,1),
            (ecodes.EV_KEY,ecodes.KEY_HOME,0),
        ])

    async def test_home_without_release_never_leaves_ctrl_pressed(self):
        ui=await self.run_device([(ecodes.KEY_HOME,1)])
        self.assertEqual(ui.writes[-2:],[
            (ecodes.EV_KEY,ecodes.KEY_W,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0),
        ])
        self.assertEqual(ui.syn_count,2)

    async def test_web_home_code_non_browser_remains_original(self):
        keys=[(ecodes.KEY_WWW,1),(ecodes.KEY_WWW,0)]
        remote=FakeRemote(keys)
        ui=FakeUInput()
        with patch.object(hid.UInput,'from_device',return_value=ui),\
             patch.object(hid,'browser_window_focused',return_value=False):
            await hid.forward_device(remote)
        self.assertEqual(ui.writes,[])
        self.assertEqual(ui.fwd,[(ecodes.EV_KEY,c,v) for c,v in keys])

    async def test_home_and_www_same_physical_press_close_one_tab(self):
        # Firmware may report the house icon via two different keycodes.
        # Both rapid sequences are consumed but only one Ctrl+W is emitted.
        keys=[
            (ecodes.KEY_HOME,1),
            (ecodes.KEY_WWW,1),
            (ecodes.KEY_HOME,0),
            (ecodes.KEY_WWW,0),
        ]
        ui=await self.run_device(keys)
        self.assertEqual(ui.writes,[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_W,1),
            (ecodes.EV_KEY,ecodes.KEY_W,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0),
        ])
        self.assertEqual(ui.syn_count,2)
        self.assertEqual(ui.fwd,[])

    async def test_home_shortcut_and_global_speed_do_not_conflict(self):
        keys=[(ecodes.KEY_HOME,1),(ecodes.KEY_HOME,0),
              (ecodes.KEY_UP,1),(ecodes.KEY_UP,0),
              (ecodes.KEY_DOWN,1),(ecodes.KEY_DOWN,0),
              (ecodes.KEY_VOLUMEUP,1),(ecodes.KEY_VOLUMEUP,0)]
        ui=await self.run_device(keys)
        self.assertEqual(ui.writes,[
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
            (ecodes.EV_KEY,ecodes.KEY_W,1),
            (ecodes.EV_KEY,ecodes.KEY_W,0),
            (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0),
            (ecodes.EV_KEY,ecodes.KEY_D,1),
            (ecodes.EV_KEY,ecodes.KEY_D,0),
            (ecodes.EV_KEY,ecodes.KEY_A,1),
            (ecodes.EV_KEY,ecodes.KEY_A,0),
        ])
        self.assertEqual(ui.fwd,[
            (ecodes.EV_KEY,ecodes.KEY_VOLUMEUP,1),
            (ecodes.EV_KEY,ecodes.KEY_VOLUMEUP,0),
        ])

    async def test_wps_shortcuts_preserved(self):
        self.assertEqual(hid.OK_KEYS,{ecodes.KEY_ENTER,ecodes.KEY_OK})
        self.assertIn(ecodes.KEY_BACK,hid.BACK_KEYS)
        self.assertEqual(hid.BLOCK_KEY,ecodes.KEY_F5)


if __name__=='__main__':
    unittest.main()
