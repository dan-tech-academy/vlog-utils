"""Pack a folder's non-video assets into <edit>/assets.md for the editing agent.

Images get pixel dimensions, audio gets duration, doc files (.md/.txt) get their
content inlined (truncated). The agent uses this manifest to place stills,
music beds and SFX in the EDL, and to follow the script the user dropped in.

Usage:
    python helpers/pack_assets.py <folder>
    python helpers/pack_assets.py <folder> --edit-dir /custom/edit
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
DOC_EXTS = {".md", ".txt"}
DOC_MAX_CHARS = 6000


def _files(folder: Path, exts: set[str]) -> list[Path]:
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts),
        key=lambda p: p.name.lower(),
    )


def probe_stream(path: Path) -> dict:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_type,width,height:format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, timeout=20, check=True,
        )
        return json.loads(out.stdout)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def _duration_of(data: dict) -> float | None:
    try:
        return float((data.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        return None


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    return f"{m}m {seconds - m * 60:04.1f}s"


def render_markdown(folder: Path, images: list[Path], audio: list[Path], docs: list[Path]) -> str:
    lines: list[str] = []
    lines.append("# Assets in this folder")
    lines.append("")
    lines.append("Non-video sources the EDL may use. Reference them in `sources` by filename stem.")
    lines.append("")

    lines.append("## Images")
    if not images:
        lines.append("_(none)_")
    for path in images:
        data = probe_stream(path)
        stream = next((s for s in data.get("streams") or [] if s.get("codec_type") == "video"), {})
        w, h = stream.get("width"), stream.get("height")
        dims = f"{w}×{h}" if w and h else "unknown size"
        orientation = ""
        if w and h:
            orientation = " portrait" if h > w else (" landscape" if w > h else " square")
        lines.append(f"- `{path.stem}` — {path.name} — {dims}{orientation}")
        lines.append(f"  Use as a still scene: `{{\"source\": \"{path.stem}\", \"start\": 0, \"end\": <seconds>}}`.")
    lines.append("")

    lines.append("## Audio (music beds and SFX)")
    if not audio:
        lines.append("_(none)_")
    for path in audio:
        dur = _duration_of(probe_stream(path))
        lines.append(f"- `{path.stem}` — {path.name}" + (f" — {format_duration(dur)}" if dur else ""))
    lines.append("  Reference in the EDL `audio.music` or `audio.sfx` block.")
    lines.append("")

    lines.append("## Docs / script")
    if not docs:
        lines.append("_(none)_")
    for path in docs:
        lines.append(f"### {path.name}")
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            text = ""
        if len(text) > DOC_MAX_CHARS:
            text = text[:DOC_MAX_CHARS] + "\n…(truncated)"
        lines.append(text if text else "_(empty file)_")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pack non-video assets into assets.md")
    ap.add_argument("folder", type=Path, help="Footage folder to scan (top level only)")
    ap.add_argument("--edit-dir", type=Path, default=None, help="Edit dir (default: <folder>/edit)")
    args = ap.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        sys.exit(f"not a directory: {folder}")
    edit_dir = (args.edit_dir or folder / "edit").resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)

    images = _files(folder, IMAGE_EXTS)
    audio = _files(folder, AUDIO_EXTS)
    docs = _files(folder, DOC_EXTS)

    out_path = edit_dir / "assets.md"
    out_path.write_text(render_markdown(folder, images, audio, docs), encoding="utf-8")
    print(f"packed {len(images)} images, {len(audio)} audio, {len(docs)} docs → {out_path}")


if __name__ == "__main__":
    main()
