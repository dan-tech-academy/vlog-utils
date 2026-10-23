"""edge-tts dev fallback.

Unofficial client of the Edge read-aloud endpoint. Same voice names as Azure,
and WordBoundary offsets use the same 100-nanosecond ticks. Not the publish path.
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from speech.base import NoWordBoundaries, boundaries_to_words, text_to_ssml


class EdgeSynthesizer:
    dev_only = True

    def synthesize(self, text: str, voice: str, language: str, style: str | None = None) -> dict:
        spoken = _plain_text(text)
        try:
            return asyncio.run(_stream(spoken, voice, language))
        except NoWordBoundaries:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"edge-tts failed for voice {voice}: {exc}") from exc


def _plain_text(text: str) -> str:
    """Drop SSML markers. edge-tts escapes its own SSML and would speak the tags."""
    if text_to_ssml(text, "vi") is None:
        return text
    import re

    return re.sub(r"\{\{en:(.+?)\}\}", r"\1", text)


async def _stream(text: str, voice: str, language: str) -> dict:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError(
            "edge-tts is not installed. Install the tts-edge extra: pip install edge-tts"
        ) from exc

    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    audio = bytearray()
    events: list[dict] = []
    async for chunk in communicate.stream():
        kind = chunk["type"]
        if kind == "audio":
            audio += chunk["data"]
        elif kind == "WordBoundary":
            events.append(
                {
                    "text": chunk.get("text") or "",
                    "audio_offset": chunk["offset"],
                    "duration": chunk["duration"],
                }
            )
    if not audio:
        raise RuntimeError(f"edge-tts voice {voice} returned no audio")
    words = boundaries_to_words(events)
    if not words:
        raise NoWordBoundaries(f"edge-tts voice {voice} emitted no word boundaries")
    folder = Path(tempfile.mkdtemp(prefix="edge-tts-"))
    mp3_path = folder / "voice.mp3"
    wav_path = folder / "voice.wav"
    mp3_path.write_bytes(audio)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp3_path),
            "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
            str(wav_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {
        "audio": wav_path,
        "words": words,
        "sample_rate": 24000,
        "voice": voice,
        "language": language,
    }
