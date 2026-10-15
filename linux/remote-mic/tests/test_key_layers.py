import unittest
from unittest.mock import Mock
from evdev import ecodes
from key_layers import SYSTEM_KEY_NAMES, SYSTEM_KEY_CODES, is_system_key
from remote_rules import validate
from gatt_key_bridge import keyboard_codes, consumer_codes, KeyTranslator

class TestLayerAuthority(unittest.TestCase):
    def test_reserved_system_keys_cannot_enter_any_application(self):
        for name in SYSTEM_KEY_NAMES:
            self.assertTrue(is_system_key(getattr(ecodes, name)),name)
            for scope in ("wps", "browser", "chatgpt"):
                with self.subTest(key=name, scope=scope):
                    item={"id":"restricted", "input":name,"scope":scope}
                    item.update({"action":"new_chat"} if scope=="chatgpt" else {"tap":"KEY_F5"})
                    with self.assertRaisesRegex(ValueError,"system-level"):
                        validate({"version":1,"rules":[item]})

    def test_power_uses_real_standard_hid_reports_only(self):
        self.assertEqual(keyboard_codes(bytes((0,0,0x66,0,0,0,0,0))),frozenset({ecodes.KEY_POWER}))
        self.assertEqual(consumer_codes(bytes((0x30,0))),frozenset({ecodes.KEY_POWER}))
        self.assertEqual(consumer_codes(bytes((0x32,0))),frozenset({ecodes.KEY_SLEEP}))
        self.assertEqual(consumer_codes(bytes((0x6f,0))),frozenset({ecodes.KEY_BRIGHTNESSUP}))
        self.assertEqual(consumer_codes(bytes((0x70,0))),frozenset({ecodes.KEY_BRIGHTNESSDOWN}))
        self.assertEqual(consumer_codes(bytes((0xff,0))),frozenset())
        self.assertEqual(keyboard_codes(bytes((0,0,0xfe,0,0,0,0,0))),frozenset())

    def test_power_burst_is_guarded_even_when_firmware_sends_repeats(self):
        ui=Mock()
        handler=KeyTranslator(ui)
        down=bytes((0,0,0x66,0,0,0,0,0))
        for t in (100,100.7,101.2,102.4):
            handler.feed(down,t);handler.feed(bytes(8),t+0.12)
        matches=[m for m in ui.write.call_args_list
                 if m.args==(ecodes.EV_KEY,ecodes.KEY_POWER,1)]
        self.assertEqual(len(matches),1)
        handler.feed(down,106);handler.feed(bytes(8),106.1)
        matches=[m for m in ui.write.call_args_list
                 if m.args==(ecodes.EV_KEY,ecodes.KEY_POWER,1)]
        self.assertEqual(len(matches),2)

    def test_gui_system_catalog_matches_backend_policy(self):
        from pathlib import Path
        import json
        schema=json.loads((Path(__file__).resolve().parents[1]/"electron/ui-schema.json").read_text())
        self.assertEqual({row["code"] for row in schema["systemKeys"]},SYSTEM_KEY_NAMES)

    def test_consumer_media_keys_are_not_application_keys(self):
        for x in (ecodes.KEY_VOLUMEUP,ecodes.KEY_VOLUMEDOWN,
                  ecodes.KEY_MUTE,ecodes.KEY_POWER):
            self.assertIn(x,SYSTEM_KEY_CODES)

if __name__=="__main__":
    unittest.main()
