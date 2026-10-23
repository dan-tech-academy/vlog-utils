"""Channel theme loader.

Search order is whole-file, not a merge:

1. ``<edit>/theme.json`` when that file exists
2. ``brand/theme.json`` in this repo
3. ``brand/theme.example.json``

A missing font file raises ``ThemeError`` naming every path that was tried.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = REPO_ROOT / "brand"

KNOWN_CAPTION_STYLES = frozenset(
    {"bold-overlay", "sentence", "karaoke", "terminal", "emphasis"}
)

_HEX = re.compile(r"#[0-9A-Fa-f]{6}$")
_COLOR_KEYS = ("background", "surface", "text", "textMuted", "accent")
_FONT_ROLES = ("display", "body", "mono")


class ThemeError(Exception):
    """The theme file is missing a key, a color, or a font file."""


class FontFace:
    def __init__(self, role: str, family: str, file: Path, weight: int):
        self.role = role
        self.family = family
        self.file = file
        self.weight = weight

    def __repr__(self) -> str:
        return f"FontFace({self.role!r}, {self.family!r}, {self.file})"


class Theme:
    def __init__(self, path: Path, source: str, data: dict, fonts: dict[str, FontFace]):
        self.path = path
        self.source = source
        self.data = data
        self.fonts = fonts
        meta = data.get("meta") or {}
        self.placeholders = bool(meta.get("placeholders"))
        self.note = meta.get("note") or ""
        channel = data["channel"]
        self.channel_name = channel["name"]
        self.handles = tuple(channel["handles"])
        self.handle = channel["handle"]
        colors = data["colors"]
        self.background = colors["background"]
        self.surface = colors["surface"]
        self.text = colors["text"]
        self.text_muted = colors["textMuted"]
        self.accent = colors["accent"]
        self.accent_alt = colors.get("accentAlt")
        captions = data["captions"]
        self.captions_default = captions["default"]
        self.margin_v = int(captions["margin_v"])
        frame = data["frame"]
        self.frame_width = int(frame["width"])
        self.frame_height = int(frame["height"])
        self.fps = frame["fps"]
        self.frame_mode = frame["mode"]
        self.watermark = dict(data.get("watermark") or {})
        self.lower_third = dict(data.get("lower_third") or {})
        self.intro = dict(data.get("intro") or {})
        self.outro = dict(data.get("outro") or {})
        self.sfx = dict(data.get("sfx") or {})
        self.music = dict(data.get("music") or {})

    def font(self, role: str) -> FontFace:
        try:
            return self.fonts[role]
        except KeyError as exc:
            raise ThemeError(
                f"theme {self.path} has no font role '{role}'"
            ) from exc


def theme_candidates(edit_dir: Path | None) -> list[tuple[str, Path]]:
    """Paths that ``load_theme`` will consider, in order.

    An existing ``<edit>/theme.json`` replaces the repo file. The repo file
    is not merged in afterwards.
    """
    if edit_dir is not None:
        override = Path(edit_dir) / "theme.json"
        if override.is_file():
            return [("edit", override)]
    repo = BRAND_DIR / "theme.json"
    example = BRAND_DIR / "theme.example.json"
    found: list[tuple[str, Path]] = []
    if repo.is_file():
        found.append(("repo", repo))
    elif example.is_file():
        found.append(("example", example))
    return found


def load_theme(edit_dir: Path | None = None) -> Theme:
    candidates = theme_candidates(edit_dir)
    if not candidates:
        looked = "<edit>/theme.json, brand/theme.json, brand/theme.example.json"
        raise ThemeError(f"no theme file found (looked for {looked})")
    source, path = candidates[0]
    return load_theme_file(path, source=source)


def load_theme_file(path: Path, source: str = "file") -> Theme:
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ThemeError(f"theme {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ThemeError(f"theme {path} must be a JSON object")
    _require_mapping(data, "channel", path)
    _require_mapping(data, "colors", path)
    _require_mapping(data, "fonts", path)
    _require_mapping(data, "captions", path)
    _require_mapping(data, "frame", path)
    channel = data["channel"]
    for key in ("name", "handles", "handle"):
        if key not in channel:
            raise ThemeError(f"missing key 'channel.{key}' in {path}")
    colors = data["colors"]
    for key in _COLOR_KEYS:
        if key not in colors:
            raise ThemeError(f"missing key 'colors.{key}' in {path}")
        _check_hex(colors[key], f"colors.{key}", path)
    if "accentAlt" in colors and colors["accentAlt"] is not None:
        _check_hex(colors["accentAlt"], "colors.accentAlt", path)
    captions = data["captions"]
    for key in ("default", "margin_v"):
        if key not in captions:
            raise ThemeError(f"missing key 'captions.{key}' in {path}")
    style = captions["default"]
    if style not in KNOWN_CAPTION_STYLES:
        raise ThemeError(f"unknown caption style '{style}' in {path}")
    frame = data["frame"]
    for key in ("width", "height", "fps", "mode"):
        if key not in frame:
            raise ThemeError(f"missing key 'frame.{key}' in {path}")
    if frame["mode"] not in ("source", "force"):
        raise ThemeError(
            f"frame.mode in {path} must be 'source' or 'force', got {frame['mode']!r}"
        )
    fonts: dict[str, FontFace] = {}
    for role in _FONT_ROLES:
        if role not in data["fonts"]:
            raise ThemeError(f"missing key 'fonts.{role}' in {path}")
        fonts[role] = _load_face(role, data["fonts"][role], path)
    return Theme(path, source, data, fonts)


def _require_mapping(data: dict, key: str, path: Path) -> None:
    if key not in data or not isinstance(data[key], dict):
        raise ThemeError(f"missing key '{key}' in {path}")


def _check_hex(value: object, key: str, path: Path) -> None:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ThemeError(f"color '{key}' in {path} must be #RRGGBB, got {value!r}")


def _load_face(role: str, spec: object, theme_path: Path) -> FontFace:
    where = f"fonts.{role}"
    if not isinstance(spec, dict):
        raise ThemeError(f"missing key '{where}' in {theme_path}")
    for key in ("family", "file", "weight"):
        if key not in spec:
            raise ThemeError(f"missing key '{where}.{key}' in {theme_path}")
    file_str = spec["file"]
    if not isinstance(file_str, str) or not file_str:
        raise ThemeError(f"missing font file for '{where}' in {theme_path}")
    resolved = _resolve_font(file_str, theme_path)
    return FontFace(role, str(spec["family"]), resolved, int(spec["weight"]))


def _resolve_font(file_str: str, theme_path: Path) -> Path:
    raw = Path(file_str)
    if raw.is_absolute():
        candidates = [raw]
    else:
        candidates = [
            (theme_path.parent / raw),
            (REPO_ROOT / raw),
            (BRAND_DIR / raw),
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    tried = ", ".join(str(c) for c in candidates)
    raise ThemeError(f"missing font file '{file_str}' (tried {tried})")
