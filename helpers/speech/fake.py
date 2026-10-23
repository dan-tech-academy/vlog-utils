"""Deterministic synthesizer for tests and offline renders. No network."""

from __future__ import annotations

import math
import struct
from pathlib import Path

from speech.base import write_pcm_wav


class FakeSynthesizer:
    def __init__(self, sample_rate: int = 24000, seconds_per_word: float = 0.4):
        self.sample_rate = sample_rate
        self.seconds_per_word = seconds_per_word
        self.calls = 0

    def synthesize(self, text: str, voice: str, language: str, style: str | None = None) -> dict:
        self.calls += 1
        tokens = [tok for tok in text.replace("{{en:", "").replace("}}", "").split() if tok]
        if not tokens:
            tokens = ["…"]
        words = []
        t = 0.0
        for token in tokens:
            words.append(
                {
                    "type": "word",
                    "text": token,
                    "start": t,
                    "end": round(t + self.seconds_per_word, 6),
                }
            )
            t += self.seconds_per_word
        pcm = _tone(self.sample_rate, t, freq=220.0 if language.startswith("vi") else 330.0)
        dest = _scratch(voice, self.calls)
        write_pcm_wav(dest, pcm, self.sample_rate)
        return {
            "audio": dest,
            "words": words,
            "sample_rate": self.sample_rate,
            "voice": voice,
            "language": language,
        }


def _scratch(voice: str, call: int) -> Path:
    folder = Path("/tmp/video-use-fake-tts")
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "-" for ch in voice)[:40]
    return folder / f"{safe}-{call}.wav"


def _tone(sample_rate: int, duration: float, freq: float) -> bytes:
    count = max(1, int(round(duration * sample_rate)))
    frames = bytearray()
    for i in range(count):
        sample = int(8000 * math.sin(2 * math.pi * freq * (i / sample_rate)))
        frames += struct.pack("<h", sample)
    return bytes(frames)
