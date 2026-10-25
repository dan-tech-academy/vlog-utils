"""Footage inventory. Extensions match helpers/transcribe_batch.py."""

from __future__ import annotations

from pathlib import Path

# Same membership as helpers/transcribe_batch.VIDEO_EXTS, including the
# lowercase-only ".m4v" entry. Comparison is case-sensitive on the suffix.
VIDEO_EXTS = {".mp4", ".MP4", ".mov", ".MOV", ".mkv", ".MKV", ".avi", ".AVI", ".m4v"}


def list_videos(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    videos = [p for p in folder.iterdir() if p.is_file() and p.suffix in VIDEO_EXTS]
    return sorted(videos, key=lambda p: p.name.lower())


def transcript_file(edit_dir: Path, video: Path) -> Path:
    """Track 0 cache path. Matches helpers/transcribe.transcript_path for track 0."""
    return edit_dir / "transcripts" / f"{video.stem}.json"
