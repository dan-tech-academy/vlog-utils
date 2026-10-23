"""Alpha cards and the lower-third for one explainer render.

``render.py`` calls ``bake_plan`` when ``edit/visual_plan.json`` exists.
The card is an rgba clip placed on the safe rect. The A-roll stays visible
around it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from explainer_layout import card_rect, delivery, lower_third_rect
from style import load_style


def _hex(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def render_card_png(path: Path, theme, lines: list[str], width: int, height: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (max(2, int(width)), max(2, int(height))), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    surface = _hex(theme.surface) + (230,)
    accent = _hex(theme.accent) + (255,)
    text = _hex(theme.text) + (255,)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=28, fill=surface)
    draw.rectangle((0, 0, 14, height), fill=accent)
    font_path = theme.font("display").file
    y = 36
    for index, line in enumerate(lines):
        size = 96 if index == 0 else 36
        font = _font(font_path, size)
        draw.text((40, y), line, font=font, fill=text if index else accent)
        y += size + 16
    image.save(path)
    return path


def render_lower_third_png(path: Path, theme, width: int, height: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (max(2, int(width)), max(2, int(height))), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    accent = _hex(theme.accent) + (255,)
    text = _hex(theme.text) + (255,)
    muted = _hex(theme.text_muted) + (255,)
    draw.rectangle((0, 0, 8, height), fill=accent)
    name_font = _font(theme.font("display").file, 36)
    handle_font = _font(theme.font("body").file, 24)
    spec = theme.lower_third or {}
    draw.text((24, 8), spec.get("name") or theme.channel_name, font=name_font, fill=text)
    draw.text((24, 52), spec.get("handle") or theme.handle, font=handle_font, fill=muted)
    image.save(path)
    return path


def encode_rgba(png: Path, dest: Path, duration: float, fps: int = 30) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(png),
        "-t", f"{max(0.1, duration):.3f}",
        "-r", str(fps),
        "-c:v", "qtrle", "-pix_fmt", "argb",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return dest


def apply_run_to_theme(theme, edit_dir: Path):
    """Frame size for this run only. Colors and fonts stay on the channel theme."""
    path = Path(edit_dir) / "style-run.json"
    if not path.is_file():
        return None
    run = json.loads(path.read_text())
    if run.get("style") not in (None, "explainer"):
        return run
    style = load_style()
    box = delivery(style, run.get("orientation") or "portrait", run.get("chrome") or "clean")
    theme.frame_width = box["width"]
    theme.frame_height = box["height"]
    theme.margin_v = box["margin_v"]
    theme.caption_font_size = box["font_size"]
    theme.frame_mode = "force"
    theme.explainer_style = style
    theme.explainer_run = run
    theme.explainer_box = box
    return run


def _lines_for(segment: dict) -> list[str]:
    treatment = segment.get("treatment") or {}
    lines = []
    text = treatment.get("text")
    if isinstance(text, str) and text.strip():
        lines.append(text.strip())
    data = treatment.get("data") or {}
    if isinstance(data, dict):
        if data.get("type") == "comparison":
            before = data.get("before") or ""
            after = data.get("after") or ""
            if before or after:
                lines.append(f"{before} → {after}".strip())
        for item in data.get("items") or []:
            lines.append(str(item))
    return lines or [segment.get("quote") or ""]


def bake_plan(edl: dict, edit_dir: Path, theme) -> dict:
    """Add alpha overlays, SFX events, and the music id from the visual plan."""
    edit_dir = Path(edit_dir)
    plan_path = edit_dir / "visual_plan.json"
    if not plan_path.is_file():
        return edl
    plan = json.loads(plan_path.read_text())
    style = getattr(theme, "explainer_style", None) or load_style()
    run = getattr(theme, "explainer_run", None) or {"orientation": "portrait", "chrome": "clean"}
    box = getattr(theme, "explainer_box", None) or delivery(
        style, run.get("orientation") or "portrait", run.get("chrome") or "clean",
    )
    out = dict(edl)
    if not out.get("overlays"):
        overlays = []
        visuals = edit_dir / "visuals"
        visuals.mkdir(parents=True, exist_ok=True)
        for segment in plan.get("segments") or []:
            treatment = segment.get("treatment") or {}
            layout = treatment.get("layout") or "clean"
            rect = card_rect(box, layout, face_center_x=segment.get("face_center_x"))
            if rect is None or "start" not in segment:
                continue
            duration = max(0.2, float(segment["end"]) - float(segment["start"]))
            png = visuals / f"{segment.get('id', 'card')}.png"
            mov = visuals / f"{segment.get('id', 'card')}.mov"
            render_card_png(png, theme, _lines_for(segment), int(rect.w), int(rect.h))
            encode_rgba(png, mov, duration)
            overlays.append({
                "file": str(mov),
                "start_in_output": float(segment["start"]),
                "duration": duration,
                "x": int(rect.x),
                "y": int(rect.y),
                "alpha": True,
            })
        if (style.get("brand") or {}).get("lower_third", True):
            lower = lower_third_rect(box)
            hold = 3.0 if box["orientation"] == "portrait" else 4.0
            png = visuals / "lower-third.png"
            mov = visuals / "lower-third.mov"
            render_lower_third_png(png, theme, int(lower.w), int(lower.h))
            encode_rgba(png, mov, hold)
            overlays.insert(0, {
                "file": str(mov),
                "start_in_output": 0.0,
                "duration": hold,
                "x": int(lower.x),
                "y": int(lower.y),
                "alpha": True,
            })
        out["overlays"] = overlays
    audio = dict(out.get("audio") or {})
    if "events" not in audio and "sfx" not in audio:
        events = []
        for segment in plan.get("segments") or []:
            kind = (segment.get("treatment") or {}).get("sfx")
            if kind and "end" in segment:
                events.append({"kind": kind, "at": float(segment["end"])})
        audio["events"] = events
    music = plan.get("music") or {}
    if music and "music" not in audio:
        if music.get("source") == "folder":
            audio["music"] = {"file": music["file"], "picked_from": "folder"}
        elif music.get("source") == "library" and music.get("id"):
            audio["music"] = {"id": music["id"], "picked_from": "library"}
    if audio:
        out["audio"] = audio
        out["version"] = max(int(out.get("version") or 1), 2)
    captions = dict(out.get("captions") or {})
    captions.setdefault("style", (style.get("captions") or {}).get("style") or "sentence")
    captions.setdefault("language", style.get("language") or "vi")
    out["captions"] = captions
    out["language"] = captions["language"]
    frame = dict(out.get("frame") or {})
    frame.setdefault("width", box["width"])
    frame.setdefault("height", box["height"])
    out["frame"] = frame
    _apply_punch_ins(out, plan)
    return out


def _apply_punch_ins(edl: dict, plan: dict) -> None:
    """A punch-in is a further scale around the crop the plan already has.

    With no crop, the window is the whole source. The agent still chooses
    the window. This only adds the zoom the motion named.
    """
    wanted = {
        segment.get("quote")
        for segment in plan.get("segments") or []
        if (segment.get("treatment") or {}).get("motion") == "punch-in"
    }
    if not wanted:
        return
    from inventory import ffprobe_media

    for segment in edl.get("ranges") or []:
        if segment.get("quote") not in wanted:
            continue
        crop = dict(segment.get("crop") or {})
        if not crop.get("w") or not crop.get("h"):
            src = (edl.get("sources") or {}).get(segment.get("source"))
            if not src:
                continue
            probe = ffprobe_media(Path(src))
            width = int(probe.get("width") or 0)
            height = int(probe.get("height") or 0)
            if width < 2 or height < 2:
                continue
            width -= width % 2
            height -= height % 2
            crop = {
                "x": 0,
                "y": 0,
                "w": width,
                "h": height,
                "source": "look",
                "why": "Punch-in around the frame the plan asked for.",
            }
        crop["zoom"] = max(float(crop.get("zoom") or 1.0), 1.15)
        segment["crop"] = crop
