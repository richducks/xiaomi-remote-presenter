from __future__ import annotations

import array
import shutil
import subprocess


class VirtualMicError(RuntimeError):
    pass


class PulseVirtualMic:
    """PipeWire/PulseAudio-compatible virtual microphone using a null-sink monitor."""

    def __init__(self, sink_name: str = "xiaomi_remote_mic_sink") -> None:
        self.sink_name = sink_name
        self.module_id: str | None = None
        self.player: subprocess.Popen | None = None

    @property
    def source_name(self) -> str:
        return f"{self.sink_name}.monitor"

    def start(self) -> None:
        for cmd in ("pactl", "paplay"):
            if shutil.which(cmd) is None:
                raise VirtualMicError(f"missing command: {cmd}")
        result = subprocess.run(
            ["pactl", "load-module", "module-null-sink",
             f"sink_name={self.sink_name}", "rate=16000", "channels=1",
             "sink_properties=device.description=Xiaomi_Remote_Mic_Sink"],
            text=True, capture_output=True,
        )
        if result.returncode != 0:
            # Reuse an existing sink when a prior unclean run left it loaded.
            check = subprocess.run(["pactl", "list", "short", "sinks"], text=True, capture_output=True)
            if self.sink_name not in check.stdout:
                raise VirtualMicError(result.stderr.strip() or "failed to create virtual sink")
        else:
            self.module_id = result.stdout.strip()
        subprocess.run(
            ["pactl", "set-source-properties", self.source_name,
             "device.description=Xiaomi Remote Microphone"],
            text=True, capture_output=True,
        )
        self.player = subprocess.Popen(
            ["paplay", "--raw", "--rate=16000", "--channels=1", "--format=s16le",
             f"--device={self.sink_name}"],
            stdin=subprocess.PIPE,
        )

    def write_samples(self, samples: list[int]) -> None:
        if not samples or self.player is None or self.player.stdin is None:
            return
        pcm = array.array("h", samples)
        if pcm.itemsize != 2:
            raise VirtualMicError("unexpected host int16 size")
        self.player.stdin.write(pcm.tobytes())
        self.player.stdin.flush()

    def close(self) -> None:
        if self.player is not None:
            try:
                if self.player.stdin:
                    self.player.stdin.close()
                self.player.terminate()
                self.player.wait(timeout=1)
            except Exception:
                try: self.player.kill()
                except Exception: pass
            self.player = None
        if self.module_id:
            subprocess.run(["pactl", "unload-module", self.module_id], capture_output=True)
            self.module_id = None
