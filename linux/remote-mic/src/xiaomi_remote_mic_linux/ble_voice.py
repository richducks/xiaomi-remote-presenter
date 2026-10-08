from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import protocol
from .audio import PulseVirtualMic

LOG = logging.getLogger("xiaomi-remote-mic")
NAMES = ("MI RC", "Xiaomi Bluetooth Remote 2 Pro", "小米蓝牙语音遥控器")
_BLUEZ_DEVICE_IFACE = "org.bluez.Device1"


@dataclass(frozen=True)
class Candidate:
    name: str
    address: str


def _is_rc003(name: str, props: dict | None = None) -> bool:
    name = (name or "").strip()
    if name in NAMES or "MI RC" in name.upper():
        return True
    props = props or {}
    uuids = {str(v).casefold() for v in props.get("UUIDs", [])}
    modalias = str(props.get("Modalias", "")).casefold()
    return (
        protocol.VOICE_SERVICE_UUID.casefold() in uuids
        or ("v2717" in modalias and "p32b8" in modalias)
    )


async def _known_bluez_devices() -> list[BLEDevice]:
    """Return BlueZ-known devices, including paired devices that are not advertising.

    Bleak's public scanner only returns advertisements. RC003 normally remains
    connected as a HID device and may stop advertising, so on Linux we also
    consume Bleak's BlueZ manager cache to reuse the already-known D-Bus path.
    The private API is isolated here so future Bleak changes have one fallback
    point; failure simply falls back to normal scanning.
    """
    try:
        from bleak.backends.bluezdbus.manager import get_global_bluez_manager

        manager = await get_global_bluez_manager()
        properties = getattr(manager, "_properties", {})
    except Exception as exc:
        LOG.debug("BlueZ known-device lookup unavailable: %s", exc)
        return []

    out: list[BLEDevice] = []
    for path, interfaces in properties.items():
        if not isinstance(interfaces, dict):
            continue
        props = interfaces.get(_BLUEZ_DEVICE_IFACE)
        if not isinstance(props, dict):
            continue
        address = str(props.get("Address", "")).strip()
        if not address:
            continue
        name = str(props.get("Alias") or props.get("Name") or "").strip()
        if not _is_rc003(name, props):
            continue
        out.append(BLEDevice(address, name or None, {"path": path, "props": props}))
    return out


async def scan(timeout: float = 8.0) -> list[Candidate]:
    found: dict[str, Candidate] = {}

    # First include paired/connected BlueZ objects; this is the normal RC003
    # steady state and does not require the remote to wake and advertise.
    for d in await _known_bluez_devices():
        found[d.address.casefold()] = Candidate(d.name or "MI RC", d.address)

    # A paired/connected RC003 is the normal steady state. Return it immediately
    # instead of forcing a six-second discovery cycle on every service start.
    if found:
        return list(found.values())

    # Otherwise merge advertisements so a newly pairing/unpaired remote is visible.
    try:
        devices = await BleakScanner.discover(timeout=timeout)
    except Exception as exc:
        LOG.debug("active BLE scan failed: %s", exc)
        devices = []
    for d in devices:
        name = (d.name or "").strip()
        if _is_rc003(name):
            found[d.address.casefold()] = Candidate(name or "MI RC", d.address)
    return list(found.values())


async def _resolve_target(address: str) -> tuple[BLEDevice | str, bool]:
    """Resolve a MAC to a BlueZ-known BLEDevice without forcing re-discovery.

    Returns (target, preserve_physical_connection). When the RC003 was already
    connected before this process attached, cleanup must release only our D-Bus
    resources and leave the HID/BLE physical connection intact.
    """
    wanted = address.casefold()
    for d in await _known_bluez_devices():
        if d.address.casefold() != wanted:
            continue
        props = d.details.get("props", {}) if isinstance(d.details, dict) else {}
        return d, bool(props.get("Connected", False))

    # Last-resort public Bleak resolution for a device not yet in BlueZ cache.
    try:
        d = await BleakScanner.find_device_by_address(address, timeout=8.0)
    except Exception:
        d = None
    return (d if d is not None else address), False


class LinuxATVVBridge:
    def __init__(self, address: str, gain_db: float = 10.0) -> None:
        self.address = address
        self.session = protocol.ATVVSession(gain_db=gain_db)
        self.audio = PulseVirtualMic()
        self.client: BleakClient | None = None
        self.caps_ready = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._loop = asyncio.get_running_loop()
        self._open_pending = False
        self._frames = 0
        self._samples = 0
        self._peak = 0

    async def _write_tx(self, data: bytes) -> None:
        if self.client is None or not self.client.is_connected:
            return
        async with self._write_lock:
            await self.client.write_gatt_char(protocol.VOICE_TX_UUID, data, response=True)

    def _control_cb(self, _char, data: bytearray) -> None:
        payload = bytes(data)
        try:
            kind, value = self.session.handle_control(payload)
        except Exception as exc:
            LOG.error("ATVV control error: %s", exc)
            return
        LOG.info("ATVV control: %s%s", kind, f" {value}" if value is not None else "")
        if kind == "caps":
            self.caps_ready.set()
        elif kind == "mic_button":
            if not self._open_pending and not self.session.mic_open:
                self._open_pending = True
                asyncio.run_coroutine_threadsafe(self._send_open(), self._loop)
        elif kind == "audio_start":
            self._open_pending = False
            self._frames = self._samples = self._peak = 0
        elif kind == "audio_stop":
            self._open_pending = False
            LOG.info(
                "voice stats: frames=%d samples=%d peak=%d",
                self._frames,
                self._samples,
                self._peak,
            )

    async def _send_open(self) -> None:
        try:
            await self._write_tx(self.session.open_command())
            LOG.info("MIC_OPEN sent")
        except Exception as exc:
            self._open_pending = False
            LOG.error("MIC_OPEN failed: %s", exc)

    def _audio_cb(self, _char, data: bytearray) -> None:
        try:
            samples = self.session.handle_audio(bytes(data))
            if not samples:
                return
            self._frames += 1
            self._samples += len(samples)
            self._peak = max(self._peak, max(abs(v) for v in samples))
            self.audio.write_samples(samples)
        except Exception as exc:
            LOG.error("audio pipeline error: %s", exc)

    async def _release_client(self, client: BleakClient, preserve_connection: bool) -> None:
        # Remove our notification subscriptions first, but do not disconnect
        # an RC003 that was already connected for HID before this bridge ran.
        for uuid in (protocol.VOICE_AUDIO_UUID, protocol.VOICE_CONTROL_UUID):
            try:
                await client.stop_notify(uuid)
            except Exception:
                pass

        if preserve_connection:
            backend = getattr(client, "_backend", None)
            cleanup = getattr(backend, "_cleanup_all", None)
            if callable(cleanup):
                cleanup()
                LOG.info("released BLE client resources; preserved existing HID connection")
                return
        try:
            await client.disconnect()
        except Exception as exc:
            LOG.debug("BLE disconnect cleanup: %s", exc)

    async def run(self) -> None:
        self.audio.start()
        LOG.info("virtual microphone: %s", self.audio.source_name)
        client: BleakClient | None = None
        preserve_connection = False
        try:
            target, preserve_connection = await _resolve_target(self.address)
            client = BleakClient(target, timeout=20.0)
            self.client = client
            await client.connect()
            LOG.info("BLE connected%s", " (reused BlueZ HID connection)" if preserve_connection else "")
            services = client.services
            uuids = {str(s.uuid).upper() for s in services}
            if protocol.VOICE_SERVICE_UUID.upper() not in uuids:
                raise RuntimeError("ATVV voice service not found; wrong device or BlueZ did not expose GATT")
            await client.start_notify(protocol.VOICE_AUDIO_UUID, self._audio_cb)
            await client.start_notify(protocol.VOICE_CONTROL_UUID, self._control_cb)
            await self._write_tx(protocol.GET_CAPABILITIES_V10)
            try:
                await asyncio.wait_for(self.caps_ready.wait(), timeout=5.0)
            except TimeoutError as exc:
                raise RuntimeError("ATVV capability negotiation timed out") from exc
            caps = self.session.caps
            LOG.info(
                "ATVV ready: version=0x%04x frame=%d rate=%.0f",
                caps.version,
                caps.frame_size,
                caps.sample_rate,
            )
            while client.is_connected:
                await asyncio.sleep(1.0)
        finally:
            if self.client is not None and self.session.mic_open:
                try:
                    await self._write_tx(self.session.close_command())
                except Exception:
                    pass
            self.client = None
            if client is not None:
                await self._release_client(client, preserve_connection)
            self.audio.close()
