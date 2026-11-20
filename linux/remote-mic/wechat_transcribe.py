#!/usr/bin/env python3
"""Offline Whisper inference in a short-lived process (zero idle model RAM)."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys

MODEL_CACHE = Path(__file__).resolve().parent / '.vendor' / 'stt-models'


def transcribe(wav_file: str) -> str:
    from faster_whisper import WhisperModel
    model_name = os.environ.get('XIAOMI_WECHAT_STT_MODEL', 'base')
    model = WhisperModel(model_name, device='cpu', compute_type='int8',
                         download_root=str(MODEL_CACHE), local_files_only=True,
                         cpu_threads=4)
    # Pass PCM samples directly. Newer PyAV releases removed metadata_errors
    # from av.open(), while faster-whisper's filename decoder still uses it.
    import numpy as np
    import wave
    with wave.open(wav_file, 'rb') as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2 or stream.getframerate() != 16000:
            raise ValueError('expected mono signed-16-bit 16kHz WAV')
        pcm = stream.readframes(stream.getnframes())
    audio = np.frombuffer(pcm, dtype='<i2').astype('float32') / 32768.0
    segments, _ = model.transcribe(audio, language='zh', beam_size=3,
                                   vad_filter=True, condition_on_previous_text=False,
                                   no_speech_threshold=0.65)
    return ''.join(segment.text for segment in segments).strip()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: wechat_transcribe.py audio.wav')
    print(json.dumps({'text':transcribe(sys.argv[1])}, ensure_ascii=False))
