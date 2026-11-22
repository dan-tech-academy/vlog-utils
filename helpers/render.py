"""Render a video from an EDL (version 1 or 2).

Implements the HEURISTICS render pipeline in the correct order:

  1. Per-segment extract with color grade + 30ms audio fades baked in.
     Image sources become Ken Burns / pan segments on the shared canvas.
  2. Segment assembly into base.mp4: lossless `-c copy` concat when every
     cut is hard, otherwise an xfade + acrossfade chain for transitions.
  3. If overlays or subtitles: single filter graph that overlays animations
     (with PTS shift so frame 0 lands at the overlay window start)
     and applies `subtitles` filter LAST → final.mp4
  4. Optional `audio` block: music bed + SFX hits mixed under the voice.
  5. Loudness normalization to -14 LUFS / -1 dBTP.

Optionally builds a master SRT from the per-source transcripts + EDL
output-timeline offsets, applies the proven force_style (2-word
UPPERCASE chunks, Helvetica 18 Bold, MarginV=35).

Usage:
    python helpers/render.py <edl.json> -o final.mp4
    python helpers/render.py <edl.json> -o preview.mp4 --preview
    python helpers/render.py <edl.json> -o final.mp4 --build-subtitles
    python helpers/render.py <edl.json> -o final.mp4 --no-subtitles
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

try:
    from grade import get_preset, auto_grade_for_clip  # same directory
except Exception:
    def get_preset(name: str) -> str:
        return ""

    def auto_grade_for_clip(video, start=0.0, duration=None, verbose=False):  # type: ignore
        return "eq=contrast=1.03:saturation=0.98", {}


# -------- Subtitle style (bold-overlay, proven at 1920×1080 and 1080×1920) --
#
# MarginV is NOT taste — it is a platform safe-zone rule.
# TikTok / IG Reels / Shorts UI (caption, username, music, right-rail actions)
# covers roughly the bottom ~25–30% of a 1080×1920 frame. Captions placed near
# the bottom edge get clipped or obscured by the UI. libass auto-scales the
# render canvas relative to PlayResY=288, so MarginV=90 lands the caption
# baseline roughly 30% up from the bottom on any aspect — clear of the UI on
# every major vertical-video platform. Do not drop this below ~75 without a
# specific reason.
SUB_FORCE_STYLE = (
    "FontName=Helvetica,FontSize=18,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H00000000,"
    "BorderStyle=1,Outline=2,Shadow=0,"
    "Alignment=2,MarginV=90"
)

# -------- Helpers ------------------------------------------------------------


def run(cmd: list[str], quiet: bool = False) -> None:
    if not quiet:
        print(f"  $ {' '.join(str(c) for c in cmd[:6])}{' …' if len(cmd) > 6 else ''}")
    subprocess.run(cmd, check=True)


def resolve_grade_filter(grade_field: str | None) -> str:
    """The EDL's 'grade' field can be a preset name, a raw ffmpeg filter, or 'auto'.

    Returns the filter string to embed into the per-segment -vf chain.
    For 'auto', returns the sentinel "__AUTO__" which is resolved per-segment.
    """
    if not grade_field:
        return ""
    if grade_field == "auto":
        return "__AUTO__"
    # Preset names are short identifiers, filter strings contain '=' or ','.
    if re.fullmatch(r"[a-zA-Z0-9_\-]+", grade_field):
        try:
            return get_preset(grade_field)
        except KeyError:
            print(f"warning: unknown preset '{grade_field}', using as raw filter")
            return grade_field
    return grade_field


def resolve_path(maybe_path: str, base: Path) -> Path:
    """Resolve a path that may be absolute or relative to `base`."""
    p = Path(maybe_path)
    if p.is_absolute():
        return p
    return (base / p).resolve()


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}


def source_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTS:
        return "image"
    if suffix in AUDIO_EXTS:
        return "audio"
    return "video"


def probe_image_size(path: Path) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "json", str(path)],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(out.stdout).get("streams") or []
        if streams:
            return int(streams[0]["width"]), int(streams[0]["height"])
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
        pass
    return None


# -------- Effects ------------------------------------------------------------
#
# EDL v2 per-range `effect` field. Whitelisted so agents cannot emit arbitrary
# filter chains; every effect lands on the shared canvas at the same size.

EFFECTS = {"static", "zoom_in", "zoom_out", "pan_left", "pan_right", "punch_in"}

TRANSITIONS = {
    "fade", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown",
    "circleopen", "circleclose", "fadeblack", "fadewhite",
}

# Depth of the zoom, shared by both implementations so cards and final agree.
ZOOM_DEPTH = 1.35


def video_effect_filter(effect: str | None, duration: float, w: int, h: int,
                        fps: float = 25.0) -> str:
    """Animated zoom/pan for video via zoompan: crop sizes are evaluated once at
    init, so crop cannot animate — zoompan re-evaluates per output frame.
    The caller must pre-scale the input to ≥ ZOOM_DEPTH× the output canvas."""
    if not effect or effect == "static":
        return ""
    frames = max(1, int(round(duration * fps)))
    k = ZOOM_DEPTH - 1.0
    n = max(1, frames - 1)  # on goes 0..frames-1
    if effect == "zoom_in":
        z = f"min(1+{k:.2f}*on/{n},{ZOOM_DEPTH})"
    elif effect == "zoom_out":
        z = f"max({ZOOM_DEPTH}-{k:.2f}*on/{n},1)"
    elif effect == "punch_in":
        z = f"min(1+{2 * k:.2f}*on/{n},{ZOOM_DEPTH})"
    elif effect in ("pan_left", "pan_right"):
        z = f"{ZOOM_DEPTH}"
    else:
        return ""
    if effect == "pan_left":
        x = f"(iw-ow)*min(on/{n},1)"
    elif effect == "pan_right":
        x = f"(iw-ow)*(1-min(on/{n},1))"
    else:
        x = "(iw-ow)/2"
    return (
        f"zoompan=z='{z}':x='{x}':y='(ih-oh)/2'"
        f":d=1:s={w}x{h}:fps={fps:g}"
    )


def image_effect_filter(effect: str | None, w: int, h: int, frames: int = 1, fps: float = 25.0) -> str:
    """zoompan expression for a still: input is pre-scaled to 2× the canvas.

    `d`/`fps` are not usable inside zoompan expressions, so the frame count and
    rate are baked into each expression as constants. `static` still routes
    through zoompan (z=1) so a lone input frame expands to `frames` outputs.
    """
    d = max(frames, 1)
    cx = "'iw/2-(iw/zoom/2)'"
    cy = "'ih/2-(ih/zoom/2)'"
    if not effect or effect == "static":
        return f"zoompan=z='1':x={cx}:y={cy}:s={w}x{h}"
    if effect == "zoom_in":
        return f"zoompan=z='min(1+{ZOOM_DEPTH - 1:.2f}*on/{d},{ZOOM_DEPTH})':x={cx}:y={cy}:s={w}x{h}"
    if effect == "zoom_out":
        return f"zoompan=z='max({ZOOM_DEPTH}-{ZOOM_DEPTH - 1:.2f}*on/{d},1)':x={cx}:y={cy}:s={w}x{h}"
    if effect == "punch_in":
        return f"zoompan=z='min(1+2.0*on/{fps:g},{ZOOM_DEPTH})':x={cx}:y={cy}:s={w}x{h}"
    if effect == "pan_left":
        return f"zoompan=z={ZOOM_DEPTH}:x='(iw-iw/zoom)*on/{d}':y={cy}:s={w}x{h}"
    if effect == "pan_right":
        return f"zoompan=z={ZOOM_DEPTH}:x='(iw-iw/zoom)*(1-on/{d})':y={cy}:s={w}x{h}"
    return ""


def target_canvas(edl: dict, edit_dir: Path) -> tuple[int, int]:
    """One canvas for the whole render so xfade can blend adjacent segments.

    Orientation comes from the first range's source: portrait → 1080×1920,
    anything else → 1920×1080.
    """
    ranges = edl.get("ranges") or []
    sources = edl.get("sources") or {}
    portrait = False
    if ranges:
        raw = ranges[0].get("source")
        if raw and sources.get(raw):
            src = resolve_path(str(sources[raw]), edit_dir)
            if source_kind(src) == "image":
                size = probe_image_size(src)
                portrait = bool(size and size[1] > size[0])
            else:
                portrait = is_portrait_source(src)
    return (1080, 1920) if portrait else (1920, 1080)


def transition_in(range_row: dict) -> dict | None:
    raw = range_row.get("transition_in")
    if not isinstance(raw, dict):
        return None
    ttype = str(raw.get("type") or "").lower()
    if ttype in ("", "cut", "none") or ttype not in TRANSITIONS:
        return None
    try:
        dur = float(raw.get("duration_s"))
    except (TypeError, ValueError):
        return None
    if dur <= 0:
        return None
    return {"type": ttype, "duration_s": min(dur, 3.0)}


def resolve_subtitles_path(maybe_path: str, edit_dir: Path) -> Path:
    """Resolve the EDL's subtitles path: relative to the EDL's directory, else the
    current directory (agents often write "edit/master.srt"). A missing file is an
    error: rendering on without it silently ships a video with no captions."""
    candidates = [resolve_path(maybe_path, edit_dir)]
    if not Path(maybe_path).is_absolute():
        candidates.append(Path(maybe_path).resolve())
    for c in candidates:
        if c.exists():
            return c
    tried = ", ".join(str(c) for c in candidates)
    sys.exit(f"subtitles file in EDL not found (tried {tried}). Fix the path or pass --no-subtitles.")


# -------- HDR → SDR tone mapping (HLG / PQ sources) --------------------------
#
# iPhone defaults to HLG HDR in Rec.2020 (and many mirrorless cameras ship PQ).
# If the source is HDR and we only downconvert bit depth (yuv420p10le → yuv420p)
# without tone-mapping, the output is 8-bit but still carries HLG/PQ transfer
# metadata. Players that honor the metadata (screen recorders, most social
# upload re-encodes) interpret 8-bit values in an HDR container and the result
# looks oversaturated / blown out. QuickTime on macOS can hide this locally —
# screen recording and uploaded renders cannot.
#
# Fix: detect HDR via color_transfer and prepend a zscale+tonemap chain to the
# vf graph so the output is clean Rec.709 SDR.

HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}  # PQ (HDR10) and HLG

TONEMAP_CHAIN = (
    "zscale=t=linear:npl=100,"
    "format=gbrpf32le,"
    "zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,"
    "format=yuv420p"
)


def is_hdr_source(video: Path) -> bool:
    """Return True if the source uses a PQ or HLG transfer function."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=color_transfer",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() in HDR_TRANSFERS
    except subprocess.CalledProcessError:
        return False


def is_portrait_source(video: Path) -> bool:
    """Return True if the displayed video is portrait, including rotation."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=width,height:stream_side_data=rotation",
             "-of", "json", str(video)],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(out.stdout).get("streams") or []
        if not streams:
            return False
        stream = streams[0]
        w, h = int(stream["width"]), int(stream["height"])

        # ffmpeg autorotates display-matrix side data before applying filters.
        # Swap coded dimensions for quarter-turns so the scale axis is selected
        # from the dimensions the filter actually sees. A plain metadata tag is
        # intentionally ignored because it does not guarantee autorotation.
        rotation = 0
        for side_data in stream.get("side_data_list") or []:
            if side_data.get("rotation") is not None:
                rotation = side_data["rotation"]
                break
        if int(round(float(rotation))) % 360 in (90, 270):
            w, h = h, w
        return h > w
    except (
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        OSError,
        OverflowError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return False


def parse_fps(value: str) -> str:
    """Validate and canonicalize an ffmpeg frame rate."""
    text = value.strip()
    if len(text) > 32 or not re.fullmatch(
        r"(?:[0-9]+(?:\.[0-9]+)?|[0-9]+/[0-9]+)", text
    ):
        raise argparse.ArgumentTypeError(
            "FPS must be a positive number or rational, e.g. 30 or 30000/1001"
        )
    try:
        rate = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise argparse.ArgumentTypeError(
            "FPS must be a positive number or rational, e.g. 30 or 30000/1001"
        ) from exc
    if rate <= 0:
        raise argparse.ArgumentTypeError("FPS must be greater than zero")
    # FFmpeg stores video rates as AVRational (signed 32-bit components).
    # Bounding the reduced fraction keeps every accepted canonical value safe
    # for ffmpeg and makes parse_fps(parse_fps(value)) idempotent.
    max_component = 2_147_483_647
    if rate.numerator > max_component or rate.denominator > max_component:
        raise argparse.ArgumentTypeError("FPS precision or magnitude is too large")
    return f"{rate.numerator}/{rate.denominator}"


def probe_source_fps(video: Path) -> str | None:
    """Return an ffmpeg-ready source rate, preferring the average frame rate.

    ``avg_frame_rate`` represents the observed average and is the better default
    for variable-frame-rate inputs. ``r_frame_rate`` remains a fallback for
    streams where the average is unavailable. Values are normalized to an exact
    rational so rates such as ``30000/1001`` survive without rounding.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate,r_frame_rate",
             "-of", "json", str(video)],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(out.stdout).get("streams") or []
        if not streams:
            return None
        for field in ("avg_frame_rate", "r_frame_rate"):
            value = streams[0].get(field)
            if value and value != "0/0":
                try:
                    return parse_fps(value)
                except argparse.ArgumentTypeError:
                    continue
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
        return None
    return None


# -------- Per-segment extraction (Rule 2 + Rule 3) --------------------------


def extract_segment(
    source: Path,
    seg_start: float,
    duration: float,
    grade_filter: str,
    out_path: Path,
    preview: bool = False,
    draft: bool = False,
    rate: str | None = None,
    canvas: tuple[int, int] | None = None,
    effect: str | None = None,
) -> None:
    """Extract a cut range as its own MP4 with grade + 30ms audio fades baked in.

    `-ss` before `-i` for fast accurate seeking. Every segment lands on the
    shared `canvas` (scale + pad) so xfade can blend any pair; without a canvas
    the old behavior is kept — 1080p landscape, or height-locked for portrait
    sources.

    Quality ladder:
      - final (default): canvas-size libx264 fast CRF 20
      - preview:         canvas-size libx264 medium CRF 22 (evaluable for QC)
      - draft:           720p libx264 ultrafast CRF 28 (cut-point check only)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if canvas is not None:
        w, h = canvas
        scale = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
    else:
        portrait = is_portrait_source(source)
        if draft:
            scale = "scale=-2:1280" if portrait else "scale=1280:-2"
        else:
            scale = "scale=-2:1920" if portrait else "scale=1920:-2"

    out_rate = rate if rate is not None else (probe_source_fps(source) or "24")

    vf_parts: list[str] = []
    if is_hdr_source(source):
        vf_parts.append(TONEMAP_CHAIN)
    if canvas is not None and video_effect_filter(effect, duration, *canvas,
                                                 fps=float(Fraction(out_rate))):
        # zoompan needs headroom above the canvas to move inside; cover-scale to
        # ZOOM_DEPTH× then animate the window.
        zw = int(w * ZOOM_DEPTH)
        zh = int(h * ZOOM_DEPTH)
        vf_parts.append(
            f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
            f"crop={zw}:{zh},fps={Fraction(out_rate)},"
            f"{video_effect_filter(effect, duration, w, h, fps=float(Fraction(out_rate)))}"
        )
    else:
        vf_parts.append(scale)
    if grade_filter:
        vf_parts.append(grade_filter)
    vf = ",".join(vf_parts)

    # 30ms audio fades at both edges (Rule 3) — prevent pops
    fade_out_start = max(0.0, duration - 0.03)
    af = f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start:.3f}:d=0.03"

    if draft:
        preset, crf = "ultrafast", "28"
    elif preview:
        preset, crf = "medium", "22"
    else:
        preset, crf = "fast", "20"

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seg_start:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-pix_fmt", "yuv420p", "-r", out_rate,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def extract_image_segment(
    image: Path,
    duration: float,
    grade_filter: str,
    effect: str | None,
    out_path: Path,
    canvas: tuple[int, int],
    rate: str,
    preview: bool = False,
    draft: bool = False,
) -> None:
    """Turn a still into a segment: cover-scale, Ken Burns via zoompan, silent audio.

    zoompan needs the input larger than the canvas, so the image is cover-scaled
    to 2× the canvas first. A silent stereo track keeps the uniform audio layout
    the concat and acrossfade assembly rely on.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = canvas
    fps = float(Fraction(rate))
    frames = max(1, int(round(duration * fps)))

    vf_parts: list[str] = [
        f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase",
        f"crop={w * 2}:{h * 2}",
    ]
    motion = image_effect_filter(effect, w, h, frames, fps)
    vf_parts.append(f"{motion}:d={frames}:fps={fps:g}")
    if grade_filter:
        vf_parts.append(grade_filter)
    vf_parts.append("format=yuv420p")
    vf = ",".join(vf_parts)

    if draft:
        preset, crf = "ultrafast", "28"
    elif preview:
        preset, crf = "medium", "22"
    else:
        preset, crf = "fast", "20"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(image),
        "-f", "lavfi", "-t", f"{duration:.3f}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-pix_fmt", "yuv420p", "-r", rate,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def extract_all_segments(
    edl: dict,
    edit_dir: Path,
    preview: bool,
    draft: bool = False,
    fps: str | None = None,
) -> list[Path]:
    """Extract every EDL range into edit_dir/clips_graded/seg_NN.mp4.
    Returns the ordered list of segment paths.

    If the EDL `grade` is "auto", analyze each segment range with
    `auto_grade_for_clip` and apply a per-segment subtle correction.
    Otherwise, apply the same preset/raw filter to every segment.
    """
    resolved = resolve_grade_filter(edl.get("grade"))
    is_auto = resolved == "__AUTO__"
    clips_dir = edit_dir / (
        "clips_draft" if draft else ("clips_preview" if preview else "clips_graded")
    )
    clips_dir.mkdir(parents=True, exist_ok=True)

    ranges = edl["ranges"]
    sources = edl["sources"]

    # Resolve ONE output frame rate for the entire render and apply it to every
    # segment. The lossless concat (Rule 2, `-c copy`) requires all segments to
    # share a frame rate; probing per-segment would diverge for multi-source
    # EDLs that mix rates (e.g. a 30fps and a 60fps source) and break the concat.
    # Explicit --fps wins; otherwise preserve the first source's rate.
    if fps is not None:
        out_rate = parse_fps(str(fps))
    elif ranges:
        first_src = resolve_path(sources[ranges[0]["source"]], edit_dir)
        out_rate = probe_source_fps(first_src) or "24"
    else:
        out_rate = "24"

    canvas = target_canvas(edl, edit_dir)

    seg_paths: list[Path] = []
    print(f"extracting {len(ranges)} segment(s) → {clips_dir.name}/  @ {out_rate} fps"
          f"{' (forced)' if fps is not None else ' (from source)'}"
          f"  canvas {canvas[0]}×{canvas[1]}")
    if is_auto:
        print("  (auto-grade per segment: analyzing each range)")
    for i, r in enumerate(ranges):
        src_name = r["source"]
        src_path = resolve_path(sources[src_name], edit_dir)
        start = float(r["start"])
        end = float(r["end"])
        duration = end - start
        out_path = clips_dir / f"seg_{i:02d}_{src_name}.mp4"
        kind = source_kind(src_path)
        effect = r.get("effect") if isinstance(r.get("effect"), str) else None
        seg_grade = r.get("grade") if isinstance(r.get("grade"), str) else None

        if is_auto and kind == "video":
            seg_filter, _stats = auto_grade_for_clip(src_path, start=start, duration=duration, verbose=False)
        elif seg_grade:
            seg_filter = resolve_grade_filter(seg_grade)
        else:
            seg_filter = resolved
        if seg_filter == "__AUTO__":
            seg_filter = ""

        note = r.get("beat") or r.get("note") or ""
        print(f"  [{i:02d}] {src_name}  {start:7.2f}-{end:7.2f}  ({duration:5.2f}s)  {note}"
              + (f"  [{kind}:{effect}]" if kind != "video" or effect else ""))
        if is_auto:
            print(f"        grade: {seg_filter or '(none)'}")
        if kind == "image":
            extract_image_segment(
                src_path, duration, seg_filter, effect, out_path,
                canvas=canvas, rate=out_rate, preview=preview, draft=draft,
            )
        else:
            extract_segment(
                src_path, start, duration, seg_filter, out_path,
                preview=preview, draft=draft, rate=out_rate,
                canvas=canvas, effect=effect,
            )
        seg_paths.append(out_path)

    return seg_paths


# -------- Lossless concat ----------------------------------------------------


def concat_segments(segment_paths: list[Path], out_path: Path, edit_dir: Path) -> None:
    """Lossless concat via the concat demuxer. No re-encode."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list = edit_dir / "_concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in segment_paths))

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"concat → {out_path.name}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    concat_list.unlink(missing_ok=True)


def output_duration(ranges: list[dict]) -> float:
    """Timeline length after transitions overlap adjacent segments."""
    total = 0.0
    for index, r in enumerate(ranges):
        dur = float(r["end"]) - float(r["start"])
        if index > 0:
            trans = transition_in(r)
            if trans:
                dur -= trans["duration_s"]
        total += max(dur, 0.0)
    return total


def assemble_segments(
    segment_paths: list[Path],
    ranges: list[dict],
    out_path: Path,
    edit_dir: Path,
    *,
    preview: bool = False,
) -> None:
    """Join segments into base.mp4.

    All hard cuts → lossless concat. Any `transition_in` on a range switches the
    whole assembly to one xfade (video) + acrossfade (audio) filter pass.
    """
    transitions = [transition_in(r) for r in ranges]
    if not any(transitions):
        concat_segments(segment_paths, out_path, edit_dir)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    for path in segment_paths:
        inputs += ["-i", str(path)]

    # xfade/concat require matching timebases; normalize every input to AVTB.
    filter_parts: list[str] = []
    for i in range(len(segment_paths)):
        filter_parts.append(f"[{i}:v]settb=AVTB[vin{i}]")
        filter_parts.append(f"[{i}:a]asettb=AVTB[ain{i}]")
    vlabel = "vin0"
    alabel = "ain0"
    # The timeline point where each transition starts is the accumulated output
    # length minus the transition's own overlap.
    accumulated = float(ranges[0]["end"]) - float(ranges[0]["start"]) if ranges else 0.0
    for k in range(1, len(segment_paths)):
        trans = transitions[k]
        dur_k = float(ranges[k]["end"]) - float(ranges[k]["start"])
        if not trans:
            # Hard cut between blended sections: concatenate via zero-second xfade
            # equivalent — just chain a cut with a minimal fade-free jump.
            filter_parts.append(f"[{vlabel}][vin{k}]concat=n=2:v=1:a=0[v{k}]")
            filter_parts.append(f"[{alabel}][ain{k}]concat=n=2:v=0:a=1[a{k}]")
            accumulated += dur_k
        else:
            d = trans["duration_s"]
            offset = accumulated - d
            filter_parts.append(
                f"[{vlabel}][vin{k}]xfade=transition={trans['type']}:duration={d:.3f}:offset={offset:.3f}[v{k}]"
            )
            filter_parts.append(f"[{alabel}][ain{k}]acrossfade=d={d:.3f}:o=1[a{k}]")
            accumulated = offset + dur_k
        vlabel = f"v{k}"
        alabel = f"a{k}"

    preset, crf = ("medium", "22") if preview else ("fast", "20")
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{vlabel}]", "-map", f"[{alabel}]",
        "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"assemble ({len(segment_paths)} segs, transitions) → {out_path.name}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


# -------- Music bed + SFX mix -------------------------------------------------


def mix_audio(
    base_path: Path,
    audio_spec: dict,
    total_duration: float,
    out_path: Path,
    edit_dir: Path,
) -> None:
    """Mix a music bed and timed SFX hits under the video's own audio.

    `audio_spec` is the EDL `audio` block: `music: {source, volume, fade_in_s,
    fade_out_s}` and `sfx: [{source, at_s, volume}]`. Output keeps the base
    video stream untouched (copy) and rebuilds only the audio track.
    """
    sources = audio_spec.get("sources") or {}
    music = audio_spec.get("music")
    sfx = audio_spec.get("sfx") or []

    inputs: list[str] = ["-i", str(base_path)]

    def _audio_path(key) -> Path | None:
        if not isinstance(key, str):
            return None
        raw = sources.get(key, key)
        path = resolve_path(str(raw), edit_dir)
        return path if path.is_file() else None

    music_path: Path | None = None
    if isinstance(music, dict) and music.get("source"):
        music_path = _audio_path(music["source"])
        if music_path is None:
            print(f"  music source {music['source']} không tìm thấy, bỏ qua")
        else:
            inputs += ["-i", str(music_path)]
    sfx_paths: list[Path] = []
    sfx_items: list[dict] = []
    for item in sfx:
        if not isinstance(item, dict) or not item.get("source"):
            continue
        path = _audio_path(item["source"])
        if path is None:
            print(f"  sfx source {item['source']} không tìm thấy, bỏ qua")
            continue
        sfx_paths.append(path)
        sfx_items.append(item)
        inputs += ["-i", str(path)]

    filter_parts: list[str] = ["[0:a]anull[base]"]
    mix_labels: list[str] = ["[base]"]

    if music_path is not None:
        volume = min(max(float(music.get("volume", 0.25)), 0.0), 1.0)
        fade_in = max(float(music.get("fade_in_s", 0.5)), 0.0)
        fade_out = max(float(music.get("fade_out_s", 2.0)), 0.0)
        fade_out_start = max(0.0, total_duration - fade_out)
        # Loop the bed until the video ends, then trim exactly to length.
        filter_parts.append(
            f"[1:a]aloop=loop=-1:size=2147483647,atrim=duration={total_duration:.3f},"
            f"volume={volume:.3f},afade=t=in:st=0:d={fade_in:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}[mus]"
        )
        mix_labels.append("[mus]")

    for i, item in enumerate(sfx_items):
        at = max(float(item.get("at_s", 0.0)), 0.0)
        volume = min(max(float(item.get("volume", 0.8)), 0.0), 1.0)
        delay_ms = int(round(at * 1000))
        input_index = (2 if music_path is not None else 1) + i
        filter_parts.append(
            f"[{input_index}:a]adelay={delay_ms}|{delay_ms},volume={volume:.3f}[fx{i}]"
        )
        mix_labels.append(f"[fx{i}]")

    n = len(mix_labels)
    filter_parts.append(
        f"{''.join(mix_labels)}amix=inputs={n}:duration=first:normalize=0,"
        f"alimiter=limit=0.95[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"mix audio (music: {'yes' if music_path else 'no'}, sfx: {len(sfx_paths)}) → {out_path.name}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


# -------- Master SRT (Rule 5) ------------------------------------------------


PUNCT_BREAK = set(".,!?;:")


def _srt_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _words_in_range(transcript: dict, t_start: float, t_end: float) -> list[dict]:
    out: list[dict] = []
    for w in transcript.get("words", []):
        if w.get("type") != "word":
            continue
        ws = w.get("start")
        we = w.get("end")
        if ws is None or we is None:
            continue
        if we <= t_start or ws >= t_end:
            continue
        out.append(w)
    return out


CHUNK_WORDS = 2         # target words per cue
CHUNK_MAX_WORDS = 3     # a too-short chunk may grow to this many words
CHUNK_MIN_S = 0.35      # a cue shorter than this reads as a flash
CHUNK_PAUSE_S = 0.3     # a gap this long between words ends the cue


def chunk_words(words: list[dict]) -> list[list[dict]]:
    """Group transcript words into caption cues.

    A cue closes on trailing punctuation or on a pause before the next word.
    Otherwise it closes at CHUNK_WORDS words, unless it would be on screen for
    less than CHUNK_MIN_S; then it takes up to CHUNK_MAX_WORDS words. So
    "does | is" across a pause stays split, and fast "what a" does not flash.
    """
    words = [w for w in words if (w.get("text") or "").strip()]
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for i, w in enumerate(words):
        current.append(w)
        text = w["text"].strip()
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - w["end"]) if nxt else 0.0
        dur = w["end"] - current[0]["start"]
        if (
            nxt is None
            or text[-1] in PUNCT_BREAK
            or gap >= CHUNK_PAUSE_S
            or len(current) >= CHUNK_MAX_WORDS
            or (len(current) >= CHUNK_WORDS and dur >= CHUNK_MIN_S)
        ):
            chunks.append(current)
            current = []
    return chunks


def build_master_srt(edl: dict, edit_dir: Path, out_path: Path) -> None:
    """Build an output-timeline SRT from per-source transcripts.

    - phrase-aware ~2-word chunks (see chunk_words)
    - UPPERCASE text
    - Output times computed as word.start - segment_start + segment_offset
    """
    transcripts_dir = edit_dir / "transcripts"
    sources = edl["sources"]

    entries: list[tuple[float, float, str]] = []
    seg_offset = 0.0

    for i, r in enumerate(edl["ranges"]):
        src_name = r["source"]
        seg_start = float(r["start"])
        seg_end = float(r["end"])
        seg_duration = seg_end - seg_start

        tr_path = transcripts_dir / f"{src_name}.json"
        if not tr_path.exists():
            if source_kind(resolve_path(sources[src_name], edit_dir)) != "image":
                print(f"  no transcript for {src_name}, skipping captions for this segment")
        else:
            transcript = json.loads(tr_path.read_text())
            words_in_seg = _words_in_range(transcript, seg_start, seg_end)

            for chunk in chunk_words(words_in_seg):
                local_start = max(seg_start, chunk[0].get("start", seg_start))
                local_end = min(seg_end, chunk[-1].get("end", seg_end))
                out_start = max(0.0, local_start - seg_start) + seg_offset
                out_end = max(0.0, local_end - seg_start) + seg_offset
                if out_end <= out_start:
                    out_end = out_start + 0.4
                text = " ".join((w.get("text") or "").strip() for w in chunk)
                text = re.sub(r"\s+", " ", text).strip()
                # Strip trailing punctuation for cleaner uppercase look
                text = text.rstrip(",;:")
                text = text.upper()
                entries.append((out_start, out_end, text))

        # The next scene's transition overlaps the tail of this one, shifting
        # every later cue earlier on the output timeline.
        next_trans = None
        if i + 1 < len(edl["ranges"]):
            next_trans = transition_in(edl["ranges"][i + 1])
        seg_offset += seg_duration - (next_trans["duration_s"] if next_trans else 0.0)

    # Sort and write as SRT
    entries.sort(key=lambda e: e[0])
    lines: list[str] = []
    for i, (a, b, t) in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(a)} --> {_srt_timestamp(b)}")
        lines.append(t)
        lines.append("")
    out_path.write_text("\n".join(lines))
    print(f"master SRT → {out_path.name} ({len(entries)} cues)")


# -------- Loudness normalization (social-ready audio) -----------------------


# Social-media standard: -14 LUFS integrated, -1 dBTP peak, LRA 11 LU.
# Matches YouTube / Instagram / TikTok / X / LinkedIn normalization targets.
LOUDNORM_I = -14.0
LOUDNORM_TP = -1.0
LOUDNORM_LRA = 11.0


def measure_loudness(video_path: Path) -> dict[str, str] | None:
    """Run ffmpeg loudnorm first pass and parse the JSON measurement.

    Returns a dict with measured_i, measured_tp, measured_lra, measured_thresh,
    target_offset, or None if measurement failed.
    """
    filter_str = (
        f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}:print_format=json"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(video_path),
        "-af", filter_str,
        "-vn", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # loudnorm prints the JSON to stderr at the end of the run
    stderr = proc.stderr

    # Find the JSON block — loudnorm output contains a `{ ... }` block
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stderr[start : end + 1])
    except json.JSONDecodeError:
        return None
    needed = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not needed.issubset(data.keys()):
        return None
    return data


def apply_loudnorm_two_pass(
    input_path: Path,
    output_path: Path,
    preview: bool = False,
) -> bool:
    """Run two-pass loudnorm on input_path, write normalized copy to output_path.

    Returns True on success, False if measurement failed (caller should fall
    back to copying the input unchanged).

    In preview mode, skips the measurement pass and uses a one-pass approximation
    for speed. Final mode always does the proper two-pass.
    """
    if preview:
        # One-pass approximation — faster, slightly less accurate.
        filter_str = f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-nostats",
            "-i", str(input_path),
            "-c:v", "copy",
            "-af", filter_str,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(output_path),
        ]
        print(f"  loudnorm (1-pass preview) → {output_path.name}")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True

    # Full two-pass
    print(f"  loudnorm pass 1: measuring {input_path.name}")
    measurement = measure_loudness(input_path)
    if measurement is None:
        print("  loudnorm measurement failed — falling back to 1-pass")
        return apply_loudnorm_two_pass(input_path, output_path, preview=True)

    print(f"    measured: I={measurement['input_i']} LUFS  "
          f"TP={measurement['input_tp']}  LRA={measurement['input_lra']}")

    # Pure silence measures -inf — loudnorm can't normalize it, so don't try.
    if "-inf" in (str(measurement["input_i"]), str(measurement["input_tp"])):
        print("    silent track — copying audio as-is")
        run(["ffmpeg", "-y", "-i", str(input_path), "-c:v", "copy",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", str(output_path)], quiet=True)
        return True

    filter_str = (
        f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}"
        f":measured_I={measurement['input_i']}"
        f":measured_TP={measurement['input_tp']}"
        f":measured_LRA={measurement['input_lra']}"
        f":measured_thresh={measurement['input_thresh']}"
        f":offset={measurement['target_offset']}"
        f":linear=true"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(input_path),
        "-c:v", "copy",
        "-af", filter_str,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(output_path),
    ]
    print(f"  loudnorm pass 2: normalizing → {output_path.name}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return True


# -------- Final compositing (Rule 1 + Rule 4) -------------------------------


def build_final_composite(
    base_path: Path,
    overlays: list[dict],
    subtitles_path: Path | None,
    out_path: Path,
    edit_dir: Path,
) -> None:
    """Final pass: base → overlays (PTS-shifted) → subtitles LAST → out.

    If there are no overlays and no subtitles, just copy base to out.
    """
    has_overlays = bool(overlays)
    has_subs = (
        subtitles_path is not None
        and subtitles_path.exists()
        and subtitles_path.stat().st_size > 0
    )

    if not has_overlays and not has_subs:
        # Nothing to do — just rename/copy base to final name
        run(["ffmpeg", "-y", "-i", str(base_path), "-c", "copy", str(out_path)], quiet=True)
        return

    inputs: list[str] = ["-i", str(base_path)]
    for ov in overlays:
        ov_path = resolve_path(ov["file"], edit_dir)
        inputs += ["-i", str(ov_path)]

    filter_parts: list[str] = []
    # PTS-shift every overlay so its frame 0 lands at start_in_output
    for idx, ov in enumerate(overlays, start=1):
        t = float(ov["start_in_output"])
        filter_parts.append(f"[{idx}:v]setpts=PTS-STARTPTS+{t}/TB[a{idx}]")

    # Chain overlays on top of base
    current = "[0:v]"
    for idx, ov in enumerate(overlays, start=1):
        t = float(ov["start_in_output"])
        dur = float(ov["duration"])
        end = t + dur
        next_label = f"[v{idx}]"
        filter_parts.append(
            f"{current}[a{idx}]overlay=enable='between(t,{t:.3f},{end:.3f})'{next_label}"
        )
        current = next_label

    # Subtitles LAST — Rule 1
    if has_subs:
        subs_abs = str(subtitles_path.resolve()).replace(":", r"\:").replace("'", r"\'")
        filter_parts.append(
            f"{current}subtitles='{subs_abs}':force_style='{SUB_FORCE_STYLE}'[outv]"
        )
        out_label = "[outv]"
    else:
        # Rename the last overlay output to [outv] for consistency
        if has_overlays:
            filter_parts.append(f"{current}null[outv]")
            out_label = "[outv]"
        else:
            out_label = "[0:v]"

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", out_label,
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"compositing → {out_path.name}")
    print(f"  overlays: {len(overlays)}, subtitles: {'yes' if has_subs else 'no'}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


# -------- Main ---------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a video from an EDL")
    ap.add_argument("edl", type=Path, help="Path to edl.json")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output video path")
    ap.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: 1080p, medium, CRF 22 — evaluable for QC, faster than final.",
    )
    ap.add_argument(
        "--draft",
        action="store_true",
        help="Draft mode: 720p, ultrafast, CRF 28 — cut-point verification only.",
    )
    ap.add_argument(
        "--build-subtitles",
        action="store_true",
        help="Build master.srt from transcripts + EDL offsets before compositing",
    )
    ap.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Skip subtitles even if the EDL references one",
    )
    ap.add_argument(
        "--no-loudnorm",
        action="store_true",
        help="Skip audio loudness normalization. Default is on (-14 LUFS, -1 dBTP, LRA 11).",
    )
    ap.add_argument(
        "--fps",
        type=parse_fps,
        default=None,
        help="Output frame rate. Default: preserve the source's frame rate "
             "(falls back to 24 if it can't be probed). Pass e.g. --fps 30 or "
             "--fps 30000/1001 to force.",
    )
    args = ap.parse_args()

    edl_path = args.edl.resolve()
    if not edl_path.exists():
        sys.exit(f"edl not found: {edl_path}")

    edl = json.loads(edl_path.read_text())
    edit_dir = edl_path.parent
    out_path = args.output.resolve()

    # 1. Extract per-segment (auto-grade per range if EDL grade is "auto")
    segment_paths = extract_all_segments(
        edl, edit_dir, preview=args.preview, draft=args.draft, fps=args.fps
    )

    # 2. Assemble → base (lossless concat for hard cuts, xfade for transitions)
    if args.draft:
        base_name = "base_draft.mp4"
    elif args.preview:
        base_name = "base_preview.mp4"
    else:
        base_name = "base.mp4"
    base_path = edit_dir / base_name
    assemble_segments(segment_paths, edl["ranges"], base_path, edit_dir, preview=args.preview or args.draft)

    # 3. Subtitles: build if requested, resolve final path
    subs_path: Path | None = None
    if not args.no_subtitles:
        if args.build_subtitles:
            subs_path = edit_dir / "master.srt"
            build_master_srt(edl, edit_dir, subs_path)
        elif edl.get("subtitles"):
            subs_path = resolve_subtitles_path(edl["subtitles"], edit_dir)

    # 4. Composite (overlays + subtitles LAST) → intermediate (pre-loudnorm) path
    #    then fold in the optional music bed + SFX before loudness.
    overlays = edl.get("overlays") or []
    audio_spec = edl.get("audio")
    composite_path = base_path
    if isinstance(audio_spec, dict) and (audio_spec.get("music") or audio_spec.get("sfx")):
        mixed_path = edit_dir / "base_mixed.mp4"
        total = output_duration(edl.get("ranges") or [])
        audio_spec = {**audio_spec, "sources": edl.get("sources") or {}}
        mix_audio(base_path, audio_spec, total, mixed_path, edit_dir)
        composite_path = mixed_path
    if args.no_loudnorm:
        # Composite directly to final output
        build_final_composite(composite_path, overlays, subs_path, out_path, edit_dir)
    else:
        # Composite to a temp file, then run loudnorm → final output
        tmp_composite = out_path.with_suffix(".prenorm.mp4")
        build_final_composite(composite_path, overlays, subs_path, tmp_composite, edit_dir)
        print("loudness normalization → social-ready (-14 LUFS / -1 dBTP / LRA 11)")
        apply_loudnorm_two_pass(tmp_composite, out_path, preview=args.draft)
        tmp_composite.unlink(missing_ok=True)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\ndone: {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
