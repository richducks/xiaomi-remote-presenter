"""WeChat-only voice dictation safety and interaction regression checks."""
import asyncio
import time
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

import wechat_dictation as w

WECHAT = ('com.tencent.wechat.desktop', 'wechat', '微信')

class WechatDictationTests(unittest.IsolatedAsyncioTestCase):
    def test_window_identity_not_title(self):
        self.assertTrue(w.is_wechat_identity('com.tencent.wechat.desktop', 'wechat'))
        self.assertTrue(w.is_wechat_identity('wechat.desktop', 'wechat'))
        for app, kind in [('org.mozilla.firefox.desktop','firefox'),
                          ('org.some.fakewechat.desktop','fakewechat'),
                          ('com.alibabainc.dingtalk.desktop','dingtalk')]:
            self.assertFalse(w.is_wechat_identity(app, kind))
        with patch.object(w,'_compositor_window',return_value=('org.mozilla.firefox.desktop','firefox','微信')):
            self.assertIsNone(w.wechat_window())

    async def test_recording_never_activates_outside_wechat(self):
        d = w.WechatDictation()
        with patch.object(w,'wechat_window',return_value=None), patch.object(w.asyncio,'create_subprocess_exec') as create:
            await d.start()
            await d.stop()
            create.assert_not_called()
        self.assertFalse(d.busy())

    def test_draft_has_fresh_focus_and_expiry(self):
        d = w.WechatDictation()
        d.pending_window = WECHAT
        d.draft_at = time.monotonic()
        with patch.object(w,'wechat_window',return_value=WECHAT),patch.object(w,'wechat_editor_focused',return_value=True):
            self.assertTrue(d.draft_ready())
        with patch.object(w,'wechat_window',return_value=WECHAT),patch.object(w,'wechat_editor_focused',return_value=False):
            self.assertFalse(d.draft_ready())
        d.draft_at -= w.DRAFT_TTL + 1
        with patch.object(w,'wechat_window',return_value=WECHAT),patch.object(w,'wechat_editor_focused',return_value=True):
            self.assertFalse(d.draft_ready())

    async def test_send_only_when_ready(self):
        d = w.WechatDictation()
        with patch.object(d,'draft_ready',return_value=False),patch.object(w,'paste_or_send') as paste:
            self.assertFalse(await d.send())
            paste.assert_not_called()
        d.pending_window = WECHAT
        d.draft_at = time.monotonic()
        with patch.object(d,'draft_ready',return_value=True),patch.object(w,'paste_or_send',return_value=True) as paste:
            self.assertTrue(await d.send())
            paste.assert_called_once_with('send')
        self.assertIsNone(d.pending_window)

    def test_no_virtual_keypress_without_editor(self):
        with patch.object(w,'focus_wechat_chat_editor',return_value=False),patch.object(w,'_keyboard') as keyboard:
            self.assertFalse(w.paste_or_send('send'))
            self.assertFalse(w.paste_or_send('paste'))
            keyboard.assert_not_called()

    def test_keypress_balances_modifiers(self):
        from evdev import ecodes
        ui=MagicMock()
        with patch.object(w,'focus_wechat_chat_editor',return_value=True),patch.object(w,'wechat_editor_focused',return_value=True),patch.object(w,'_keyboard',return_value=ui),patch.object(w.time,'sleep'):
            self.assertTrue(w.paste_or_send('paste'))
            self.assertTrue(w.paste_or_send('send'))
        seq=[x.args for x in ui.write.call_args_list]
        self.assertEqual(seq,[(ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,1),
                               (ecodes.EV_KEY,ecodes.KEY_V,1),
                               (ecodes.EV_KEY,ecodes.KEY_V,0),
                               (ecodes.EV_KEY,ecodes.KEY_LEFTCTRL,0),
                               (ecodes.EV_KEY,ecodes.KEY_ENTER,1),
                               (ecodes.EV_KEY,ecodes.KEY_ENTER,0)])

    def test_fast_editor_path_avoids_slow_fallback(self):
        editor = object()
        with patch.object(w, 'wechat_window', return_value=WECHAT), \
             patch.object(w, '_fast_chat_editor', return_value=editor) as fast:
            self.assertIs(w._chat_editor(), editor)
            fast.assert_called_once()

    def test_unrelated_foreground_does_not_probe_wechat_editor(self):
        with patch.object(w, 'wechat_window', return_value=None), \
             patch.object(w, '_fast_chat_editor') as fast:
            self.assertIsNone(w._chat_editor())
            fast.assert_not_called()

    async def test_keyboard_preheat_only_prepares_device(self):
        with patch.object(w, '_keyboard') as keyboard, \
             patch.object(w, 'hold_wechat_ctrl_alt') as chord:
            await w.prewarm_wechat_keyboard()
            keyboard.assert_called_once()
            chord.assert_not_called()

    def test_ctrl_alt_pair_is_balanced(self):
        from evdev import ecodes
        ui = MagicMock()
        with patch.object(w, 'wechat_window', return_value=WECHAT), \
             patch.object(w, '_keyboard', return_value=ui):
            self.assertTrue(w.hold_wechat_ctrl_alt(True))
            self.assertTrue(w.hold_wechat_ctrl_alt(False))
        self.assertEqual([call.args for call in ui.write.call_args_list], [
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1),
            (ecodes.EV_KEY, ecodes.KEY_LEFTALT, 1),
            (ecodes.EV_KEY, ecodes.KEY_LEFTALT, 0),
            (ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0),
        ])

    async def test_live_shortcut_works_without_draft_read(self):
        d = w.WechatDictation()
        with patch.object(w, 'wechat_window', return_value=WECHAT), \
             patch.object(w, 'focus_wechat_chat_editor', return_value=True), \
             patch.object(w, '_draft_signature', side_effect=RuntimeError('Qt text unreadable')), \
             patch.object(w, 'hold_wechat_ctrl_alt', return_value=True) as chord, \
             patch.object(w.asyncio, 'create_subprocess_exec') as proc, \
             patch.object(w, 'paste_or_send') as paste:
            await d.start()
            await d.start()  # duplicate BLE press must not send a second chord
            self.assertTrue(d.busy())
            self.assertEqual(chord.call_count, 1)
            chord.assert_called_once_with(True)
            await d.stop()
            await d.finish_task
            self.assertEqual([call.args for call in chord.call_args_list], [(True,), (False,)])
            self.assertFalse(d.busy())
            self.assertEqual(d.pending_window, WECHAT)
            proc.assert_not_called()  # no offline Whisper, mic, or clipboard
            paste.assert_not_called()  # release never writes duplicate text

    async def test_no_shortcut_if_editor_missing(self):
        d = w.WechatDictation()
        with patch.object(w, 'wechat_window', return_value=WECHAT), \
             patch.object(w, 'focus_wechat_chat_editor', return_value=False), \
             patch.object(w, 'hold_wechat_ctrl_alt') as chord:
            await d.start()
            chord.assert_not_called()
            self.assertFalse(d.busy())

    async def test_native_finalize_does_not_write_text(self):
        d = w.WechatDictation()
        d.SETTLE_SECONDS = 0.001
        with patch.object(w, 'wechat_window', return_value=WECHAT), \
             patch.object(w, 'paste_or_send') as paste:
            await d._finalize(WECHAT, d._session)
            self.assertEqual(d.pending_window, WECHAT)
            paste.assert_not_called()

    async def test_no_draft_if_focus_moves_to_browser(self):
        d = w.WechatDictation()
        d.SETTLE_SECONDS = 0.001
        with patch.object(w, 'wechat_window', return_value=None), \
             patch.object(w, 'paste_or_send') as paste:
            await d._finalize(WECHAT, d._session)
            self.assertIsNone(d.pending_window)
            paste.assert_not_called()

    async def test_release_held_modifiers_after_focus_loss(self):
        d = w.WechatDictation()
        d._shortcut_held = True
        d._target = WECHAT
        with patch.object(w, 'wechat_window', return_value=None), \
             patch.object(w, 'hold_wechat_ctrl_alt') as chord:
            await d.stop()
            await d.finish_task
            chord.assert_called_once_with(False)
            self.assertFalse(d.busy())

    def test_no_ctrl_alt_outside_wechat(self):
        ui = MagicMock()
        with patch.object(w, 'wechat_window', return_value=None), \
             patch.object(w, '_keyboard', return_value=ui):
            self.assertFalse(w.hold_wechat_ctrl_alt(True))
            ui.write.assert_not_called()

    def test_running_class_has_no_offline_voice_or_paste(self):
        import ast
        from pathlib import Path
        cls = next(n for n in ast.parse(Path(w.__file__).read_text()).body
                   if isinstance(n, ast.ClassDef) and n.name == 'WechatDictation')
        invoked = [n.func.attr for n in ast.walk(cls)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertNotIn('create_subprocess_exec', invoked)
        self.assertNotIn('transcribe', invoked)
        self.assertNotIn('_finish', invoked)
        self.assertFalse(any(n.value == 'paste' for n in ast.walk(cls)
                             if isinstance(n, ast.Constant)))

if __name__ == '__main__':
    unittest.main()
