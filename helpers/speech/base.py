"""Provider-neutral speech helpers.

Word ``start`` and ``end`` are seconds. Azure and edge-tts both report
word-boundary offsets as 100-nanosecond ticks (10_000_000 ticks = 1 second).
``edge_tts.submaker`` divides those ticks by 10 to get microseconds, and
``edge_tts.constants`` documents the same unit.
"""

from __future__ import annotations

import hashlib
import json
import re
import wave
from pathlib import Path

TICKS_PER_SECOND = 10_000_000

_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_EN_TOKEN = re.compile(r"\{\{en:(.+?)\}\}")

VI_BOUNDARY_VOICES = (
    "vi-VN-NamMinhNeural",
    "vi-VN-HoaiMyNeural",
    "vi-VN-Linh:MAI-Voice-2-Flash",
)


class NoWordBoundaries(RuntimeError):
    """The voice returned audio and no word-boundary events."""


def boundaries_to_words(events: list[dict], time_offset: float = 0.0) -> list[dict]:
    """Convert tick-based boundary events into Scribe-shaped words."""
    words: list[dict] = []
    for event in events:
        text = (event.get("text") or "").strip()
        if not text:
            continue
        start = round(float(event["audio_offset"]) / TICKS_PER_SECOND + time_offset, 6)
        end = round(start + float(event["duration"]) / TICKS_PER_SECOND, 6)
        words.append({"type": "word", "text": text, "start": start, "end": end})
    return words


def words_are_monotonic(words: list[dict]) -> bool:
    previous = 0.0
    for word in words:
        start = float(word["start"])
        end = float(word["end"])
        if word.get("type") != "word" or end <= start or start < previous - 1e-6:
            return False
        previous = end
    return True


def split_sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    parts = [part.strip() for part in _SENTENCE.split(stripped) if part.strip()]
    return parts or [stripped]


def shift_words(words: list[dict], offset: float) -> list[dict]:
    shifted = []
    for word in words:
        shifted.append(
            {
                **word,
                "start": float(word["start"]) + offset,
                "end": float(word["end"]) + offset,
            }
        )
    return shifted


def join_chunk_words(chunks: list[list[dict]], durations: list[float]) -> list[dict]:
    """Place each chunk on a running timeline. ``durations`` are seconds of audio."""
    joined: list[dict] = []
    offset = 0.0
    for words, duration in zip(chunks, durations):
        joined.extend(shift_words(words, offset))
        offset += float(duration)
    return joined


def voices_to_try(voice: str) -> list[str]:
    """NamMinh and HoaiMy fall through to each other, then to Linh. Then stop."""
    if voice not in ("vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"):
        return [voice]
    ordered = [voice]
    for candidate in VI_BOUNDARY_VOICES:
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered


def first_voice_with_words(voice: str, synthesize_one) -> dict:
    """Call ``synthesize_one(voice)`` until a result contains words.

    The last voice id is in the error. This does not align the WAV.
    """
    tried: list[str] = []
    for candidate in voices_to_try(voice):
        tried.append(candidate)
        result = synthesize_one(candidate)
        if result.get("words"):
            result["voice"] = candidate
            return result
    raise NoWordBoundaries(f"Azure voice {tried[-1]} emitted no word boundaries")


def text_to_ssml(text: str, language: str) -> str | None:
    """Wrap ``{{en:...}}`` tokens in SSML. Plain text stays plain.

    The adapter does not invent a pronunciation for unmarked English words.
    """
    if "{{en:" not in text:
        return None
    pieces: list[str] = []
    cursor = 0
    for match in _EN_TOKEN.finditer(text):
        pieces.append(_xml_escape(text[cursor : match.start()]))
        pieces.append(
            f'<lang xml:lang="en-US">{_xml_escape(match.group(1))}</lang>'
        )
        cursor = match.end()
    pieces.append(_xml_escape(text[cursor:]))
    xml_lang = "vi-VN" if language.lower().startswith("vi") else "en-US"
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{xml_lang}">{"".join(pieces)}</speak>'
    )


def cache_key(provider: str, voice: str, language: str, style: str | None, text: str) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "voice": voice,
            "language": language,
            "style": style or "",
            "text": text,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def synthesize_cached(
    edit_dir: Path,
    provider: str,
    voice: str,
    language: str,
    text: str,
    synthesize,
    style: str | None = None,
) -> dict:
    """Return wav + words, calling ``synthesize`` only on a cache miss."""
    folder = Path(edit_dir) / "audio" / "tts"
    folder.mkdir(parents=True, exist_ok=True)
    key = cache_key(provider, voice, language, style, text)
    wav_path = folder / f"{key}.wav"
    words_path = folder / f"{key}.words.json"
    if wav_path.is_file() and words_path.is_file():
        meta = json.loads(words_path.read_text())
        return {
            "audio": wav_path,
            "words": meta["words"],
            "sample_rate": meta.get("sample_rate"),
            "voice": meta.get("voice", voice),
            "language": meta.get("language", language),
            "cached": True,
        }
    result = synthesize(text, voice, language, style)
    audio = Path(result["audio"])
    if audio.resolve() != wav_path.resolve():
        wav_path.write_bytes(audio.read_bytes())
    words_path.write_text(
        json.dumps(
            {
                "words": result["words"],
                "sample_rate": result.get("sample_rate"),
                "voice": result.get("voice", voice),
                "language": result.get("language", language),
                "provider": provider,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    stored = dict(result)
    stored["audio"] = wav_path
    stored["cached"] = False
    return stored


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate() or 1
        return handle.getnframes() / float(rate)


def write_pcm_wav(path: Path, pcm: bytes, sample_rate: int, channels: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


def concat_wavs(paths: list[Path], dest: Path) -> float:
    if not paths:
        raise ValueError("concat_wavs needs at least one file")
    with wave.open(str(paths[0]), "rb") as first:
        params = first.getparams()
        frames = [first.readframes(first.getnframes())]
    for path in paths[1:]:
        with wave.open(str(path), "rb") as handle:
            if handle.getparams()[:3] != params[:3]:
                raise ValueError(f"wav format mismatch: {path}")
            frames.append(handle.readframes(handle.getnframes()))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as out:
        out.setparams(params)
        for blob in frames:
            out.writeframes(blob)
    return wav_duration(dest)


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
