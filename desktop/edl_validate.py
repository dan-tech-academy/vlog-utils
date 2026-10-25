"""EDL checks the storyboard and the render button share.

Word edges come from Scribe `type == "word"` entries. Padding must sit in the
30–200ms window unless the media itself has less room at that edge.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PAD_MIN = 0.03
PAD_MAX = 0.20
EPS = 0.001


@dataclass
class Validation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    render_edl: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def probe_duration(path: Path) -> float | None:
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def load_words(edit_dir: Path, source_key: str) -> tuple[list[tuple[float, float]], bool]:
    path = edit_dir / "transcripts" / f"{source_key}.json"
    if not path.is_file():
        return [], False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], True
    words: list[tuple[float, float]] = []
    for entry in data.get("words") or []:
        if entry.get("type") != "word":
            continue
        start = entry.get("start")
        end = entry.get("end")
        if start is None or end is None:
            continue
        words.append((float(start), float(end)))
    words.sort()
    return words, True


def _inside(t: float, words: list[tuple[float, float]]) -> bool:
    return any(start + EPS < t < end - EPS for start, end in words)


def _resolve(maybe: str, edit_dir: Path) -> Path:
    path = Path(maybe)
    if path.is_absolute():
        return path
    return (edit_dir / path).resolve()


def validate_edl(
    edl: dict,
    edit_dir: Path,
    *,
    durations: dict[str, float] | None = None,
    probe: bool = True,
) -> Validation:
    errors: list[str] = []
    warnings: list[str] = []
    render_edl = json.loads(json.dumps(edl))
    sources = edl.get("sources")
    ranges = edl.get("ranges")
    if not isinstance(sources, dict) or not sources:
        errors.append("EDL thiếu sources.")
        sources = {}
    if not isinstance(ranges, list) or not ranges:
        errors.append("EDL không có range nào.")
        ranges = []

    for index, raw in enumerate(ranges):
        label = f"range {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{label} không phải object.")
            continue
        key = raw.get("source")
        if not isinstance(key, str) or key not in sources:
            errors.append(f"{label} trỏ tới nguồn không có trong sources.")
            continue
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{label} thiếu start/end hợp lệ.")
            continue
        if end <= start:
            errors.append(f"{label}: start phải nhỏ hơn end.")
            continue

        source_path = _resolve(str(sources[key]), edit_dir)
        if not source_path.is_file():
            errors.append(f"Không thấy file nguồn {key}: {source_path}")
            continue
        if source_path.stem != key:
            errors.append(
                f"Khóa nguồn {key} phải trùng tên file {source_path.stem} để phụ đề khớp transcript."
            )

        words, found = load_words(edit_dir, key)
        if not found:
            errors.append(f"Thiếu transcript cho {key}.")
            continue
        if not words:
            continue

        if _inside(start, words) or _inside(end, words):
            errors.append(f"Cắt nằm giữa một từ của {key}.")

        kept = [word for word in words if word[1] > start + EPS and word[0] < end - EPS]
        if not kept:
            continue
        first = min(word[0] for word in kept)
        last = max(word[1] for word in kept)
        pad_in = first - start
        pad_out = end - last
        duration = None
        if durations is not None and key in durations:
            duration = durations[key]
        elif probe:
            duration = probe_duration(source_path)
        if duration is not None and end > duration + 0.02:
            errors.append(f"{label} kết thúc sau độ dài của {key}.")

        room_before = first
        at_start = start <= EPS and room_before < PAD_MIN
        if pad_in < -EPS:
            errors.append(f"Đệm đầu của {key} cắt vào trong từ.")
        elif not at_start and not (PAD_MIN - EPS <= pad_in <= PAD_MAX + EPS):
            errors.append(
                f"Đệm đầu {pad_in * 1000:.0f}ms của {key} ngoài cửa sổ 30–200ms."
            )

        room_after = None if duration is None else duration - last
        at_end = (
            duration is not None
            and end >= duration - 0.02
            and room_after is not None
            and room_after < PAD_MIN
        )
        if pad_out < -EPS:
            errors.append(f"Đệm cuối của {key} cắt vào trong từ.")
        elif not at_end and not (PAD_MIN - EPS <= pad_out <= PAD_MAX + EPS):
            errors.append(
                f"Đệm cuối {pad_out * 1000:.0f}ms của {key} ngoài cửa sổ 30–200ms."
            )

    kept_overlays: list[dict] = []
    overlays = edl.get("overlays") or []
    if overlays and not isinstance(overlays, list):
        errors.append("overlays phải là một list.")
        overlays = []
    for overlay in overlays:
        if not isinstance(overlay, dict) or not overlay.get("file"):
            warnings.append("Bỏ qua overlay thiếu file.")
            continue
        path = _resolve(str(overlay["file"]), edit_dir)
        if not path.is_file():
            warnings.append(f"Overlay không tồn tại, sẽ không render: {overlay['file']}")
            continue
        kept_overlays.append(overlay)
    if "overlays" in render_edl:
        render_edl["overlays"] = kept_overlays

    return Validation(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        render_edl=render_edl,
    )
