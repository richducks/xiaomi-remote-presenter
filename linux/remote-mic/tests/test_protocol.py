import unittest
from xiaomi_remote_mic_linux import protocol


class ProtocolTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(protocol.mic_open_command(0x100), b"\x0c\x00")
        self.assertEqual(protocol.mic_close_command(0x100, 9), b"\x0d\x09")

    def test_caps(self):
        caps = protocol.ATVVCapabilities.parse(bytes((0x0b, 0x01, 0x00, 0x02, 0x03, 0x00, 0x78)))
        self.assertIsNotNone(caps)
        self.assertEqual(caps.sample_rate, 16000.0)
        self.assertEqual(caps.frame_size, 120)

    def test_adpcm_decoder_length(self):
        dec = protocol.IMAADPCMDecoder()
        self.assertEqual(len(dec.decode(b"\x00" * 120)), 240)

    def test_session_audio_gate(self):
        s = protocol.ATVVSession()
        s.handle_control(bytes((0x0b, 0x01, 0x00, 0x02, 0x03, 0x00, 0x78)))
        self.assertEqual(s.handle_audio(b"\x00" * 120), [])
        s.handle_control(bytes((0x04, 0, 2, 7)))
        self.assertEqual(len(s.handle_audio(b"\x00" * 120)), 240)
        self.assertEqual(s.close_command(), b"\x0d\x07")


if __name__ == "__main__":
    unittest.main()
