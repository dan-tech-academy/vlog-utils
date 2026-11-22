"""EDL checks the storyboard and the render button share.

Word edges come from Scribe `type == "word"` entries. Padding must sit in the
30–200ms window unless the media itself has less room at that edge.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from desktop.media import KIND_AUDIO, KIND_DOC, KIND_IMAGE, asset_kind

PAD_MIN = 0.03
PAD_MAX = 0.20
EPS = 0.001

EFFECTS = {"static", "zoom_in", "zoom_out", "pan_left", "pan_right", "punch_in"}
TRANSITIONS = {
    "fade", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circleopen", "circleclose", "fadeblack", "fadewhite",
}
TRANSITION_MIN_S = 0.1
TRANSITION_MAX_S = 3.0


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


def load_word_entries(edit_dir: Path, source_key: str) -> list[dict]:
    path = edit_dir / "transcripts" / f"{source_key}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = []
    for entry in data.get("words") or []:
        if entry.get("type") != "word" or entry.get("start") is None or entry.get("end") is None:
            continue
        entries.append({
            "start": float(entry["start"]),
            "end": float(entry["end"]),
            "text": str(entry.get("text") or "").strip(),
        })
    entries.sort(key=lambda item: item["start"])
    return entries


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

        kind = asset_kind(source_path)
        if kind in (KIND_AUDIO, KIND_DOC):
            errors.append(f"{label}: nguồn {key} là {kind}, không thể là cảnh trong video.")
            continue

        effect = raw.get("effect")
        if effect is not None and str(effect) not in EFFECTS:
            errors.append(
                f"{label}: effect '{effect}' không hợp lệ (cho phép: {', '.join(sorted(EFFECTS))})."
            )

        seg_grade = raw.get("grade")
        if seg_grade is not None and not str(seg_grade).strip():
            errors.append(f"{label}: grade không được rỗng.")

        transition = raw.get("transition_in")
        if transition is not None:
            if index == 0:
                errors.append(f"{label}: transition_in chỉ đặt trên cảnh thứ hai trở đi.")
            elif not isinstance(transition, dict):
                errors.append(f"{label}: transition_in phải là object.")
            else:
                ttype = str(transition.get("type") or "")
                if ttype not in TRANSITIONS:
                    errors.append(
                        f"{label}: transition '{ttype}' không hỗ trợ (cho phép: {', '.join(sorted(TRANSITIONS))})."
                    )
                try:
                    tdur = float(transition.get("duration_s"))
                except (TypeError, ValueError):
                    errors.append(f"{label}: transition_in thiếu duration_s.")
                    tdur = None
                if tdur is not None and not (TRANSITION_MIN_S <= tdur <= TRANSITION_MAX_S):
                    errors.append(
                        f"{label}: transition {tdur:.2f}s ngoài cửa sổ {TRANSITION_MIN_S}–{TRANSITION_MAX_S}s."
                    )
                if tdur is not None:
                    prev = ranges[index - 1]
                    prev_dur = float(prev.get("end", 0)) - float(prev.get("start", 0))
                    if tdur >= min(end - start, prev_dur):
                        errors.append(f"{label}: transition dài hơn cảnh cạnh nó.")

        if kind == KIND_IMAGE:
            continue

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

    audio = edl.get("audio")
    if audio is not None:
        if not isinstance(audio, dict):
            errors.append("audio phải là một object.")
        else:
            total = 0.0
            for index, row in enumerate(ranges):
                if isinstance(row, dict):
                    try:
                        total += float(row["end"]) - float(row["start"])
                    except (KeyError, TypeError, ValueError):
                        pass
            music = audio.get("music")
            if music is not None:
                if not isinstance(music, dict):
                    errors.append("audio.music phải là object.")
                else:
                    mkey = music.get("source")
                    mpath = sources.get(mkey)
                    mkind = asset_kind(_resolve(str(mpath), edit_dir)) if mpath else None
                    if not isinstance(mkey, str) or mkey not in sources:
                        errors.append("audio.music.source không có trong sources.")
                    elif mkind != KIND_AUDIO:
                        errors.append(f"audio.music.source {mkey} không phải file âm thanh.")
                    try:
                        vol = float(music.get("volume", 0.25))
                        if not 0.0 <= vol <= 1.0:
                            errors.append("audio.music.volume ngoài 0–1.")
                    except (TypeError, ValueError):
                        errors.append("audio.music.volume không hợp lệ.")
                    for fade_key in ("fade_in_s", "fade_out_s"):
                        if music.get(fade_key) is not None:
                            try:
                                if float(music[fade_key]) < 0:
                                    errors.append(f"audio.music.{fade_key} phải ≥ 0.")
                            except (TypeError, ValueError):
                                errors.append(f"audio.music.{fade_key} không hợp lệ.")
            sfx = audio.get("sfx")
            if sfx is not None:
                if not isinstance(sfx, list):
                    errors.append("audio.sfx phải là list.")
                else:
                    for sindex, item in enumerate(sfx):
                        label = f"audio.sfx[{sindex}]"
                        if not isinstance(item, dict):
                            errors.append(f"{label} không phải object.")
                            continue
                        skey = item.get("source")
                        spath = sources.get(skey)
                        skind = asset_kind(_resolve(str(spath), edit_dir)) if spath else None
                        if not isinstance(skey, str) or skey not in sources:
                            errors.append(f"{label}: source không có trong sources.")
                        elif skind != KIND_AUDIO:
                            errors.append(f"{label}: {skey} không phải file âm thanh.")
                        try:
                            at = float(item.get("at_s"))
                            if at < 0:
                                errors.append(f"{label}: at_s phải ≥ 0.")
                            elif total and at > total:
                                warnings.append(f"{label}: đặt sau cuối video ({at:.1f}s > {total:.1f}s).")
                        except (TypeError, ValueError):
                            errors.append(f"{label}: at_s không hợp lệ.")
                        if item.get("volume") is not None:
                            try:
                                if not 0.0 <= float(item["volume"]) <= 1.0:
                                    errors.append(f"{label}: volume ngoài 0–1.")
                            except (TypeError, ValueError):
                                errors.append(f"{label}: volume không hợp lệ.")

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
