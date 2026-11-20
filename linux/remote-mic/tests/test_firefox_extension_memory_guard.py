"""Unit tests for the Firefox-only high-RSS recovery guard."""
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).resolve().parents[1] / "firefox_extension_memory_guard.py"
spec = importlib.util.spec_from_file_location("firefox_extension_memory_guard", PATH)
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


class GuardTests(unittest.TestCase):
    def test_parse_snap_firefox_one_or_multiple_argv(self):
        cmd = (b"/snap/firefox/8995/usr/lib/firefox/firefox -contentproc "
               b"-parentPid 2562200 -other stuff")
        self.assertEqual(guard.parse_firefox_parent(cmd), 2562200)
        self.assertEqual(
            guard.parse_firefox_parent(cmd.replace(b" ", b"\0")),
            None)
        spaced = (b"/snap/firefox/8995/usr/lib/firefox/firefox\0"
                  b"-contentproc\0-parentPid\0" b"2562200\0")
        self.assertEqual(guard.parse_firefox_parent(spaced.replace(b"\0", b" ")), 2562200)
        self.assertIsNone(guard.parse_firefox_parent(
            b"/usr/bin/not-firefox -contentproc -parentPid 12"))
        self.assertIsNone(guard.parse_firefox_parent(
            b"/snap/firefox/8995/firefox -parentPid 12"))

    def test_single_spike_cannot_terminate(self):
        host = guard.Host(100, 2, 5000, guard.MAX_RSS_KIB + 1)
        state, stop = guard.decision({}, host, 1000)
        self.assertFalse(stop)
        state, stop = guard.decision(state, host, 1100)
        self.assertFalse(stop)
        state, stop = guard.decision(state, host, 1180)
        self.assertTrue(stop)

    def test_under_limit_clears_state(self):
        high = guard.Host(100, 2, 5000, guard.MAX_RSS_KIB + 1)
        state, _ = guard.decision({}, high, 1000)
        low = guard.Host(100, 2, 5000, 1024)
        self.assertEqual(guard.decision(state, low, 2000), ({}, False))

    def test_reused_pid_does_not_inherit_sample(self):
        high = guard.Host(100, 2, 5000, guard.MAX_RSS_KIB + 1)
        state, _ = guard.decision({}, high, 1000)
        reused = guard.Host(100, 2, 5001, guard.MAX_RSS_KIB + 1)
        later, stop = guard.decision(state, reused, 3000)
        self.assertFalse(stop)
        self.assertEqual(later["first"], 3000)

    def test_missing_host_refuses_action(self):
        self.assertEqual(guard.decision({"pid": 11}, None, 1e6), ({}, False))

    def test_no_overeager_kill_in_main(self):
        safe = guard.Host(11, 2, 1234, 800000)
        with patch.object(guard, "find_hosts", return_value=[safe]), \
             patch.object(guard, "read_state", return_value={}), \
             patch.object(guard, "save_state") as save, \
             patch.object(guard.os, "kill") as kill, \
             patch.object(guard, "DISABLE_FILE", pathlib.Path("/unlikely-test-path-no-guard-file")):
            guard.main()
        save.assert_called_once()
        kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
