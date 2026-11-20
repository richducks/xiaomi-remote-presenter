#!/usr/bin/env python3
"""Failsafe for Firefox extension-host RAM leaks; never exits the browser.

A second check after >=3 minutes is required to terminate a runaway
WebExtensions child. Tabs, session and Firefox main process are untouched.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import signal
import time
from dataclasses import dataclass

MAX_RSS_KIB = 7 * 1024 * 1024
MIN_GROWTH_SECONDS = 180
STATE_FILE = Path.home() / ".local/state/xiaomi-remote-presenter/firefox-extensions-guard.json"
DISABLE_FILE = Path.home() / ".config/xiaomi-remote-presenter/disable-firefox-extension-guard"


@dataclass(frozen=True)
class Host:
    pid: int
    parent_pid: int
    started: int
    rss_kib: int


def parse_firefox_parent(command: bytes) -> int | None:
    """Firefox snap may encode all content-process args in one argv entry."""
    text = command.decode(errors="replace")
    if not text.startswith("/snap/firefox/") or "-contentproc" not in text:
        return None
    match = re.search(r"(?:^|\s)-parentPid\s+(\d+)(?:\s|$)", text)
    return int(match.group(1)) if match else None


def identify_host(pid: int) -> Host | None:
    """Require the exact Firefox WebExtensions child and its live parent."""
    try:
        base = Path(f"/proc/{pid}")
        if (base / "comm").read_text().strip() != "WebExtensions":
            return None
        command = (base / "cmdline").read_bytes().replace(b"\0", b" ")
        parent = parse_firefox_parent(command)
        if parent is None:
            return None
        parent_dir = Path(f"/proc/{parent}")
        if (parent_dir / "comm").read_text().strip() != "firefox":
            return None
        if not os.path.realpath(f"/proc/{parent}/exe").startswith("/snap/firefox/"):
            return None
        # /proc/[pid]/stat field 22; indices from field 3 after the ')'.
        stat_fields = (base / "stat").read_text().rsplit(") ", 1)[1].split()
        started = int(stat_fields[19])
        line = next(x for x in (base / "status").read_text().splitlines()
                    if x.startswith("VmRSS:"))
        rss = int(line.split()[1])
        return Host(pid, parent, started, rss)
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def find_hosts() -> list[Host]:
    hosts = []
    for name in os.listdir("/proc"):
        if name.isdigit():
            host = identify_host(int(name))
            if host is not None:
                hosts.append(host)
    return hosts


def decision(previous: dict, host: Host | None, now: float) -> tuple[dict, bool]:
    """Pure two-phase guard: never act on one sample or a recycled PID."""
    if host is None or host.rss_kib < MAX_RSS_KIB:
        return {}, False
    if (previous.get("pid") == host.pid
            and previous.get("started") == host.started):
        first = previous.get("first", now)
        try:
            if 0 <= now - float(first) and now - float(first) >= MIN_GROWTH_SECONDS:
                return {}, True
        except (TypeError, ValueError):
            pass
        return {"pid": host.pid, "started": host.started, "first": first}, False
    return {"pid": host.pid, "started": host.started, "first": now}, False


def read_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    temp.write_text(json.dumps(state), encoding="utf-8")
    temp.replace(STATE_FILE)


def main() -> int:
    if DISABLE_FILE.exists():
        print("disabled by user sentinel")
        return 0
    hosts = find_hosts()
    # Do not guess which user/Firefox session should be affected.
    if len(hosts) != 1:
        save_state({})
        print(f"no unique Firefox extension child ({len(hosts)}); no action")
        return 0
    host = hosts[0]
    state, should_stop = decision(read_state(), host, time.monotonic())
    if not should_stop:
        save_state(state)
        print(f"Firefox WebExtensions pid={host.pid} rss_mib={host.rss_kib//1024}; "
              f"threshold_mib={MAX_RSS_KIB//1024}; action=none")
        return 0
    # Validate again immediately before a scoped SIGTERM.
    current = identify_host(host.pid)
    if current != host:
        save_state({})
        print("Firefox extension child changed during check; no action")
        return 0
    os.kill(host.pid, signal.SIGTERM)
    save_state({})
    print(f"RECOVER: stopped only runaway Firefox WebExtensions child "
          f"pid={host.pid}, rss_mib={host.rss_kib//1024}; browser untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
