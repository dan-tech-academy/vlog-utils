"""Caption styles.

``bold-overlay`` is the historical 2–3 word uppercase chunker.
``sentence`` is the long-form style and the default for Vietnamese:
12–18 syllables, or 4–7 English words, breaking on punctuation and pauses.
ASS burns do not take ``force_style`` (it would override the embedded styles).
PlayRes is the frame size so ``margin_v`` is pixels.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

PUNCT_BREAK = set(".,!?;:")
PAUSE_S = 0.3

_STYLE_SPEC = {
    # id: (font role, size, bold, alignment, margin extra, border style, outline)
    "bold-overlay": ("display", 64, True, 2, 0, 1, 3),
    "sentence": ("body", 72, False, 2, 36, 1, 2),
    "karaoke": ("body", 68, False, 2, 20, 1, 2),
    "terminal": ("mono", 54, False, 2, 48, 3, 0),
    "emphasis": ("display", 78, True, 2, 24, 1, 3),
}


def apply_case(text: str, style_id: str) -> str:
    """Uppercase is a style flag. Python's ``str.upper`` covers ``đ`` → ``Đ``."""
    if style_id == "bold-overlay":
        return text.upper()
    return text


def kf_centiseconds(seconds: float) -> int:
    """ASS ``\\kf`` duration. One centisecond is 0.01 s."""
    return max(0, int(round(float(seconds) * 100)))


def chunk_for_style(words: list[dict], style_id: str, language: str = "en") -> list[list[dict]]:
    if style_id not in _STYLE_SPEC:
        raise ValueError(f"unknown caption style '{style_id}'")
    if style_id == "bold-overlay":
        from render import chunk_words

        return chunk_words(words)
    if style_id == "emphasis":
        return _chunk_emphasis(words)
    if style_id in ("karaoke", "terminal"):
        return _chunk_budget(words, 10_000, 10_000)
    lo, hi = (12, 18) if language in ("vi", "vi-VN") else (4, 7)
    return _chunk_budget(words, lo, hi)


def _spoken(words: list[dict]) -> list[dict]:
    return [w for w in words if (w.get("text") or "").strip()]


def _chunk_budget(words: list[dict], lo: int, hi: int) -> list[list[dict]]:
    """Close on punctuation, a pause, or the syllable/word budget.

    ``lo`` is the preferred minimum. A cue may close earlier on punctuation
    or a pause. It closes once it reaches ``hi`` even mid-sentence.
    """
    words = _spoken(words)
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for i, word in enumerate(words):
        current.append(word)
        text = word["text"].strip()
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - word["end"]) if nxt else 0.0
        count = len(current)
        hit_budget = count >= hi or (count >= lo and nxt is not None and count + 1 > hi)
        if (
            nxt is None
            or (text and text[-1] in PUNCT_BREAK)
            or gap >= PAUSE_S
            or hit_budget
        ):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def _chunk_emphasis(words: list[dict]) -> list[list[dict]]:
    words = _spoken(words)
    if not words:
        return []
    payoff = max(range(len(words)), key=lambda i: len(_bare(words[i]["text"])))
    start = max(0, payoff - 1)
    end = min(len(words), payoff + 2)
    return [words[start:end]]


def _bare(text: str) -> str:
    return text.strip().strip("".join(PUNCT_BREAK))


def cues_from_words(words: list[dict], style_id: str, language: str = "en") -> list[dict]:
    cues = []
    for chunk in chunk_for_style(words, style_id, language):
        raw = " ".join((w.get("text") or "").strip() for w in chunk)
        raw = re.sub(r"\s+", " ", raw).strip()
        if style_id == "bold-overlay":
            raw = raw.rstrip(",;:")
        cues.append(
            {
                "start": float(chunk[0]["start"]),
                "end": float(chunk[-1]["end"]),
                "text": apply_case(raw, style_id),
                "words": chunk,
                "style": style_id,
            }
        )
    return cues


def cues_for_edl(edl: dict, edit_dir: Path, style_id: str, language: str = "en") -> list[dict]:
    """Output-timeline cues. Same offset rule as ``build_master_srt``."""
    from render import _words_in_range

    transcripts = Path(edit_dir) / "transcripts"
    cues: list[dict] = []
    offset = 0.0
    for segment in edl["ranges"]:
        src = segment["source"]
        seg_start = float(segment["start"])
        seg_end = float(segment["end"])
        duration = seg_end - seg_start
        path = transcripts / f"{src}.json"
        if not path.exists():
            offset += duration
            continue
        transcript = json.loads(path.read_text())
        local = _words_in_range(transcript, seg_start, seg_end)
        shifted = []
        for word in local:
            start = max(0.0, float(word["start"]) - seg_start) + offset
            end = max(0.0, float(word["end"]) - seg_start) + offset
            shifted.append({**word, "start": start, "end": end})
        cues.extend(cues_from_words(shifted, style_id, language))
        offset += duration
    return cues


def hex_to_ass(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def ass_timestamp(seconds: float) -> str:
    cs_total = max(0, int(round(seconds * 100)))
    hours, rem = divmod(cs_total, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def style_line(style_id: str, theme) -> str:
    role, size, bold, alignment, margin_extra, border, outline = _STYLE_SPEC[style_id]
    face = theme.font(role)
    override = getattr(theme, "caption_font_size", None)
    if override and style_id == "sentence":
        size = int(override)
        margin_extra = 0
    margin_v = int(theme.margin_v) + margin_extra
    primary = theme.text
    secondary = theme.text_muted
    outline_color = "#000000"
    back = "&H00000000"
    if style_id == "bold-overlay":
        primary = "#FFFFFF"
        outline_color = "#000000"
    elif style_id == "karaoke":
        primary = theme.accent
        secondary = theme.text_muted
    elif style_id == "terminal":
        primary = theme.accent
        back = hex_to_ass(theme.surface, alpha=0)
        outline_color = theme.surface
    elif style_id == "sentence":
        outline_color = theme.text_muted
    bold_flag = -1 if bold else 0
    return ",".join(
        [
            style_id,
            face.family,
            str(size),
            hex_to_ass(primary),
            hex_to_ass(secondary),
            hex_to_ass(outline_color),
            back if style_id == "terminal" else "&H00000000",
            str(bold_flag),
            "0",
            "0",
            "0",
            "100",
            "100",
            "0",
            "0",
            str(border),
            str(outline),
            "0",
            str(alignment),
            "80",
            "80",
            str(margin_v),
            "1",
        ]
    )


def cue_body(cue: dict, style_id: str, theme) -> str:
    words = cue["words"]
    if style_id == "karaoke":
        parts = []
        for index, word in enumerate(words):
            dur = max(0.0, float(word["end"]) - float(word["start"]))
            space = " " if index else ""
            token = (word.get("text") or "").strip()
            parts.append(f"{space}{{\\kf{kf_centiseconds(dur)}}}{token}")
        return "".join(parts)
    if style_id == "emphasis" and words:
        payoff = max(words, key=lambda w: len(_bare(w.get("text") or "")))
        accent = hex_to_ass(theme.accent)
        white = hex_to_ass("#FFFFFF")
        parts = []
        for word in words:
            token = (word.get("text") or "").strip()
            if word is payoff:
                parts.append(f"{{\\c{accent}&}}{token}{{\\c{white}&}}")
            else:
                parts.append(token)
        return " ".join(parts)
    if style_id == "terminal":
        return "› " + cue["text"]
    return cue["text"]


def write_ass(cues: list[dict], out_path: Path, theme, style_id: str) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {int(theme.frame_width)}",
            f"PlayResY: {int(theme.frame_height)}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: {style_line(style_id, theme)}",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
    lines = [header]
    for cue in cues:
        body = cue_body(cue, style_id, theme).replace("\n", " ")
        lines.append(
            "Dialogue: 0,"
            f"{ass_timestamp(cue['start'])},"
            f"{ass_timestamp(cue['end'])},"
            f"{style_id},,0,0,0,,{body}"
        )
    out_path.write_text("\n".join(lines) + "\n")


def escape_filter_path(path: Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def subtitle_filter(path: Path, *, fontsdir: Path | None = None, force_style: str | None = None) -> str:
    """ffmpeg ``subtitles`` filter fragment, without the trailing label.

    ASS files get ``fontsdir`` and never ``force_style``. SRT files get
    ``force_style`` and no ``fontsdir``.
    """
    escaped = escape_filter_path(path)
    if Path(path).suffix.lower() == ".ass":
        extra = ""
        if fontsdir is not None:
            extra = f":fontsdir='{escape_filter_path(fontsdir)}'"
        return f"subtitles='{escaped}'{extra}"
    if not force_style:
        raise ValueError(f"SRT captions need force_style ({path})")
    return f"subtitles='{escaped}':force_style='{force_style}'"


def ffmpeg_has_libass() -> bool:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
    )
    return "subtitles" in proc.stdout


def require_libass() -> None:
    if not ffmpeg_has_libass():
        raise SystemExit(
            "ffmpeg has no subtitles filter (libass is missing). "
            "Install an ffmpeg build with libass before burning captions."
        )
