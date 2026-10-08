import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
class VideoSetupUITests(unittest.TestCase):
    def test_setup_page_is_accessible_and_has_one_install_link(self):
        text=(ROOT/"chatgpt-web/video-setup.html").read_text()
        self.assertEqual(text.count('href="/xiaomi-video-speed.user.js"'),1)
        self.assertIn('Global Speed',text)
        self.assertIn('v0.5.0',text)
        self.assertIn('id="connect"',text)
        self.assertIn('id="result"',text)
        self.assertIn("j.pip_ready",text)

if __name__=="__main__":unittest.main()
