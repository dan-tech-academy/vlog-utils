"""Watermark, intro, outro, and lower-third layout.

These features stay off until a logo PNG exists and the theme turns them on.
Intro and outro are synthetic sources, so caption offsets keep the usual formula.
"""

from __future__ import annotations

import copy
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class BrandError(Exception):
    pass


class Rect:
    def __init__(self, x: float, y: float, w: float, h: float):
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = float(h)

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.x + self.w <= other.x
            or other.x + other.w <= self.x
            or self.y + self.h <= other.y
            or other.y + other.h <= self.y
        )

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)


def layout_boxes(width: int, height: int, margin_v: int = 90) -> dict[str, Rect]:
    """Caption band and the lower-third above it. They do not share pixels."""
    caption_h = 72
    caption = Rect(0, height - margin_v - caption_h, width, caption_h)
    gap = 16
    lower_h = 110
    lower_w = min(640, max(120, width - 96))
    lower = Rect(48, caption.y - gap - lower_h, lower_w, lower_h)
    mark = Rect(width - 160 - 36, 36, 160, 64)
    return {"caption": caption, "lower_third": lower, "watermark": mark}


def logo_path(theme) -> Path:
    raw = (theme.watermark or {}).get("file") or "brand/logo.png"
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / raw
    return path


def require_logo(theme) -> Path | None:
    """Return the logo when a feature needs it. Missing file is an error."""
    needs = bool((theme.watermark or {}).get("enabled") or (theme.intro or {}).get("enabled"))
    if not needs:
        return None
    path = logo_path(theme)
    if not path.is_file():
        raise BrandError(
            f"logo file not found: {path}. "
            "Drop a PNG at that path, or set watermark.enabled and intro.enabled to false."
        )
    return path


def with_brand_ranges(edl: dict, theme) -> dict:
    """Insert intro and outro sources. A disabled theme returns the same ranges."""
    intro = theme.intro or {}
    outro = theme.outro or {}
    intro_on = bool(intro.get("enabled"))
    outro_on = bool(outro.get("enabled"))
    if not intro_on and not outro_on:
        return edl
    out = copy.deepcopy(edl)
    ranges = list(out.get("ranges") or [])
    if ranges and ranges[0].get("role") == "intro":
        return out
    built: list[dict] = []
    if intro_on:
        built.append(
            {
                "source": "INTRO",
                "start": 0.0,
                "end": float(intro.get("duration_s") or 2.5),
                "role": "intro",
                "beat": "INTRO",
            }
        )
    for segment in ranges:
        item = dict(segment)
        item.setdefault("role", "content")
        built.append(item)
    if outro_on:
        built.append(
            {
                "source": "OUTRO",
                "start": 0.0,
                "end": float(outro.get("duration_s") or 3.5),
                "role": "outro",
                "beat": "OUTRO",
            }
        )
    sources = dict(out.get("sources") or {})
    if intro_on:
        sources["INTRO"] = "brand/intro.mp4"
    if outro_on:
        sources["OUTRO"] = "brand/outro.mp4"
    out["ranges"] = built
    out["sources"] = sources
    return out


def content_segment_offset(ranges: list[dict]) -> float:
    """Output time where the first content range begins."""
    offset = 0.0
    for segment in ranges:
        if segment.get("role", "content") == "content":
            return offset
        offset += float(segment["end"]) - float(segment["start"])
    return offset


def output_caption_time(word_start: float, segment_start: float, segment_offset: float) -> float:
    return word_start - segment_start + segment_offset


def watermark_xy(width: int, height: int, width_px: int = 160, margin: int = 36, corner: str = "top-right") -> tuple[int, int]:
    del height
    if corner == "top-left":
        return margin, margin
    if corner == "bottom-left":
        return margin, margin
    return width - width_px - margin, margin


def append_brand_filters(
    parts: list[str],
    current: str,
    *,
    watermark_input: int | None,
    watermark_xy_px: tuple[int, int] | None,
    subs_clause: str | None,
) -> str:
    """Watermark sits above content overlays and under subtitles."""
    if watermark_input is not None and watermark_xy_px is not None:
        x, y = watermark_xy_px
        parts.append(
            f"[{watermark_input}:v]format=rgba,colorchannelmixer=aa=0.85[wm]"
        )
        parts.append(f"{current}[wm]overlay={x}:{y}:format=auto[vwm]")
        current = "[vwm]"
    if subs_clause:
        parts.append(f"{current}{subs_clause}[outv]")
        return "[outv]"
    if parts:
        parts.append(f"{current}null[outv]")
        return "[outv]"
    return current


def write_card(path: Path, theme, duration: float, lines: list[str]) -> None:
    """Silent brand card. Used for intro and outro sources."""
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = int(theme.frame_width), int(theme.frame_height)
    fps = int(theme.fps) if float(theme.fps) == int(theme.fps) else theme.fps
    color = theme.background.lstrip("#")
    font = str(theme.font("display").file).replace(":", r"\:").replace("'", r"\'")
    draw = []
    y = height // 2 - 40 * max(1, len(lines))
    for line in lines:
        safe = line.replace(":", r"\:").replace("'", r"\'").replace("%", r"\%")
        draw.append(
            f"drawtext=fontfile='{font}':text='{safe}':fontcolor=white:"
            f"fontsize=64:x=(w-text_w)/2:y={y}"
        )
        y += 80
    vf = ",".join(draw) if draw else "null"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x{color}:s={width}x{height}:r={fps}:d={duration:.3f}",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-vf", vf,
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "ultrafast",
        "-c:a", "aac", "-ar", "48000",
        "-movflags", "+faststart",
        str(path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def materialize_cards(edl: dict, theme, edit_dir: Path) -> dict:
    """Write intro/outro files when those ranges were inserted."""
    edl = with_brand_ranges(edl, theme)
    edit_dir = Path(edit_dir)
    if (theme.intro or {}).get("enabled"):
        title = (theme.intro or {}).get("title") or theme.channel_name
        write_card(edit_dir / "brand" / "intro.mp4", theme, float(theme.intro["duration_s"]), [title])
    if (theme.outro or {}).get("enabled"):
        lines = list((theme.outro or {}).get("lines") or [theme.channel_name, theme.handle])
        write_card(
            edit_dir / "brand" / "outro.mp4",
            theme,
            float(theme.outro["duration_s"]),
            lines,
        )
    return edl
