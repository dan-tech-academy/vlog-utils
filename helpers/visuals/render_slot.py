"""Draw a catalog template to a silent MP4."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from visuals.layout import centered_box, fit_text, inside, safe_rect


def ease_out_cubic(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def render_template(
    template: str,
    params: dict,
    theme,
    size: tuple[int, int],
    fps: float,
    duration: float,
    out_path: Path,
    *,
    plate: bool = True,
) -> dict:
    width, height = size
    frames = max(1, int(round(float(duration) * float(fps))))
    safe = safe_rect(width, height, theme.margin_v)
    images = [
        _draw(template, params, theme, width, height, safe, index, frames, plate)
        for index in range(frames)
    ]
    _encode(images, Path(out_path), fps)
    return {
        "template": template,
        "frames": frames,
        "duration": frames / float(fps),
        "safe": safe.as_tuple(),
    }


def _draw(template, params, theme, width, height, safe, index, frames, plate):
    if plate:
        color = _rgb(theme.background)
    else:
        color = (0, 0, 0)
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)
    progress = ease_out_cubic((index + 1) / frames)
    accent = _rgb(theme.accent)
    text_color = _rgb(theme.text)
    muted = _rgb(theme.text_muted)
    if template == "stat":
        fitted = fit_text(params.get("value") or "0", theme.font("display").file, int(safe.w), 160, 96)
        box = centered_box(fitted["width"], fitted["height"], safe)
        draw.text((box.x, box.y), fitted["text"], font=fitted["font"], fill=accent)
        label = params.get("label") or ""
        if label:
            small = fit_text(label, theme.font("body").file, int(safe.w), 42, 28)
            draw.text((safe.x, box.y + box.h + 16), small["text"], font=small["font"], fill=muted)
    elif template == "list":
        items = list(params.get("items") or [])
        visible = max(1, int(round(progress * len(items)))) if items else 0
        y = safe.y
        for item in items[:visible]:
            fitted = fit_text(item, theme.font("body").file, int(safe.w) - 40, 48, 32)
            draw.rectangle((safe.x, y + 8, safe.x + 10, y + 28), fill=accent)
            draw.text((safe.x + 24, y), fitted["text"], font=fitted["font"], fill=text_color)
            y += fitted["height"] + 18
    elif template == "comparison":
        mid = safe.x + safe.w / 2
        left = fit_text(params.get("left") or "", theme.font("display").file, int(safe.w / 2) - 40, 54, 32)
        right = fit_text(params.get("right") or "", theme.font("display").file, int(safe.w / 2) - 40, 54, 32)
        draw.text((safe.x, safe.y + 40), left["text"], font=left["font"], fill=text_color)
        if progress > 0.45:
            draw.text((mid + 20, safe.y + 40), right["text"], font=right["font"], fill=accent)
    elif template == "code":
        fitted = fit_text(params.get("text") or "", theme.font("mono").file, int(safe.w) - 48, 40, 28)
        draw.rectangle(
            (safe.x, safe.y, safe.x + safe.w, safe.y + fitted["height"] + 48),
            fill=_rgb(theme.surface),
        )
        shown = fitted["text"][: max(1, int(len(fitted["text"]) * progress))]
        draw.text((safe.x + 24, safe.y + 20), shown + "▍", font=fitted["font"], fill=accent)
    elif template == "question":
        fitted = fit_text(params.get("text") or "", theme.font("display").file, int(safe.w), 64, 36)
        box = centered_box(fitted["width"], fitted["height"], safe)
        draw.text((box.x, box.y), fitted["text"], font=fitted["font"], fill=text_color)
    elif template == "section":
        fitted = fit_text(params.get("label") or "", theme.font("display").file, int(safe.w), 72, 40)
        draw.text((safe.x, safe.y + 20), fitted["text"], font=fitted["font"], fill=text_color)
        rule = int((safe.w * 0.45) * progress)
        draw.rectangle((safe.x, safe.y + fitted["height"] + 36, safe.x + rule, safe.y + fitted["height"] + 44), fill=accent)
    elif template == "quote":
        fitted = fit_text(params.get("text") or "", theme.font("body").file, int(safe.w), 48, 32)
        box = centered_box(fitted["width"], fitted["height"], safe)
        draw.text((box.x, box.y), fitted["text"], font=fitted["font"], fill=text_color)
        if params.get("attribution"):
            small = fit_text(params["attribution"], theme.font("body").file, int(safe.w), 28, 22)
            draw.text((box.x, box.y + box.h + 12), small["text"], font=small["font"], fill=muted)
    else:
        fitted = fit_text(params.get("text") or "", theme.font("display").file, int(safe.w), 68, 36)
        dy = int((1 - progress) * 24)
        box = centered_box(fitted["width"], fitted["height"], safe)
        draw.text((box.x, box.y + dy), fitted["text"], font=fitted["font"], fill=text_color)
    return image


def stat_glyph_box(theme, value: str = "40%") -> dict:
    safe = safe_rect(theme.frame_width, theme.frame_height, theme.margin_v)
    fitted = fit_text(value, theme.font("display").file, int(safe.w), 160, 96)
    box = centered_box(fitted["width"], fitted["height"], safe)
    return {"safe": safe, "glyph": box, "inside": inside(box, safe), "fitted": fitted}


def _encode(frames: list, path: Path, fps: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = frames[0].size
    duration = len(frames) / float(fps)
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t", f"{duration:.3f}",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "30",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart",
        str(path),
    ]
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    assert proc.stdin is not None
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    err = proc.stderr.read() if proc.stderr is not None else b""
    code = proc.wait()
    if code != 0:
        raise RuntimeError(err.decode("utf-8", "replace")[-800:])


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
