"""Portrait unless the prompt asks for landscape."""

from __future__ import annotations

LANDSCAPE_PHRASES = (
    "16:9",
    "16x9",
    "1920x1080",
    "landscape",
    "horizontal",
    "youtube widescreen",
)
SHORTS_PHRASES = ("shorts", "tiktok", "reels")


def resolve_orientation(prompt: str) -> dict:
    text = (prompt or "").lower()
    if any(phrase in text for phrase in LANDSCAPE_PHRASES):
        orientation, chrome = "landscape", "clean"
    elif any(phrase in text for phrase in SHORTS_PHRASES):
        orientation, chrome = "portrait", "shorts"
    else:
        orientation, chrome = "portrait", "clean"
    return {"style": "explainer", "orientation": orientation, "chrome": chrome}
