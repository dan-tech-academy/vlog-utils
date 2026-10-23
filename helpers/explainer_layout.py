"""Safe zones for the talking-head explainer.

A card rect is the legal region when a segment asks for one. A clean
segment has no card. These boxes are not an instruction to draw a card.
"""

from __future__ import annotations

from brand import Rect, layout_boxes


def delivery(style: dict, orientation: str, chrome: str) -> dict:
    frame = style["frames"][orientation]
    margin_v = int(frame["margin_v"])
    if orientation == "portrait" and chrome == "shorts":
        margin_v += int(style["chrome"]["shorts"]["bottom_extra"])
    side = 80 if orientation == "landscape" else int(style["chrome"][chrome]["side"])
    right_extra = 0
    if orientation == "portrait":
        right_extra = int(style["chrome"][chrome]["right_extra"])
    top = 116 if orientation == "landscape" else int(style["chrome"][chrome]["top"])
    return {
        "width": int(frame["width"]),
        "height": int(frame["height"]),
        "margin_v": margin_v,
        "font_size": int(frame["font_size"]),
        "side": side,
        "right_extra": right_extra,
        "top": top,
        "orientation": orientation,
        "chrome": chrome,
    }


def caption_band(box: dict) -> Rect:
    height = 72
    top = box["height"] - box["margin_v"] - height
    return Rect(0, top, box["width"], height)


def lower_third_rect(box: dict) -> Rect:
    if box["orientation"] == "portrait":
        width = min(640, box["width"] - box["side"] * 2 - box["right_extra"])
        return Rect(box["side"], box["top"], width, 110)
    boxes = layout_boxes(box["width"], box["height"], box["margin_v"])
    return boxes["lower_third"]


def _safe(box: dict) -> Rect:
    caption = caption_band(box)
    lower = lower_third_rect(box)
    left = box["side"]
    right = box["width"] - box["side"] - box["right_extra"]
    if box["orientation"] == "portrait":
        top = box["top"] + lower.h + 16
        bottom = caption.y - 16
    else:
        top = max(box["top"], 116)
        bottom = min(caption.y, lower.y) - 16
    return Rect(left, top, max(40, right - left), max(40, bottom - top))


def card_rect(
    box: dict,
    layout: str,
    *,
    face_center_x: float | None = None,
    max_width: int | None = None,
) -> Rect | None:
    """Return the card rect, or None when this layout draws no card."""
    if layout in (None, "clean", "lower-third"):
        return None
    safe = _safe(box)
    if layout == "lower-card" or (layout == "side-card" and box["orientation"] == "portrait"):
        card_h = min(int(box["height"] * 0.38), int(safe.h))
        return Rect(safe.x, safe.y + safe.h - card_h, safe.w, card_h)
    if layout in ("side-card", "split", "bespoke"):
        card_w = 640 if max_width is None else max_width
        card_h = 520
        card_w = min(card_w, int(safe.w))
        card_h = min(card_h, int(safe.h))
        face_on_right = face_center_x is not None and face_center_x >= box["width"] / 2
        if face_on_right:
            x = safe.x
        else:
            x = safe.x + safe.w - card_w
        y = safe.y + max(0, (safe.h - card_h) / 2)
        return Rect(x, y, card_w, card_h)
    return None


def expand_rect(rect: Rect, pad: float) -> Rect:
    return Rect(rect.x - pad, rect.y - pad, rect.w + pad * 2, rect.h + pad * 2)


def place_card(
    box: dict,
    layout: str,
    *,
    face_center_x: float | None = None,
    face_box: dict | None = None,
) -> tuple[Rect | None, str | None]:
    """Place a card. The second value is an error field when the eyes would be covered."""
    rect = card_rect(box, layout, face_center_x=face_center_x)
    if rect is None or not face_box:
        return rect, None
    face = expand_rect(Rect(face_box["x"], face_box["y"], face_box["w"], face_box["h"]), 24)
    if not rect.intersects(face):
        return rect, None
    if box["orientation"] == "landscape" and layout == "side-card":
        shrunk = card_rect(box, layout, face_center_x=face_center_x, max_width=480)
        if shrunk is not None and not shrunk.intersects(face):
            return shrunk, None
    return rect, "treatment.layout"
