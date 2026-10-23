"""Classify a footage folder for the talking-head explainer.

The classifier does not call Scribe and does not move files. Speech ratio
comes from a transcript the caller already has. A file that still needs one
is marked ``needs_transcript`` instead of being given a guessed role.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}

FOLDER_ROLES = {
    "voice": "voice",
    "music": "music",
    "sfx": "sfx",
    "broll": "broll",
    "photos": "photo",
    "screen": "broll",
}

TALKING_HEAD_RATIO = 0.45
BROLL_RATIO = 0.15
VOICE_RATIO = 0.40
MUSIC_SPEECH_RATIO = 0.05
MUSIC_MIN_S = 20.0
SFX_MAX_S = 3.0


def speech_ratio(words: list[dict], duration: float) -> float:
    """Voiced time divided by duration. Overlapping words are merged."""
    if duration <= 0:
        return 0.0
    spans = []
    for word in words or []:
        try:
            start = float(word["start"])
            end = float(word["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end > start:
            spans.append((start, end))
    spans.sort()
    merged: list[list[float]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    voiced = sum(end - start for start, end in merged)
    return min(1.0, voiced / float(duration))


def _folder_role(path: Path, root: Path) -> str | None:
    try:
        parts = path.resolve().relative_to(root.resolve()).parts[:-1]
    except ValueError:
        parts = path.parts[:-1]
    for part in parts:
        if part in FOLDER_ROLES:
            return FOLDER_ROLES[part]
    return None


def _kind(path: Path, probe: dict) -> str:
    kind = probe.get("kind")
    if kind in ("image", "audio", "video"):
        return kind
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXT:
        return "image"
    if suffix in AUDIO_EXT:
        return "audio"
    if suffix in VIDEO_EXT:
        return "video"
    return "other"


def classify_probe(path: Path, probe: dict, transcript: dict | None, folder_role: str | None) -> dict:
    """One inventory entry. ``transcript`` is ``{"words": [...], "path": str|None}`` or None."""
    kind = _kind(path, probe)
    duration = float(probe.get("duration_s") or 0.0)
    has_audio = bool(probe.get("has_audio", kind == "audio"))
    words = (transcript or {}).get("words") if transcript else None
    ratio = speech_ratio(words, duration) if words is not None else None
    needs = False
    role = None
    source = "probe"

    if kind == "image" or folder_role == "photo":
        role = "photo"
        source = "folder" if folder_role == "photo" else "probe"
    elif folder_role == "sfx" or (kind == "audio" and duration < SFX_MAX_S and folder_role != "music"):
        role = "sfx"
        source = "folder" if folder_role == "sfx" else "probe"
    elif folder_role == "music":
        role = "music"
        source = "folder"
    elif folder_role == "broll":
        role = "broll"
        source = "folder"
    elif folder_role == "voice" and kind == "audio":
        role = "voice"
        source = "folder"
    elif kind == "video" and not has_audio:
        role = "broll"
        source = "probe"
    elif kind in ("audio", "video"):
        if words is None:
            needs = True
            source = "probe"
        else:
            source = "scribe"
            if kind == "audio":
                if ratio is not None and ratio > VOICE_RATIO:
                    role = "voice"
                elif ratio is not None and ratio < MUSIC_SPEECH_RATIO and duration > MUSIC_MIN_S:
                    role = "music"
                else:
                    role = "ambiguous"
            else:
                if ratio is not None and ratio > TALKING_HEAD_RATIO:
                    role = "talking_head"
                elif ratio is not None and ratio < BROLL_RATIO:
                    role = "broll"
                else:
                    role = "ambiguous"
    else:
        role = "ambiguous"

    return {
        "path": str(path),
        "role": role,
        "duration_s": duration,
        "width": probe.get("width"),
        "height": probe.get("height"),
        "fps": probe.get("fps"),
        "has_audio": has_audio,
        "speech_ratio": ratio,
        "transcript": (transcript or {}).get("path") if transcript else None,
        "source": source,
        "needs_transcript": needs,
    }


def iter_asset_files(folder: Path):
    root = Path(folder).resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.resolve().relative_to(root)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        if "edit" in rel.parts:
            continue
        try:
            path.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError:
            yield path
            continue
        # A file that lives in this repo is the engine, not footage.
        continue


def ffprobe_media(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height,avg_frame_rate",
        "-of", "json",
        str(path),
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(out.stdout or "{}")
    duration = float((data.get("format") or {}).get("duration") or 0.0)
    width = height = None
    fps = None
    has_audio = False
    kind = _kind(path, {})
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "audio":
            has_audio = True
        if stream.get("codec_type") == "video" and width is None:
            width = stream.get("width")
            height = stream.get("height")
            rate = stream.get("avg_frame_rate") or ""
            if rate and rate != "0/0" and "/" in rate:
                num, den = rate.split("/", 1)
                if float(den) != 0:
                    fps = float(num) / float(den)
            kind = "video"
    if kind == "image":
        has_audio = False
    return {
        "kind": kind,
        "duration_s": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": has_audio,
    }


def build_inventory(
    folder: Path,
    *,
    probes: dict | None = None,
    transcripts: dict | None = None,
) -> dict:
    """``probes`` and ``transcripts`` are keyed by path relative to ``folder``."""
    folder = Path(folder)
    files = []
    for path in iter_asset_files(folder):
        rel = path.resolve().relative_to(folder.resolve()).as_posix()
        probe = dict((probes or {}).get(rel) or {})
        if not probe:
            probe = ffprobe_media(path)
        transcript = (transcripts or {}).get(rel)
        entry = classify_probe(path, probe, transcript, _folder_role(path, folder))
        entry["path"] = rel
        files.append(entry)
    return {"folder": str(folder), "files": files}


def apply_look(inventory: dict, rel_path: str, role: str) -> dict:
    """Record a timeline_view decision. ``role`` is ``talking_head`` or ``broll``."""
    if role not in ("talking_head", "broll"):
        raise ValueError(f"look role must be talking_head or broll, got {role!r}")
    for entry in inventory.get("files") or []:
        if entry.get("path") == rel_path:
            entry["role"] = role
            entry["source"] = "look"
            entry["needs_transcript"] = False
            return entry
    raise KeyError(rel_path)


def write_inventory(inventory: dict, edit_dir: Path) -> Path:
    dest = Path(edit_dir) / "inventory.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(inventory, indent=2))
    return dest


def roles_present(inventory: dict) -> set[str]:
    return {entry["role"] for entry in inventory.get("files") or [] if entry.get("role")}
