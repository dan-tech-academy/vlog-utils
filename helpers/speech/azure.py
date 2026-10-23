"""Azure Speech standard neural TTS.

Word times come from ``synthesis_word_boundary``. Offsets are 100-nanosecond
ticks. If NamMinh or HoaiMy returns no boundaries, the other vi-VN neural
voice is tried, then ``vi-VN-Linh:MAI-Voice-2-Flash``, then the call fails
with that voice id. The WAV is not aligned by a second model.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from speech.base import (
    NoWordBoundaries,
    TICKS_PER_SECOND,
    boundaries_to_words,
    concat_wavs,
    first_voice_with_words,
    split_sentences,
    text_to_ssml,
    wav_duration,
)


def load_azure_credentials() -> tuple[str, str]:
    """Read the key and region from the environment or a repo ``.env``.

    The values are returned to the caller and are not logged.
    """
    found: dict[str, str] = {}
    for candidate in (Path(__file__).resolve().parents[2] / ".env", Path(".env")):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            found.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    key = os.environ.get("AZURE_SPEECH_KEY") or found.get("AZURE_SPEECH_KEY", "")
    region = os.environ.get("AZURE_SPEECH_REGION") or found.get("AZURE_SPEECH_REGION", "")
    return key, region


def credentials_present() -> bool:
    key, region = load_azure_credentials()
    return bool(key and region)


class AzureSynthesizer:
    def synthesize(self, text: str, voice: str, language: str, style: str | None = None) -> dict:
        key, region = load_azure_credentials()
        if not key or not region:
            raise RuntimeError(
                "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION not found in .env or environment"
            )
        sentences = split_sentences(text)
        if len(sentences) <= 1:
            return self._with_fallback(text, voice, language, key, region)
        parts = [
            self._with_fallback(sentence, voice, language, key, region)
            for sentence in sentences
        ]
        return _concat_results(parts, voice, language)

    def _with_fallback(self, text: str, voice: str, language: str, key: str, region: str) -> dict:
        def once(candidate: str) -> dict:
            return _synthesize_one(text, candidate, language, key, region)

        try:
            return first_voice_with_words(voice, once)
        except NoWordBoundaries:
            raise

    def synthesize_one_for_test(self, text, voice, language, key, region):
        return _synthesize_one(text, voice, language, key, region)


def _synthesize_one(text: str, voice: str, language: str, key: str, region: str) -> dict:
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as exc:
        raise RuntimeError(
            "azure-cognitiveservices-speech is not installed. "
            "Install the tts extra: pip install 'azure-cognitiveservices-speech'"
        ) from exc

    folder = Path(tempfile.mkdtemp(prefix="azure-tts-"))
    wav_path = folder / "chunk.wav"
    config = speechsdk.SpeechConfig(subscription=key, region=region)
    config.speech_synthesis_voice_name = voice
    config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
    )
    audio_config = speechsdk.audio.AudioOutputConfig(filename=str(wav_path))
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=config, audio_config=audio_config
    )
    events: list[dict] = []

    def on_boundary(evt) -> None:
        duration = getattr(evt, "duration", 0)
        if hasattr(duration, "total_seconds"):
            duration_ticks = int(round(duration.total_seconds() * TICKS_PER_SECOND))
        else:
            duration_ticks = int(duration)
        events.append(
            {
                "text": evt.text,
                "audio_offset": int(evt.audio_offset),
                "duration": duration_ticks,
            }
        )

    synthesizer.synthesis_word_boundary.connect(on_boundary)
    ssml = text_to_ssml(text, language)
    if ssml:
        result = synthesizer.speak_ssml_async(ssml).get()
    else:
        result = synthesizer.speak_text_async(text).get()
    completed = speechsdk.ResultReason.SynthesizingAudioCompleted
    if result.reason != completed:
        details = getattr(result, "cancellation_details", None)
        reason = getattr(details, "reason", result.reason)
        message = getattr(details, "error_details", "") or ""
        raise RuntimeError(f"Azure synthesis failed ({reason}): {message[:300]}")
    return {
        "audio": wav_path,
        "words": boundaries_to_words(events),
        "sample_rate": 24000,
        "voice": voice,
        "language": language,
    }


def _concat_results(parts: list[dict], voice: str, language: str) -> dict:
    dest_dir = Path(tempfile.mkdtemp(prefix="azure-tts-join-"))
    dest = dest_dir / "joined.wav"
    durations = [wav_duration(Path(part["audio"])) for part in parts]
    concat_wavs([Path(part["audio"]) for part in parts], dest)
    from speech.base import join_chunk_words

    words = join_chunk_words([part["words"] for part in parts], durations)
    return {
        "audio": dest,
        "words": words,
        "sample_rate": parts[0].get("sample_rate", 24000),
        "voice": voice,
        "language": language,
    }
