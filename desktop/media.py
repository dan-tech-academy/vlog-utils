"""Footage inventory. Extensions match helpers/transcribe_batch.py."""

from __future__ import annotations

from pathlib import Path

# Same membership as helpers/transcribe_batch.VIDEO_EXTS, including the
# lowercase-only ".m4v" entry. Comparison is case-sensitive on the suffix.
VIDEO_EXTS = {".mp4", ".MP4", ".mov", ".MOV", ".mkv", ".MKV", ".avi", ".AVI", ".m4v"}

IMAGE_EXTS = {
    ".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG", ".webp", ".WEBP",
    ".bmp", ".BMP", ".tif", ".TIF", ".tiff", ".TIFF",
}
AUDIO_EXTS = {
    ".mp3", ".MP3", ".wav", ".WAV", ".m4a", ".M4A", ".aac", ".AAC",
    ".ogg", ".OGG", ".flac", ".FLAC", ".opus", ".OPUS",
}
DOC_EXTS = {".md", ".MD", ".txt", ".TXT"}

KIND_VIDEO = "video"
KIND_IMAGE = "image"
KIND_AUDIO = "audio"
KIND_DOC = "doc"


def _files(folder: Path, exts: set[str]) -> list[Path]:
    if not folder.is_dir():
        return []
    found = [p for p in folder.iterdir() if p.is_file() and p.suffix in exts]
    return sorted(found, key=lambda p: p.name.lower())


def list_videos(folder: Path) -> list[Path]:
    return _files(folder, VIDEO_EXTS)


def list_images(folder: Path) -> list[Path]:
    return _files(folder, IMAGE_EXTS)


def list_audio(folder: Path) -> list[Path]:
    return _files(folder, AUDIO_EXTS)


def list_docs(folder: Path) -> list[Path]:
    return _files(folder, DOC_EXTS)


def asset_kind(path: Path) -> str | None:
    suffix = path.suffix
    if suffix in VIDEO_EXTS:
        return KIND_VIDEO
    if suffix in IMAGE_EXTS:
        return KIND_IMAGE
    if suffix in AUDIO_EXTS:
        return KIND_AUDIO
    if suffix in DOC_EXTS:
        return KIND_DOC
    return None


def list_assets(folder: Path) -> dict[str, list[Path]]:
    return {
        KIND_VIDEO: list_videos(folder),
        KIND_IMAGE: list_images(folder),
        KIND_AUDIO: list_audio(folder),
        KIND_DOC: list_docs(folder),
    }


def transcript_file(edit_dir: Path, video: Path) -> Path:
    """Track 0 cache path. Matches helpers/transcribe.transcript_path for track 0."""
    return edit_dir / "transcripts" / f"{video.stem}.json"
