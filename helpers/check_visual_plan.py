"""Check a visual plan against explainer guardrails and safe zones.

The checker does not pick a template. A number rendered as a comparison
is allowed. A comparison card on a line with no datum is not.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from explainer_layout import card_rect, delivery, place_card
from style import StyleError, load_style

DATUM = re.compile(
    r"\d|%|\$|€|£|₫|\bvs\b|versus|so với|hơn",
    re.IGNORECASE,
)
NUMERAL = re.compile(r"\d+(?:[.,]\d+)?%?")


class PlanError(StyleError):
    pass


def signature(treatment: dict) -> tuple:
    layout = (treatment or {}).get("layout") or "clean"
    if layout == "clean":
        return ("clean",)
    data = treatment.get("data") or {}
    data_type = data.get("type") if isinstance(data, dict) else None
    return (layout, treatment.get("motion") or "hold", data_type)


def _labels(treatment: dict) -> list[str]:
    labels = []
    text = treatment.get("text")
    if isinstance(text, str) and text.strip():
        labels.append(text.strip())
    data = treatment.get("data")
    if isinstance(data, dict):
        for key in ("before", "after", "label", "title"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                labels.append(value.strip())
        for item in data.get("items") or []:
            if isinstance(item, str) and item.strip():
                labels.append(item.strip())
    return labels


def _grounded(label: str, quote: str, why: str) -> bool:
    if label in quote:
        return True
    if label not in (why or ""):
        return False
    for numeral in NUMERAL.findall(label):
        bare = numeral[:-1] if numeral.endswith("%") else numeral
        if numeral not in quote and bare not in quote:
            return False
    return True


def _edge_inside_word(edge: float, words: list[dict], eps: float = 1e-3) -> bool:
    for word in words:
        start = float(word["start"])
        end = float(word["end"])
        if start + eps < edge < end - eps:
            return True
    return False


def _graphics(segments: list[dict]) -> list[dict]:
    graphic_layouts = {"side-card", "lower-card", "split", "bespoke"}
    out = []
    for segment in segments:
        treatment = segment.get("treatment") or {}
        layout = treatment.get("layout") or "clean"
        if layout in graphic_layouts or treatment.get("data") or (
            treatment.get("overlay") in ("alpha-card", "broll", "photo") and layout != "clean"
        ):
            if layout != "clean":
                out.append(segment)
    return out


def check_visual_plan(
    plan: dict,
    style: dict,
    run: dict,
    inventory: dict,
    *,
    words_by_source: dict | None = None,
    edl: dict | None = None,
    manifest: dict | None = None,
    face_box: dict | None = None,
    face_center_x: float | None = None,
) -> list[PlanError]:
    errors: list[PlanError] = []
    orientation = (run or {}).get("orientation") or "portrait"
    chrome = (run or {}).get("chrome") or "clean"
    if orientation not in ("portrait", "landscape"):
        errors.append(PlanError("orientation", "must be portrait or landscape"))
        return errors
    box = delivery(style, orientation, chrome)
    segments = list((plan or {}).get("segments") or [])
    guard = style.get("guardrails") or {}
    allowed_sfx = set((style.get("sfx") or {}).get("kinds") or [])
    primitives = style.get("primitives") or {}

    previous = None
    for segment in segments:
        sid = segment.get("id") or "?"
        for key in ("intent", "why", "treatment"):
            if not segment.get(key):
                errors.append(PlanError(f"segments.{sid}.{key}", "missing"))
        treatment = segment.get("treatment") or {}
        layout = treatment.get("layout") or "clean"
        if layout not in set(primitives.get("layout") or []):
            errors.append(PlanError(f"segments.{sid}.treatment.layout", f"unknown layout {layout}"))
        motion = treatment.get("motion")
        if motion and motion not in set(primitives.get("motion") or []):
            errors.append(PlanError(f"segments.{sid}.treatment.motion", f"unknown motion {motion}"))
        transition = treatment.get("transition")
        if transition and transition not in set(primitives.get("transition") or ["cut"]):
            errors.append(PlanError(f"segments.{sid}.treatment.transition", "only cut is allowed on the face"))
        sfx = treatment.get("sfx")
        if sfx:
            if sfx == "cut" or (style.get("sfx") or {}).get("cuts") is False and sfx == "cut":
                errors.append(PlanError(f"segments.{sid}.treatment.sfx", "jump cuts stay dry"))
            elif sfx not in allowed_sfx:
                errors.append(PlanError(f"segments.{sid}.treatment.sfx", f"{sfx} is not an explainer kind"))
        quote = segment.get("quote") or ""
        why = segment.get("why") or ""
        if treatment.get("data") and not DATUM.search(quote):
            errors.append(PlanError(f"segments.{sid}.treatment.data", "quote has no datum"))
        for label in _labels(treatment):
            if not _grounded(label, quote, why):
                errors.append(PlanError(f"segments.{sid}.treatment.text", f"{label!r} is not in the quote"))
        if previous is not None and guard.get("no_same_treatment_back_to_back", True):
            if signature(previous.get("treatment") or {}) == signature(treatment):
                errors.append(PlanError(f"segments.{sid}.treatment", "same treatment as the previous segment"))
        if layout not in ("clean", "lower-third") and "start" in segment and "end" in segment:
            duration = float(segment["end"]) - float(segment["start"])
            if duration + 1e-6 < float(guard.get("min_graphic_s") or 0):
                errors.append(PlanError(f"segments.{sid}.end", "graphic is shorter than min_graphic_s"))
        if orientation == "portrait" and layout == "side-card":
            errors.append(PlanError(f"segments.{sid}.treatment.layout", "portrait uses lower-card"))
        if orientation == "landscape" and layout == "lower-card":
            errors.append(PlanError(f"segments.{sid}.treatment.layout", "landscape uses side-card"))
        placed, face_error = place_card(
            box, layout, face_center_x=face_center_x, face_box=face_box,
        )
        if face_error:
            errors.append(PlanError(f"segments.{sid}.{face_error}", "card covers the face"))
        elif placed is not None:
            # place_card already kept the card inside the safe rect.
            # A zero-size rect is still a broken layout.
            if placed.w < 40 or placed.h < 40:
                errors.append(PlanError(f"segments.{sid}.treatment.layout", "card rect collapsed"))
        previous = segment

    graphics = [s for s in _graphics(segments) if "start" in s and "end" in s]
    graphics.sort(key=lambda s: float(s["start"]))
    min_clean = float(guard.get("min_clean_s") or 0)
    for earlier, later in zip(graphics, graphics[1:]):
        gap = float(later["start"]) - float(earlier["end"])
        if gap + 1e-6 < min_clean:
            errors.append(PlanError(f"segments.{later.get('id')}.start", "clean-face gap is too short"))
    window = 10.0
    cap = int(guard.get("max_graphics_per_10s") or 99)
    for segment in graphics:
        start = float(segment["start"])
        count = sum(1 for other in graphics if start <= float(other["start"]) < start + window)
        if count > cap:
            errors.append(PlanError(f"segments.{segment.get('id')}.start", "too many graphics in 10s"))
            break

    _check_music(plan, inventory, manifest, errors)
    _check_frame(edl, box, errors)
    _check_words(edl, words_by_source or {}, errors)
    return errors


def _check_music(plan, inventory, manifest, errors: list[PlanError]) -> None:
    roles = {entry.get("role") for entry in (inventory or {}).get("files") or []}
    music = (plan or {}).get("music") or {}
    folder_has_music = "music" in roles
    if folder_has_music and music.get("source") == "library":
        errors.append(PlanError("music.source", "folder music wins over the library"))
        return
    if folder_has_music and music.get("source") not in ("folder",):
        errors.append(PlanError("music.source", "folder music must be the bed"))
        return
    if not folder_has_music:
        if music.get("source") not in (None, "library") and music:
            errors.append(PlanError("music.source", "no folder bed; use the library"))
        if not music:
            return
        if music.get("source") != "library":
            errors.append(PlanError("music.source", "expected library"))
            return
        bed_id = music.get("id")
        beds = {bed.get("id"): bed for bed in (manifest or {}).get("beds") or []}
        bed = beds.get(bed_id)
        if bed is None:
            errors.append(PlanError("music.id", f"{bed_id} is not in the manifest"))
            return
        if bed.get("vocals") is True:
            errors.append(PlanError("music.id", "vocals must be false"))
        if not bed.get("license"):
            errors.append(PlanError("music.license", "license is empty"))


def _check_frame(edl, box, errors: list[PlanError]) -> None:
    if not edl:
        return
    frame = edl.get("frame") or {}
    if not frame:
        errors.append(PlanError("frame", "edl is missing the delivery frame"))
        return
    if int(frame.get("width") or 0) != box["width"] or int(frame.get("height") or 0) != box["height"]:
        errors.append(PlanError(
            "frame",
            f"got {frame.get('width')}x{frame.get('height')}, run wants {box['width']}x{box['height']}",
        ))


def _check_words(edl, words_by_source, errors: list[PlanError]) -> None:
    if not edl:
        return
    for index, segment in enumerate(edl.get("ranges") or []):
        words = words_by_source.get(segment.get("source")) or []
        for edge_name in ("start", "end"):
            edge = float(segment[edge_name])
            if _edge_inside_word(edge, words):
                errors.append(PlanError(f"ranges[{index}].{edge_name}", "cut falls inside a word"))


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check an explainer visual plan")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--style", type=Path)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--edl", type=Path)
    parser.add_argument("--words", type=Path, help="JSON object of source id -> word list")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--face-box", type=Path, help="JSON {x,y,w,h} in the delivery frame")
    args = parser.parse_args(argv)
    style = load_style(args.style) if args.style else load_style()
    manifest = load_json(args.manifest) if args.manifest else {"beds": []}
    face_box = load_json(args.face_box) if args.face_box else None
    words = load_json(args.words) if args.words else {}
    errors = check_visual_plan(
        load_json(args.plan),
        style,
        load_json(args.run),
        load_json(args.inventory),
        words_by_source=words,
        edl=load_json(args.edl) if args.edl else None,
        manifest=manifest,
        face_box=face_box,
    )
    if errors:
        for error in errors:
            print(f"{error.field}: {error}", file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
