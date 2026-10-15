import unittest
from unittest.mock import Mock
from evdev import ecodes
from gatt_key_bridge import KeyTranslator, keyboard_codes, KEYS

def packet(usage): return bytes([0,0,usage,0,0,0,0,0])
class ProxyTranslationTests(unittest.TestCase):
    def test_captured_home_enter_back_up(self):
        for key,code in [(0x4a,ecodes.KEY_HOME),(0x28,ecodes.KEY_ENTER),
                         (0xf1,ecodes.KEY_BACK),(0x52,ecodes.KEY_UP)]:
            self.assertEqual(keyboard_codes(packet(key)),frozenset([code]))
    def test_hid_keyboard_media_usages(self):
        for usage, output in ((0x7f,ecodes.KEY_MUTE),
                              (0x80,ecodes.KEY_VOLUMEUP),
                              (0x81,ecodes.KEY_VOLUMEDOWN)):
            self.assertEqual(keyboard_codes(packet(usage)),frozenset([output]))

    def test_consumer_reports_standard_usages_only(self):
        from gatt_key_bridge import consumer_codes
        for raw,code in ((bytes((0xe9,0)),ecodes.KEY_VOLUMEUP),
                         (bytes((0xea,0)),ecodes.KEY_VOLUMEDOWN),
                         (bytes((0xe2,0)),ecodes.KEY_MUTE)):
            self.assertEqual(consumer_codes(raw),frozenset([code]))
        self.assertFalse(consumer_codes(bytes((0x0a,0xfe))))
        self.assertFalse(consumer_codes(bytes((0,0))))

    def test_release(self):
        ui=Mock()
        t=KeyTranslator(ui); t.feed(packet(0x4a),100)
        t.feed(bytes(8),100.25)
        self.assertIn((ecodes.EV_KEY,ecodes.KEY_HOME,1),[c.args for c in ui.write.call_args_list])
        self.assertIn((ecodes.EV_KEY,ecodes.KEY_HOME,0),[c.args for c in ui.write.call_args_list])
    def test_duplicate_pair_suppressed(self):
        ui=Mock();t=KeyTranslator(ui)
        for tm in [100,100.2,100.45,100.7,101,101.3,101.6]:
            t.feed(packet(0x4a),tm)
            t.feed(bytes(8),tm+.08)
        self.assertEqual(sum(c.args==(ecodes.EV_KEY,ecodes.KEY_HOME,1) for c in ui.write.call_args_list),1)
    def test_new_press_after_silence(self):
        ui=Mock();t=KeyTranslator(ui)
        t.feed(packet(0x4a),100);t.feed(bytes(8),100.1)
        t.feed(packet(0x4a),100.4);t.feed(bytes(8),100.5)
        t.feed(packet(0x4a),102);t.feed(bytes(8),102.1)
        self.assertEqual(sum(c.args==(ecodes.EV_KEY,ecodes.KEY_HOME,1)
                             for c in ui.write.call_args_list),2)

    def test_unmapped_does_not_inject(self):
        ui=Mock();t=KeyTranslator(ui);t.feed(packet(0xfe),100)
        ui.write.assert_not_called()
    def test_direction_repeated_only_short_interval(self):
        ui=Mock();t=KeyTranslator(ui)
        t.feed(packet(0x52),100);t.feed(bytes(8),100.06)
        t.feed(packet(0x52),100.1);t.feed(bytes(8),100.14)
        t.feed(packet(0x52),100.32)
        self.assertEqual(sum(c.args==(ecodes.EV_KEY,ecodes.KEY_UP,1) for c in ui.write.call_args_list),2)
if __name__ == "__main__":unittest.main()
