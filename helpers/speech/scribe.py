"""Footage transcription. This is the Scribe adapter, not a TTS timer."""

from __future__ import annotations

import json
from pathlib import Path


def transcribe(
    media,
    language: str | None = None,
    num_speakers: int | None = None,
    audio_track: int = 0,
    edit_dir: Path | None = None,
    api_key: str | None = None,
) -> dict:
    from transcribe import load_api_key, transcribe_one

    video = Path(media)
    folder = Path(edit_dir) if edit_dir is not None else video.parent / "edit"
    key = api_key if api_key is not None else load_api_key()
    path = transcribe_one(
        video,
        folder,
        key,
        language=language,
        num_speakers=num_speakers,
        audio_track=audio_track,
    )
    return json.loads(Path(path).read_text())
