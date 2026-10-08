from __future__ import annotations

import shutil
import subprocess


def _run(args: list[str]) -> tuple[bool, str]:
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=8)
        return p.returncode == 0, (p.stdout or p.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def doctor() -> int:
    failures = 0
    print("Xiaomi Remote Mic Linux doctor\n")
    for cmd in ("bluetoothctl", "pactl", "paplay"):
        ok = shutil.which(cmd) is not None
        print(f"[{'OK' if ok else 'FAIL'}] command: {cmd}")
        failures += 0 if ok else 1
    if shutil.which("bluetoothctl"):
        ok, text = _run(["bluetoothctl", "list"])
        has_controller = ok and "Controller" in text
        print(f"[{'OK' if has_controller else 'FAIL'}] Bluetooth controller")
        if text: print("     " + text.splitlines()[0])
        failures += 0 if has_controller else 1
    if shutil.which("pactl"):
        ok, text = _run(["pactl", "info"])
        print(f"[{'OK' if ok else 'FAIL'}] PipeWire/PulseAudio compatibility")
        if ok:
            for line in text.splitlines():
                if line.startswith("Server Name:"):
                    print("     " + line)
                    break
        failures += 0 if ok else 1
    print("\nConclusion:")
    if failures:
        print(f"{failures} prerequisite check(s) failed. Fix these before testing the remote.")
        return 1
    print("No ESP32 is required. This PC has the software prerequisites for direct BLE testing.")
    return 0
