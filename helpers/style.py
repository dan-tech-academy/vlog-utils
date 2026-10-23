"""Validate the talking-head explainer preset.

The schema describes this one skill. Unknown keys fail. It is not a
vocabulary for other styles.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "skills" / "style.schema.json"
EXPLAINER_PATH = REPO_ROOT / "skills" / "style-explainer" / "style.json"


class StyleError(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"{field}: {message}")


def load_schema(path: Path | None = None) -> dict:
    return json.loads(Path(path or SCHEMA_PATH).read_text())


def load_style(path: Path | None = None) -> dict:
    path = Path(path or EXPLAINER_PATH)
    data = json.loads(path.read_text())
    errors = validate_style(data)
    if errors:
        raise errors[0]
    return data


def _reject_unknown(data: dict, allowed: set[str], field: str, errors: list[StyleError]) -> None:
    for key in data:
        if key not in allowed:
            errors.append(StyleError(key if field == "" else f"{field}.{key}", "unknown key"))


def validate_style(data: dict, schema: dict | None = None) -> list[StyleError]:
    schema = schema or load_schema()
    errors: list[StyleError] = []
    if not isinstance(data, dict):
        return [StyleError("style", "must be an object")]
    props = schema.get("properties") or {}
    _reject_unknown(data, set(props), "", errors)
    for key in schema.get("required") or []:
        if key not in data:
            errors.append(StyleError(key, "missing"))
    frames = data.get("frames")
    if isinstance(frames, dict):
        for name in ("landscape", "portrait"):
            frame = frames.get(name)
            if not isinstance(frame, dict):
                errors.append(StyleError(f"frames.{name}", "missing"))
                continue
            for part in ("width", "height", "margin_v", "font_size"):
                if part not in frame:
                    errors.append(StyleError(f"frames.{name}.{part}", "missing"))
    if data.get("energy") not in (None, "measured"):
        errors.append(StyleError("energy", "explainer energy is measured"))
    self_eval = data.get("self_eval") or {}
    if isinstance(self_eval, dict) and "max_passes" in self_eval:
        try:
            cap = int(self_eval["max_passes"])
        except (TypeError, ValueError):
            cap = 0
        if cap < 1:
            errors.append(StyleError("self_eval.max_passes", "must be a positive integer"))
    music = data.get("music") or {}
    if isinstance(music, dict) and music.get("policy") not in (None, "library"):
        errors.append(StyleError("music.policy", "explainer policy is library"))
    return errors
