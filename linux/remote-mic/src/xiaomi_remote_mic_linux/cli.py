from __future__ import annotations

import argparse
import asyncio
import logging

from . import __version__
from .ble_voice import LinuxATVVBridge, scan
from .buttons import run_button_diagnostics
from .diagnostics import doctor


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xiaomi-remote-mic")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check Bluetooth and audio prerequisites")
    scan_p = sub.add_parser("scan", help="scan for Xiaomi RC003 remotes")
    scan_p.add_argument("--timeout", type=float, default=8.0)
    run_p = sub.add_parser("run", help="run BLE voice bridge")
    run_p.add_argument("--address")
    run_p.add_argument("--gain-db", type=float, default=10.0)
    sub.add_parser("buttons", help="print evdev button events for mapping")
    return p


async def _scan_and_print(timeout: float) -> int:
    items = await scan(timeout)
    if not items:
        print("No RC003/MI RC found. Ensure it is paired, awake and nearby.")
        return 1
    for i, d in enumerate(items, 1):
        print(f"{i}. {d.name}  {d.address}")
    return 0


async def _run(address: str | None, gain_db: float) -> int:
    if not address:
        items = await scan(6.0)
        if len(items) == 0:
            print("No RC003/MI RC found.")
            return 1
        if len(items) > 1:
            print("Multiple remotes found. Re-run with --address <MAC/address>:")
            for d in items: print(f"  {d.name}  {d.address}")
            return 2
        address = items[0].address
    bridge = LinuxATVVBridge(address, gain_db=gain_db)
    await bridge.run()
    return 0


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "doctor":
        raise SystemExit(doctor())
    if args.command == "buttons":
        raise SystemExit(run_button_diagnostics())
    try:
        if args.command == "scan":
            code = asyncio.run(_scan_and_print(args.timeout))
        else:
            code = asyncio.run(_run(args.address, args.gain_db))
    except KeyboardInterrupt:
        code = 130
    except Exception as exc:
        logging.getLogger("xiaomi-remote-mic").error("fatal: %s", exc)
        code = 1
    raise SystemExit(code)
