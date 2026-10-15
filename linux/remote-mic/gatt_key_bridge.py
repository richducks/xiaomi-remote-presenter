
"""RC003 GATT input fallback when BlueZ connects but provides no evdev HID.

Never captures any other HID, never creates an input device when physical RC003
HID exists. Produces only keys directly observed in keyboard Report ID 1.
The existing video_only_hid.py process remains the only app-aware remapper.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from evdev import InputDevice, UInput, ecodes, list_devices
from bleak import BleakClient
from xiaomi_remote_mic_linux.ble_voice import _resolve_target, scan
from key_layers import SYSTEM_KEY_CODES

LOG = logging.getLogger("xiaomi-remote-gatt-key-bridge")
VID, PID = 0x2717, 0x32B8
PROXY_NAME = "Xiaomi RC003 GATT Key Proxy"
OTHER_VIRTUAL = {"Xiaomi Remote Video Only", "Xiaomi Remote 2 Pro Filtered"}
REPORT_UUID = "00002a4d-0000-1000-8000-00805f9b34fb"
REFERENCE_UUID = "00002908-0000-1000-8000-00805f9b34fb"
# HID consumer-control report (Report ID 3 on RC003) is a separate GATT
# notification characteristic. Do not treat it as an 8-byte keyboard report.
CONSUMER_REPORT_ID = b"\x03\x01"
CONSUMER_USAGES = {
    0x00E9: ecodes.KEY_VOLUMEUP,
    0x00EA: ecodes.KEY_VOLUMEDOWN,
    0x00E2: ecodes.KEY_MUTE,
    0x0030: ecodes.KEY_POWER,    # standard HID Consumer power
    0x0032: ecodes.KEY_SLEEP,    # standard HID Consumer sleep
    0x006F: ecodes.KEY_BRIGHTNESSUP,
    0x0070: ecodes.KEY_BRIGHTNESSDOWN,
}
# These codes use USB HID Keyboard/Keypad usage page 0x07; RC003 0xF1
# is observed to be its Back button, though not a standard keyboard usage.
KEYS = {
    0x28: ecodes.KEY_ENTER,
    0x29: ecodes.KEY_ESC,
    0x35: ecodes.KEY_GRAVE,
    0x4A: ecodes.KEY_HOME,
    0x4D: ecodes.KEY_END,
    0x4B: ecodes.KEY_PAGEUP,
    0x4E: ecodes.KEY_PAGEDOWN,
    0x4F: ecodes.KEY_RIGHT,
    0x50: ecodes.KEY_LEFT,
    0x51: ecodes.KEY_DOWN,
    0x52: ecodes.KEY_UP,
    0x65: ecodes.KEY_COMPOSE,
    # HID Keyboard/Keypad page media usages. RC003 firmware may emit these
    # on Report ID 1 rather than the separate Consumer Report ID 3.
    0x7F: ecodes.KEY_MUTE,
    0x80: ecodes.KEY_VOLUMEUP,
    0x81: ecodes.KEY_VOLUMEDOWN,
    0x66: ecodes.KEY_POWER,  # standard HID Keyboard system power
    0xF1: ecodes.KEY_BACK,
}
SHORT_COOLDOWN = {ecodes.KEY_UP, ecodes.KEY_DOWN, ecodes.KEY_LEFT, ecodes.KEY_RIGHT,
                  ecodes.KEY_VOLUMEUP, ecodes.KEY_VOLUMEDOWN,
                  ecodes.KEY_BRIGHTNESSUP, ecodes.KEY_BRIGHTNESSDOWN}
DANGEROUS_COOLDOWN = frozenset({ecodes.KEY_POWER, ecodes.KEY_SLEEP})
DEBOUNCE_SECS = 0.18
ACTION_COOLDOWN_SECS = 0.95
ACTION_REPEAT_GAP_SECS = 0.7  # repeated down/up packets during a held key

def physical_hid_present() -> bool:
    for path in list_devices():
        try:
            device = InputDevice(path)
            try:
                if (device.info.vendor, device.info.product) == (VID, PID) and (
                    device.name not in OTHER_VIRTUAL and device.name != PROXY_NAME
                ):
                    return True
            finally:
                device.close()
        except OSError:
            continue
    return False

def consumer_codes(data: bytes) -> frozenset[int]:
    """Decode only *standard* HID Consumer Page usages, never guess bitmasks.

    Unknown/vendor reports are ignored and logged without writing keys.
    """
    if len(data) != 2:
        return frozenset()
    usage = int.from_bytes(data, "little")
    if usage == 0:
        return frozenset()
    key = CONSUMER_USAGES.get(usage)
    return frozenset((key,)) if key is not None else frozenset()


def keyboard_codes(data: bytes) -> frozenset[int]:
    if len(data) != 8:
        return frozenset()
    # Byte 0 modifiers, byte 1 reserved, bytes 2..7 USB keyboard usages.
    # Firmware returns f1 for RC003 Back. Unknown codes deliberately ignored.
    return frozenset(KEYS[code] for code in data[2:] if code in KEYS)

class KeyTranslator:
    def __init__(self, ui: UInput):
        self.ui = ui
        self.held: set[int] = set()
        self.last_down: dict[int, float] = {}
        self.last_raw: dict[int, float] = {}

    def feed(self, data: bytes, now: float | None = None, *, kind: str = "keyboard") -> None:
        if kind == "keyboard" and len(data) != 8:
            return
        if kind == "consumer" and len(data) != 2:
            return
        if kind not in ("keyboard", "consumer"):
            return
        now = time.monotonic() if now is None else now
        wanted = keyboard_codes(data) if kind == "keyboard" else consumer_codes(data)
        previous_raw = {key: self.last_raw.get(key, -float("inf")) for key in wanted}
        for key in wanted:
            self.last_raw[key] = now
        for key in self.held - wanted:
            self.ui.write(ecodes.EV_KEY, key, 0)
        new_held = self.held & wanted
        for key in wanted - self.held:
            minimum = (5.0 if key in DANGEROUS_COOLDOWN else
                       DEBOUNCE_SECS if key in SHORT_COOLDOWN else ACTION_COOLDOWN_SECS)
            is_burst = (
                key not in SHORT_COOLDOWN
                and now - previous_raw[key] < ACTION_REPEAT_GAP_SECS
            )
            if not is_burst and now - self.last_down.get(key, -float("inf")) >= minimum:
                new_held.add(key)
                self.last_down[key] = now
                self.ui.write(ecodes.EV_KEY, key, 1)
                LOG.info("key code %s down", ecodes.KEY[key])
            else:
                LOG.debug("debounced key %s", ecodes.KEY[key])
        self.held = new_held
        self.ui.syn()

    def release(self):
        if self.held:
            for key in self.held:
                self.ui.write(ecodes.EV_KEY, key, 0)
            self.ui.syn()
        self.held.clear()

async def report_characteristic(client: BleakClient, reference: bytes = b"\x01\x01"):
    # Report Reference 0x2908: 01 01 = Keyboard Input, 03 01 = Consumer Input.
    for c in client.services.characteristics.values():
        if str(c.uuid).lower() != REPORT_UUID or "notify" not in c.properties:
            continue
        for desc in c.descriptors:
            if str(desc.uuid).lower() == REFERENCE_UUID:
                try:
                    data = bytes(await client.read_gatt_descriptor(desc.handle))
                    if data == reference:
                        return c
                except Exception as exc:
                    LOG.warning("descriptor read failed: %s", exc)
    if reference == b"\x01\x01":
        raise RuntimeError("RC003 keyboard input report ID 1 not found")
    return None

async def run_once(address: str):
    if physical_hid_present():
        LOG.info("native HID exists; no proxy input created")
        await asyncio.sleep(5)
        return
    target, preserve = await _resolve_target(address)
    client = BleakClient(target, timeout=20.0)
    ui = None
    characteristic = None
    consumer_characteristic = None
    try:
        await client.connect()
        characteristic = await report_characteristic(client)
        consumer_characteristic = await report_characteristic(client, CONSUMER_REPORT_ID)
        # Keep the proxy's VID:PID to integrate with existing known-safe filter,
        # but an unmistakably virtual name allows physical-HID detection.
        # systemd-udevd input_id only recognizes a keyboard if its evdev
        # capabilities cover a broad keyboard range. A device exposing only
        # navigation keys gets ID_INPUT_KEY=1 but *not* ID_INPUT_KEYBOARD=1;
        # GNOME/libinput then silently ignores the synthetic Ctrl+T.
        # These are advertised capabilities ONLY: unknown usages are never
        # emitted by KeyTranslator, which still uses the strict KEYS allowlist.
        keyboard_capabilities = sorted(set(KEYS.values()) | set(range(1, 129)))
        ui = UInput({ecodes.EV_KEY: sorted(set(keyboard_capabilities) | SYSTEM_KEY_CODES | set(CONSUMER_USAGES.values()))},
                    name=PROXY_NAME, bustype=ecodes.BUS_BLUETOOTH,
                    vendor=VID, product=PID, version=0x00A4,
                    phys="xiaomi-rc003-gatt-proxy")
        translator = KeyTranslator(ui)
        consumer_translator = KeyTranslator(ui)
        def callback(sender, data):
            translator.feed(bytes(data))
        await client.start_notify(characteristic, callback)
        if consumer_characteristic is not None:
            def on_consumer(sender, data):
                raw = bytes(data)
                if raw != b"\x00\x00" and not consumer_codes(raw):
                    LOG.info("unknown consumer report len=%d bytes=%s (ignored)", len(raw), raw.hex(" "))
                consumer_translator.feed(raw, kind="consumer")
            await client.start_notify(consumer_characteristic, on_consumer)
            LOG.info("Consumer HID report %s subscribed", hex(consumer_characteristic.handle))
        LOG.info("READY GATT input proxy: %s, HID report handle 0x%x", (ui.device.path if ui.device is not None else "registration pending"), characteristic.handle)
        while client.is_connected:
            await asyncio.sleep(1)
            if physical_hid_present():
                LOG.warning("native HID returned; stopping fallback proxy")
                break
    finally:
        if ui is not None:
            try:
                translator.release()
                if consumer_characteristic is not None:
                    consumer_translator.release()
            except Exception:
                pass
            try:
                ui.close()
            except Exception:
                pass
        if characteristic is not None:
            try:
                await client.stop_notify(characteristic)
            except Exception:
                pass
        if consumer_characteristic is not None:
            try:
                await client.stop_notify(consumer_characteristic)
            except Exception:
                pass
        cleanup = getattr(getattr(client, "_backend", None), "_cleanup_all", None)
        if preserve and callable(cleanup):
            cleanup()
        else:
            try:
                await client.disconnect()
            except Exception:
                pass

async def main():
    address = os.getenv("XIAOMI_REMOTE_ADDRESS")
    if not address:
        candidates = await scan(6.0)
        if len(candidates) != 1:
            raise RuntimeError("Expected exactly one paired RC003; specify XIAOMI_REMOTE_ADDRESS")
        address = candidates[0].address
    LOG.info("starting read-only BLE-HID decoding for paired RC003")
    while True:
        try:
            await run_once(address)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("input proxy lost; retrying")
            await asyncio.sleep(5)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
