"""Deterministic visual picker. Same phrase and previous choice, same id."""

from __future__ import annotations

import re

CATALOG = frozenset(
    {"kinetic", "section", "stat", "list", "comparison", "code", "question", "quote"}
)

_STAT = re.compile(r"\d|%|[$€£₫]|USD|VND", re.IGNORECASE)
_CODE = re.compile(r"`[^`]+`|(?:^|\s)(?:\$ |sudo |npm |ffmpeg |python )")
_COMPARISON = re.compile(r"\bvs\b|versus|so với|\bhơn\b", re.IGNORECASE)
_BULLET = re.compile(r"(?:^|\n)\s*(?:\d+[\).\]]|[-•])\s+\S")


class UnknownVisual(ValueError):
    pass


def select_visual(
    text: str,
    *,
    beat: str | None = None,
    first_in_beat: bool = False,
    explicit: str | None = None,
    previous: str | None = None,
) -> str:
    if explicit:
        if explicit not in CATALOG and explicit != "custom":
            raise UnknownVisual(f"unknown visual '{explicit}'")
        return explicit
    chosen = _match(text or "", beat, first_in_beat)
    # kinetic does not replace a template already on screen. A stat may.
    if previous and previous in CATALOG and chosen == "kinetic" and previous != "kinetic":
        return previous
    return chosen


def _match(text: str, beat: str | None, first_in_beat: bool) -> str:
    listed = len(_BULLET.findall(text)) >= 3 or _line_list(text)
    if not listed and _STAT.search(text):
        return "stat"
    if listed:
        return "list"
    if _CODE.search(text):
        return "code"
    if _COMPARISON.search(text):
        return "comparison"
    if first_in_beat or (beat or "").upper() in {"HOOK", "INTRO"}:
        return "section"
    if text.strip().endswith("?") and len(text.split()) <= 14:
        return "question"
    return "kinetic"


def _line_list(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return len(lines) >= 3


def params_for(template: str, text: str, beat: str | None = None) -> dict:
    if template == "stat":
        match = re.search(r"[$€£₫]?\d[\d.,]*%?", text)
        value = match.group(0) if match else text.split()[0]
        label = text.replace(value, "", 1).strip(" .")
        return {"value": value, "label": label or beat or ""}
    if template == "list":
        items = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
        return {"items": items or [text]}
    if template == "comparison":
        parts = re.split(r"\bvs\b|versus|so với|\bhơn\b", text, maxsplit=1, flags=re.IGNORECASE)
        left = parts[0].strip()
        right = parts[1].strip() if len(parts) > 1 else ""
        return {"left": left, "right": right}
    if template == "section":
        return {"label": beat or text}
    if template == "quote":
        return {"text": text.strip().strip('"')}
    return {"text": text}


def clamp_duration(template: str, requested: float) -> float:
    floor = 3.0 if template in {"stat", "list"} else 1.0
    return max(float(requested), floor)


def assign_phrases(phrases: list[dict], overlays: list[dict] | None = None) -> dict:
    """Pick a template per phrase. Custom overlays are copied through."""
    kept = [ov for ov in (overlays or []) if ov.get("template") == "custom"]
    visuals = []
    events = []
    previous = None
    beat_seen: set[str] = set()
    for phrase in phrases:
        explicit = phrase.get("visual")
        beat = phrase.get("beat")
        first = bool(beat) and beat not in beat_seen
        if beat:
            beat_seen.add(beat)
        if explicit == "custom":
            previous = "custom"
            continue
        choice = select_visual(
            phrase.get("text") or "",
            beat=beat,
            first_in_beat=first,
            explicit=explicit,
            previous=None if previous == "custom" else previous,
        )
        words = phrase.get("words") or []
        payoff = float(words[-1]["start"]) if words else float(phrase.get("start") or 0.0)
        reveal = 0.45
        start = max(0.0, payoff - reveal)
        end = float(phrase.get("end") or payoff + 1.0)
        duration = clamp_duration(choice, max(1.0, end - start))
        visuals.append(
            {
                "template": choice,
                "start": round(start, 3),
                "duration": round(duration, 3),
                "params": params_for(choice, phrase.get("text") or "", beat),
                "sfx": "reveal",
                "id": phrase.get("id") or choice,
            }
        )
        events.append({"kind": "reveal", "at": round(payoff, 3), "id": phrase.get("id") or choice})
        previous = choice
    return {"visuals": visuals, "events": events, "overlays": kept}
