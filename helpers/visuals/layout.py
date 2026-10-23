"""Safe rect and text fitting. Glyphs stay out of the caption band."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from brand import Rect, layout_boxes


def safe_rect(width: int, height: int, margin_v: int = 90) -> Rect:
    boxes = layout_boxes(width, height, margin_v)
    left = 80
    top = max(80, int(boxes["watermark"].y + boxes["watermark"].h + 16))
    right = width - 80
    bottom = min(boxes["caption"].y, boxes["lower_third"].y) - 16
    return Rect(left, top, max(40, right - left), max(40, bottom - top))


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def measure(text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    dummy = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    box = dummy.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def fit_text(text: str, font_path: Path, max_width: int, start: int, minimum: int) -> dict:
    """Shrink once, then ellipsise. ``fallback`` is set when the line still will not fit."""
    size = start
    font = _font(font_path, size)
    width, height = measure(text, font)
    shrunk = False
    if width > max_width and start > minimum:
        size = minimum
        font = _font(font_path, size)
        width, height = measure(text, font)
        shrunk = True
    shown = text
    truncated = False
    if width > max_width:
        truncated = True
        ellipsis = "…"
        while shown and measure(shown + ellipsis, font)[0] > max_width:
            shown = shown[:-1]
        shown = (shown.rstrip() + ellipsis) if shown else ellipsis
        width, height = measure(shown, font)
    return {
        "text": shown,
        "font": font,
        "size": size,
        "width": width,
        "height": height,
        "shrunk": shrunk,
        "truncated": truncated,
        "fallback": "kinetic" if truncated else None,
    }


def centered_box(width: int, height: int, safe: Rect) -> Rect:
    x = safe.x + max(0, (safe.w - width) / 2)
    y = safe.y + max(0, (safe.h - height) / 2)
    return Rect(x, y, width, height)


def inside(inner: Rect, outer: Rect) -> bool:
    return (
        inner.x >= outer.x - 0.5
        and inner.y >= outer.y - 0.5
        and inner.x + inner.w <= outer.x + outer.w + 0.5
        and inner.y + inner.h <= outer.y + outer.h + 0.5
    )
