from __future__ import annotations

from evdev import InputDevice, categorize, ecodes, list_devices

MATCH_NAMES = ("MI RC", "Xiaomi", "remote", "小米", "遥控器")


def run_button_diagnostics() -> int:
    devices = []
    denied = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except PermissionError:
            denied.append(path)
            continue
        except OSError:
            continue
        name = dev.name or ""
        if any(token.lower() in name.lower() for token in MATCH_NAMES):
            devices.append(dev)
    if not devices:
        if denied:
            print("Input devices exist but this user cannot read /dev/input/event*. Button mapping requires input-group or udev access.")
            print("Voice-over-BLE does not require this permission.")
            return 2
        print("No likely Xiaomi remote evdev device found. Pair/connect it first.")
        return 1
    if len(devices) > 1:
        print("Multiple candidate input devices found; events from all are shown:")
    for dev in devices:
        print(f"- {dev.path}: {dev.name} phys={dev.phys}")
    print("Press remote buttons. Ctrl+C to stop.\n")
    import selectors
    sel = selectors.DefaultSelector()
    for dev in devices:
        sel.register(dev.fd, selectors.EVENT_READ, dev)
    try:
        while True:
            for key, _ in sel.select(timeout=1):
                dev = key.data
                for event in dev.read():
                    if event.type in (ecodes.EV_KEY, ecodes.EV_REL, ecodes.EV_ABS):
                        print(dev.path, categorize(event))
    except KeyboardInterrupt:
        return 0
