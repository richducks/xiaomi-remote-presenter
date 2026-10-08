import importlib
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch
from evdev import ecodes

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
hid = importlib.import_module('remote_hid_filter')
media = importlib.import_module('video_browser_context')


class RemoteKeyIsolationTests(unittest.TestCase):
    def test_only_xiaomi_dpad_mapped_and_volume_passes(self):
        self.assertEqual(hid.VIDEO_RATE_KEYS, {
            ecodes.KEY_UP: ecodes.KEY_D,
            ecodes.KEY_DOWN: ecodes.KEY_A,
        })
        self.assertNotIn(ecodes.KEY_VOLUMEUP,hid.VIDEO_RATE_KEYS)
        self.assertNotIn(ecodes.KEY_VOLUMEDOWN,hid.VIDEO_RATE_KEYS)
        self.assertEqual(hid.VID,0x2717)
        self.assertEqual(hid.PID,0x32B8)

    def test_pip_browser_bridge_only_receives_dpad_and_is_firefox_only(self):
        import io
        from unittest.mock import MagicMock
        for key,kind in [(ecodes.KEY_UP,b"speed_up"),
                         (ecodes.KEY_DOWN,b"speed_down")]:
            context=MagicMock()
            context.__enter__.return_value=io.BytesIO(b'{"ok":true}')
            with patch.object(hid.urllib.request,'urlopen',return_value=context) as fetch:
                self.assertTrue(hid.route_firefox_pip_to_global_speed(key))
                req=fetch.call_args.args[0]
                self.assertIn(kind,req.data)
                self.assertIn(b'"browser": "firefox"',req.data)
                self.assertIn(b'"pip": true',req.data)
        self.assertFalse(hid.route_firefox_pip_to_global_speed(ecodes.KEY_VOLUMEUP))
        self.assertFalse(hid.route_firefox_pip_to_global_speed(ecodes.KEY_VOLUMEDOWN))

    def test_wps_keys_remain_defined(self):
        self.assertIn(ecodes.KEY_ENTER, hid.OK_KEYS)
        self.assertIn(ecodes.KEY_BACK, hid.BACK_KEYS)
        self.assertEqual(hid.BLOCK_KEY, ecodes.KEY_F5)

    def test_only_current_media_player_is_toggled(self):
        bus = MagicMock()
        with patch.object(media, 'active_browser_media_session', return_value=(bus, 'org.mpris.MediaPlayer2.firefox.test')):
            self.assertTrue(media.toggle_browser_play_pause())
            self.assertEqual(bus.call_sync.call_count, 1)
            self.assertEqual(bus.call_sync.call_args.args[2], 'org.mpris.MediaPlayer2.Player')
            self.assertEqual(bus.call_sync.call_args.args[3], 'PlayPause')

    def test_non_video_ok_is_not_swallowed(self):
        with patch.object(media, 'active_browser_media_session', return_value=None):
            self.assertFalse(media.toggle_browser_play_pause())

    def test_failed_media_method_not_reported_success(self):
        bus = MagicMock()
        bus.call_sync.side_effect = RuntimeError('player disconnected')
        with patch.object(media, 'active_browser_media_session', return_value=(bus, 'org.mpris.MediaPlayer2.chromium.test')):
            self.assertFalse(media.toggle_browser_play_pause())


if __name__ == '__main__':
    unittest.main()
