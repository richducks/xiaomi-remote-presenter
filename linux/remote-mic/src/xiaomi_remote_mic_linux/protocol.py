from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

VOICE_SERVICE_UUID = "AB5E0001-5A21-4F05-BC7D-AF01F617B664"
VOICE_TX_UUID = "AB5E0002-5A21-4F05-BC7D-AF01F617B664"
VOICE_AUDIO_UUID = "AB5E0003-5A21-4F05-BC7D-AF01F617B664"
VOICE_CONTROL_UUID = "AB5E0004-5A21-4F05-BC7D-AF01F617B664"
GET_CAPABILITIES_V10 = bytes((0x0A, 0x01, 0x00, 0x00, 0x03, 0x03))

OPCODE_AUDIO_STOP = 0x00
OPCODE_AUDIO_START = 0x04
OPCODE_MIC_BUTTON = 0x08
OPCODE_AUDIO_SYNC = 0x0A
OPCODE_CAPS = 0x0B

DEFAULT_FRAME_SIZE = 120
SUPPORTED_SAMPLE_RATE_HZ = 16000


def mic_open_command(version: int) -> bytes:
    return bytes((0x0C, 0x00)) if version >= 0x0100 else bytes((0x0C, 0x00, 0x00))


def mic_close_command(version: int, session_id: int) -> bytes:
    return bytes((0x0D, session_id & 0xFF)) if version >= 0x0100 else bytes((0x0D,))


@dataclass(frozen=True)
class ATVVCapabilities:
    version: int
    codecs: int
    interaction: int
    frame_size: int
    selected_codec: int
    sample_rate: float

    @classmethod
    def parse(cls, data: bytes) -> Optional["ATVVCapabilities"]:
        if len(data) < 7 or data[0] != OPCODE_CAPS:
            return None
        version = (data[1] << 8) | data[2]
        if version >= 0x0100:
            codecs = data[3]
            interaction = data[4]
            if codecs == 0 and len(data) >= 9 and (data[4] & 0x03):
                codecs = data[4]
                interaction = 0x03
        else:
            if len(data) < 9:
                return None
            codecs = data[4]
            interaction = 0
        frame_size = (data[5] << 8) | data[6]
        selected_codec = 0x02 if codecs & 0x02 else 0x01
        return cls(
            version=version,
            codecs=codecs,
            interaction=interaction,
            frame_size=frame_size or DEFAULT_FRAME_SIZE,
            selected_codec=selected_codec,
            sample_rate=16000.0 if selected_codec == 0x02 else 8000.0,
        )


class IMAADPCMDecoder:
    _STEP_TABLE = (
        7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,
        73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,
        449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,
        2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,
        7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,
        24623,27086,29794,32767,
    )
    _INDEX_TABLE = (-1,-1,-1,-1,2,4,6,8)

    def __init__(self) -> None:
        self.reset()

    def reset(self, predictor: int = 0, step_index: int = 0) -> None:
        self.predictor = max(-32768, min(32767, predictor))
        self.step_index = max(0, min(88, step_index))

    def decode(self, data: bytes) -> list[int]:
        out: list[int] = []
        for byte in data:
            out.append(self._decode_nibble(byte >> 4))
            out.append(self._decode_nibble(byte & 0x0F))
        return out

    def _decode_nibble(self, nibble: int) -> int:
        step = self._STEP_TABLE[self.step_index]
        diff = step >> 3
        if nibble & 1: diff += step >> 2
        if nibble & 2: diff += step >> 1
        if nibble & 4: diff += step
        self.predictor += -diff if nibble & 8 else diff
        self.predictor = max(-32768, min(32767, self.predictor))
        self.step_index += self._INDEX_TABLE[nibble & 7]
        self.step_index = max(0, min(88, self.step_index))
        return self.predictor


class DCHighPassFilter:
    def __init__(self, sample_rate: float = 16000.0, cutoff_hz: float = 20.0) -> None:
        self._alpha = math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)
        self.reset()

    def reset(self) -> None:
        self._previous_input = 0.0
        self._previous_output = 0.0
        self._initialized = False

    def process(self, samples: Sequence[int]) -> list[int]:
        if not samples:
            return []
        if not self._initialized:
            self._previous_input = float(samples[0])
            self._initialized = True
        out = []
        for sample in samples:
            current = float(sample)
            value = current - self._previous_input + self._alpha * self._previous_output
            self._previous_input = current
            self._previous_output = value
            out.append(max(-32768, min(32767, int(round(value)))))
        return out


def postprocess(samples: Sequence[int], gain_db: float = 10.0) -> list[int]:
    if not samples:
        return []
    filtered = list(samples)
    if len(samples) >= 3:
        for i in range(1, len(samples)-1):
            filtered[i] = (samples[i-1] + 2*samples[i] + samples[i+1]) >> 2
    gain = 10.0 ** (max(-24.0, min(24.0, gain_db)) / 20.0)
    return [max(-32768, min(32767, int(round(v * gain)))) for v in filtered]


class FrameAccumulator:
    def __init__(self) -> None:
        self.pending = bytearray()

    def append(self, data: bytes, frame_size: int) -> list[bytes]:
        self.pending.extend(data)
        out = []
        while frame_size > 0 and len(self.pending) >= frame_size:
            out.append(bytes(self.pending[:frame_size]))
            del self.pending[:frame_size]
        return out

    def reset(self) -> None:
        self.pending.clear()


class ATVVSession:
    def __init__(self, gain_db: float = 10.0) -> None:
        self.gain_db = gain_db
        self.decoder = IMAADPCMDecoder()
        self.dc = DCHighPassFilter()
        self.frames = FrameAccumulator()
        self.frame_size = DEFAULT_FRAME_SIZE
        self.version = 0
        self.caps: Optional[ATVVCapabilities] = None
        self.pending_sync: Optional[tuple[int,int]] = None
        self.mic_open = False
        self.session_id = 0

    def handle_control(self, payload: bytes) -> tuple[str, object | None]:
        if not payload:
            raise ValueError("empty ATVV control payload")
        opcode = payload[0]
        if opcode == OPCODE_CAPS:
            caps = ATVVCapabilities.parse(payload)
            if caps is None:
                raise ValueError("malformed ATVV CAPS payload")
            if caps.sample_rate != SUPPORTED_SAMPLE_RATE_HZ:
                raise ValueError(f"unsupported ATVV sample rate: {caps.sample_rate}")
            self.caps = caps
            self.version = caps.version
            self.frame_size = caps.frame_size
            return "caps", caps
        if opcode == OPCODE_MIC_BUTTON:
            return "mic_button", None
        if opcode == OPCODE_AUDIO_START:
            self.decoder.reset(); self.dc.reset(); self.frames.reset(); self.pending_sync = None
            self.mic_open = True
            self.session_id = payload[3] if len(payload) >= 4 else 0
            return "audio_start", self.session_id
        if opcode == OPCODE_AUDIO_STOP:
            self.mic_open = False
            self.frames.reset()
            return "audio_stop", payload[1] if len(payload) >= 2 else None
        if opcode == OPCODE_AUDIO_SYNC and len(payload) >= 7:
            self.pending_sync = (int.from_bytes(payload[4:6], "big", signed=True), payload[6])
            return "audio_sync", self.pending_sync
        return "unknown", opcode

    def handle_audio(self, payload: bytes) -> list[int]:
        if not self.mic_open:
            return []
        out: list[int] = []
        for frame in self.frames.append(payload, self.frame_size):
            if self.pending_sync is not None:
                self.decoder.reset(*self.pending_sync)
                self.dc.reset()
                self.pending_sync = None
            out.extend(postprocess(self.dc.process(self.decoder.decode(frame)), self.gain_db))
        return out

    def open_command(self) -> bytes:
        return mic_open_command(self.version)

    def close_command(self) -> bytes:
        return mic_close_command(self.version, self.session_id)
