"""Timeline mix: voice, SFX, and an optional ducked music bed.

Stems are resampled to 48 kHz stereo. ``amix`` is always ``normalize=0``.
SFX are delayed by ``at - attack`` unless the resolver already stored a
placed start. Loudnorm stays outside this module, on the mixed file.
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np

DROP_FIRST = ("tick", "cut", "transition", "impact")


def should_mix(edl: dict) -> bool:
    """Version 1 renders skip the mix even if an ``audio`` key was added."""
    try:
        version = int(edl.get("version") or 1)
    except (TypeError, ValueError):
        version = 1
    return version >= 2 and bool(edl.get("audio"))


def measure_attack(path: Path, threshold_db: float = 30.0) -> float:
    """Seconds until the first sample within ``threshold_db`` of the peak."""
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width != 2 or rate <= 0:
        raise ValueError(f"{path} must be 16-bit PCM")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 0.0:
        return 0.0
    limit = peak * (10 ** (-threshold_db / 20.0))
    hits = np.flatnonzero(np.abs(samples) >= limit)
    if hits.size == 0:
        return 0.0
    return float(hits[0]) / float(rate)


def adelay_filter(seconds: float, channels: int = 2) -> str:
    ms = max(0, int(round(float(seconds) * 1000)))
    return "adelay=" + "|".join([str(ms)] * channels)


def sfx_start_seconds(item: dict) -> float:
    """File start on the output timeline. ``at`` is the hit, unless placed."""
    at = float(item["at"])
    if item.get("placed"):
        return max(0.0, at)
    attack = item.get("attack_s", item.get("attack", 0.0)) or 0.0
    return max(0.0, at - float(attack))


def db_to_linear(db: float) -> float:
    return 10 ** (float(db) / 20.0)


def duck_volume_expr(spans: list[tuple[float, float]], duck_db: float) -> str:
    """Extra gain while the voice is hot. ``duck_db`` is negative, about −13."""
    ducked = f"{db_to_linear(duck_db):.6f}"
    if not spans:
        return "volume=1"
    clauses = [f"between(t,{start:.3f},{end:.3f})" for start, end in spans]
    if len(clauses) == 1:
        condition = clauses[0]
    else:
        condition = "gt(" + "+".join(clauses) + ",0)"
    expr = f"if({condition},{ducked},1)"
    escaped = expr.replace("\\", r"\\").replace(",", r"\,").replace(":", r"\:")
    return f"volume='{escaped}'"


def build_mix_graph(
    sfx: list[dict],
    music: dict | None,
    voice_sample_rate: int,
    voice_start: float = 0.0,
    voice_input: int = 0,
) -> str:
    """ffmpeg filtergraph. ``voice_sample_rate`` forces a 48 kHz resample."""
    del voice_sample_rate  # every stem is resampled; the arg documents why
    parts: list[str] = []
    labels: list[str] = []
    delay = f",{adelay_filter(voice_start)}" if voice_start > 0 else ""
    parts.append(
        f"[{voice_input}:a]aresample=48000,aformat=channel_layouts=stereo{delay}[voice]"
    )
    labels.append("[voice]")
    index = voice_input + 1
    for item in sfx:
        label = f"s{index}"
        gain = float(item.get("gain_db", 0.0))
        parts.append(
            f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"{adelay_filter(sfx_start_seconds(item))},volume={gain:.3f}dB[{label}]"
        )
        labels.append(f"[{label}]")
        index += 1
    if music and music.get("file"):
        parts.append(
            f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"{music_gain_chain(music)}[bed]"
        )
        labels.append("[bed]")
    if len(labels) == 1:
        parts.append(f"{labels[0]}anull[aout]")
    else:
        joined = "".join(labels)
        parts.append(
            f"{joined}amix=inputs={len(labels)}:normalize=0:duration=longest[aout]"
        )
    return ";".join(parts)


def events_from_ranges(ranges: list[dict], intro_join: str = "transition", cuts: bool = True) -> list[dict]:
    """Cut events sit on content boundaries. The intro join is not a cut."""
    events: list[dict] = []
    offset = 0.0
    for index, segment in enumerate(ranges):
        duration = float(segment["end"]) - float(segment["start"])
        if index == 0:
            offset += duration
            continue
        previous = ranges[index - 1]
        role = segment.get("role", "content")
        prev_role = previous.get("role", "content")
        if prev_role == "intro":
            if intro_join not in ("", "none", None):
                events.append({"kind": str(intro_join), "at": round(offset, 6)})
        elif role == "outro":
            events.append({"kind": "stinger", "at": round(offset, 6)})
        elif cuts and role == "content" and prev_role == "content":
            events.append({"kind": "cut", "at": round(offset, 6)})
        offset += duration
    return events


def _over_budget(events: list[dict], min_gap: float, span: float, max_in_span: int) -> bool:
    times = sorted(float(event["at"]) for event in events)
    for earlier, later in zip(times, times[1:]):
        if later - earlier < min_gap - 1e-9:
            return True
    for start in times:
        count = sum(1 for moment in times if start <= moment < start + span)
        if count > max_in_span:
            return True
    return False


def cap_events(
    events: list[dict],
    min_gap: float = 1.5,
    span: float = 20.0,
    max_in_span: int = 8,
) -> tuple[list[dict], list[dict]]:
    """Drop tick, then cut, then transition, then impact. Keep reveal and stinger."""
    kept = list(events)
    dropped: list[dict] = []
    while kept and _over_budget(kept, min_gap, span, max_in_span):
        victim = None
        for kind in DROP_FIRST:
            candidates = [event for event in kept if event.get("kind") == kind]
            if candidates:
                victim = max(candidates, key=lambda event: float(event["at"]))
                break
        if victim is None:
            break
        kept.remove(victim)
        dropped.append(victim)
    return kept, dropped


def resolve_sfx(
    events: list[dict],
    manifest: dict,
    root: Path,
    *,
    optional: bool = False,
) -> list[dict]:
    """Bind a kind to a file and store ``at`` as hit time minus attack."""
    resolved = []
    root = Path(root)
    for event in events:
        kind = event["kind"]
        spec = manifest.get(kind)
        if not spec:
            if optional:
                continue
            raise FileNotFoundError(f"sfx kind '{kind}' is not in the manifest")
        path = root / spec["file"]
        if not path.is_file():
            if optional:
                continue
            raise FileNotFoundError(f"sfx kind '{kind}' missing file {path}")
        attack = measure_attack(path)
        visible = float(event["at"])
        resolved.append(
            {
                "kind": kind,
                "file": str(path),
                "at": round(visible - attack, 6),
                "visible_at": visible,
                "attack_s": attack,
                "placed": True,
                "gain_db": float(spec.get("gain_db", -10)),
            }
        )
    return resolved


def load_manifest(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def bind_sfx(
    events: list[dict],
    manifest: dict,
    root: Path,
    edit_dir: Path,
    *,
    optional: bool = False,
    min_gap: float = 1.5,
    span: float = 20.0,
    max_in_span: int = 8,
) -> list[dict]:
    """Cap density, record what was dropped, then bind the files that remain."""
    kept, dropped = cap_events(events, min_gap=min_gap, span=span, max_in_span=max_in_span)
    dest = Path(edit_dir) / "audio" / "sfx-dropped.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"dropped": dropped}, indent=2))
    return resolve_sfx(kept, manifest, root, optional=optional)


def attach_sfx(
    edl: dict,
    edit_dir: Path,
    *,
    preset: str = "generated",
    intro_join: str = "transition",
    optional: bool = False,
    min_gap: float = 1.5,
    span: float = 20.0,
    max_in_span: int = 8,
    manifest_path: Path,
    root: Path,
) -> dict:
    """Fill ``audio.sfx`` from ``audio.events`` or from range boundaries.

    A hand-written ``sfx`` list is left alone. Version 1 edits are not mixed.
    """
    if not should_mix(edl):
        return edl
    audio = dict(edl.get("audio") or {})
    if audio.get("sfx"):
        return edl
    events = audio.get("events")
    if events is None:
        events = events_from_ranges(
            list(edl.get("ranges") or []),
            intro_join=intro_join,
            cuts=preset != "documentary",
        )
    audio["events"] = list(events)
    audio["sfx"] = bind_sfx(
        list(events),
        load_manifest(manifest_path),
        root,
        edit_dir,
        optional=optional,
        min_gap=min_gap,
        span=span,
        max_in_span=max_in_span,
    )
    updated = dict(edl)
    updated["audio"] = audio
    return updated


class MusicError(ValueError):
    """A bed is missing, vocal, or requested while the channel lock is inconsistent."""


def escape_filter_expr(expr: str) -> str:
    return expr.replace("\\", r"\\").replace(",", r"\,").replace(":", r"\:")


def _lin(var: str, t0: float, t1: float, y0: float, y1: float) -> str:
    span = t1 - t0
    if span <= 1e-4:
        return f"{y1:.6f}"
    return f"({y0:.6f}+({y1 - y0:.6f})*({var}-{t0:.3f})/{span:.3f})"


def music_envelope_expr(music: dict) -> str:
    """Linear gain: 1 in gaps, ``duck_db`` under voice, 0 at the outro start.

    Attack and release are ramps around each voice span. The fade-in is a
    short ramp from silence at t=0. The fade-out finishes at ``outro_start``.
    """
    ducked = db_to_linear(float(music.get("duck_db", -13.0)))
    attack = max(0.0, float(music.get("attack_s", 0.08)))
    release = max(0.0, float(music.get("release_s", 0.40)))
    expr = "1"
    spans = [(float(a), float(b)) for a, b in (music.get("voice_spans") or [])]
    for start, end in reversed(spans):
        if end <= start:
            continue
        a1 = min(start + attack, end)
        r1 = end + release
        down = _lin("t", start, a1, 1.0, ducked)
        hold = f"{ducked:.6f}"
        up = _lin("t", end, r1, ducked, 1.0)
        expr = (
            f"if(between(t,{start:.3f},{a1:.3f}),{down},"
            f"if(between(t,{a1:.3f},{end:.3f}),{hold},"
            f"if(between(t,{end:.3f},{r1:.3f}),{up},{expr})))"
        )
    fade_in = float(music.get("fade_in_s", 0.15))
    if fade_in > 1e-4:
        expr = f"({expr})*if(lt(t,{fade_in:.3f}),t/{fade_in:.3f},1)"
    outro = music.get("outro_start")
    fade_out = float(music.get("fade_out_s", 0.50))
    if outro is not None and fade_out > 1e-4:
        stop = float(outro)
        begin = stop - fade_out
        expr = (
            f"({expr})*if(lt(t,{begin:.3f}),1,"
            f"if(lt(t,{stop:.3f}),({stop:.3f}-t)/{fade_out:.3f},0))"
        )
    return expr


def music_gain_chain(music: dict) -> str:
    """Bed gain, then the duck and fade envelope. ``gain_db`` is the dry level."""
    gain = float(music.get("gain_db", -16.0))
    # eval=frame: the default evaluates t once, so a fade-in at 0 mutes the bed.
    return (
        f"volume={gain:.3f}dB,"
        f"volume='{escape_filter_expr(music_envelope_expr(music))}':eval=frame"
    )


def load_music_manifest(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    for bed in data.get("beds") or []:
        if bed.get("vocals") is True:
            ident = bed.get("id", "?")
            raise MusicError(
                f"music bed '{ident}' sets vocals true; beds stay instrumental"
            )
    return data


def music_is_on(theme_music: dict | None, manifest: dict | None = None) -> bool:
    """Both locks have to be open. The committed manifest stays closed."""
    if not (theme_music or {}).get("enabled"):
        return False
    if manifest is not None and manifest.get("enabled") is False:
        return False
    return True


def voice_spans_from_ranges(ranges: list[dict]) -> list[list[float]]:
    spans: list[list[float]] = []
    offset = 0.0
    for segment in ranges:
        duration = float(segment["end"]) - float(segment["start"])
        if segment.get("role", "content") == "content":
            spans.append([round(offset, 6), round(offset + duration, 6)])
        offset += duration
    return spans


def outro_start_from_ranges(ranges: list[dict]) -> float | None:
    offset = 0.0
    for segment in ranges:
        if segment.get("role") == "outro":
            return round(offset, 6)
        offset += float(segment["end"]) - float(segment["start"])
    return None


def timeline_duration(edl: dict) -> float:
    if edl.get("total_duration_s"):
        return float(edl["total_duration_s"])
    total = 0.0
    for segment in edl.get("ranges") or []:
        total += float(segment["end"]) - float(segment["start"])
    return total


def _bed_by_id(manifest: dict, bed_id: str) -> dict:
    for bed in manifest.get("beds") or []:
        if bed.get("id") == bed_id:
            return bed
    raise MusicError(f"music bed '{bed_id}' is not in the manifest")


def read_pcm(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width != 2 or rate <= 0:
        raise ValueError(f"{path} must be 16-bit PCM")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels)
    return samples, rate


def write_pcm(path: Path, samples: np.ndarray, rate: int) -> None:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        channels = 1
        flat = data
    else:
        channels = int(data.shape[1])
        flat = data.reshape(-1)
    pcm = np.clip(np.round(flat * 32767.0), -32768, 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def loop_pcm(samples: np.ndarray, rate: int, duration: float, crossfade_s: float = 0.05) -> np.ndarray:
    """Repeat a mono buffer to ``duration`` with a short overlap at each join."""
    target = max(1, int(round(float(duration) * rate)))
    data = np.asarray(samples, dtype=np.float64).reshape(-1)
    if data.size == 0:
        return np.zeros(target, dtype=np.float64)
    if data.size >= target:
        return data[:target].copy()
    cf = int(round(crossfade_s * rate))
    cf = min(cf, data.size // 2)
    if cf < 2:
        reps = int(np.ceil(target / data.size))
        return np.tile(data, reps)[:target]
    fade_down = np.linspace(1.0, 0.0, cf, endpoint=False)
    fade_up = 1.0 - fade_down
    out = data.copy()
    while out.size < target:
        blended = out[-cf:] * fade_down + data[:cf] * fade_up
        out = np.concatenate([out[:-cf], blended, data[cf:]])
    return out[:target]


def prepare_bed(
    src: Path,
    dest: Path,
    duration: float,
    *,
    loop: bool = True,
    crossfade_s: float = 0.05,
    rate: int = 48000,
) -> Path:
    """Decode, then loop or trim to the output duration. Fades stay in the graph."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    decoded = dest.with_suffix(".decoded.wav")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ac", "2", "-ar", str(rate),
        "-c:a", "pcm_s16le",
        str(decoded),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    samples, file_rate = read_pcm(decoded)
    decoded.unlink(missing_ok=True)
    if samples.ndim == 1:
        samples = np.stack([samples, samples], axis=1)
    target = max(1, int(round(float(duration) * file_rate)))
    columns = []
    for channel in range(samples.shape[1]):
        column = samples[:, channel]
        if loop and column.size < target:
            columns.append(loop_pcm(column, file_rate, duration, crossfade_s))
        elif column.size >= target:
            columns.append(column[:target])
        else:
            columns.append(np.pad(column, (0, target - column.size)))
    write_pcm(dest, np.stack(columns, axis=1), file_rate)
    return dest


def apply_music_policy(
    edl: dict,
    edit_dir: Path,
    theme_music: dict,
    manifest: dict,
    manifest_dir: Path,
    duration: float,
) -> dict:
    """Drop the bed when the channel lock is closed. Otherwise loop it to length.

    A closed lock removes ``audio.music`` so the mix graph matches a render
    that never had a bed.
    """
    if not should_mix(edl):
        return edl
    audio = dict(edl.get("audio") or {})
    if not music_is_on(theme_music, manifest):
        audio.pop("music", None)
        updated = dict(edl)
        updated["audio"] = audio
        return updated
    music = dict(audio.get("music") or {})
    bed_id = music.get("id") or (theme_music or {}).get("id")
    if bed_id and not music.get("file"):
        bed = _bed_by_id(manifest, str(bed_id))
        music["file"] = str(Path(manifest_dir) / bed["file"])
        music.setdefault("gain_db", bed.get("gain_db", -16))
        music.setdefault("loop", bed.get("loop", True))
        music["id"] = bed_id
    if not music.get("file"):
        raise MusicError("music.enabled is true and no bed file or id is set")
    src = Path(music["file"])
    if not src.is_file():
        raise MusicError(f"music bed missing file {src}")
    defaults = {
        "duck_db": -13.0,
        "attack_s": 0.08,
        "release_s": 0.4,
        "fade_in_s": 0.15,
        "fade_out_s": 0.5,
    }
    for key, fallback in defaults.items():
        if key not in music:
            music[key] = (theme_music or {}).get(key, manifest.get(key, fallback))
    if not music.get("voice_spans"):
        music["voice_spans"] = voice_spans_from_ranges(list(edl.get("ranges") or []))
    if "outro_start" not in music:
        outro = outro_start_from_ranges(list(edl.get("ranges") or []))
        if outro is not None:
            music["outro_start"] = outro
    if duration > 0:
        dest = Path(edit_dir) / "audio" / "bed.wav"
        prepare_bed(src, dest, duration, loop=bool(music.get("loop", True)))
        music["file"] = str(dest)
    audio["music"] = music
    updated = dict(edl)
    updated["audio"] = audio
    return updated


def mix_command(
    video: Path,
    voice: Path | None,
    sfx_files: list[Path],
    music_file: Path | None,
    graph: str,
    out: Path,
    voice_from_video: bool,
) -> list[str]:
    """Picture is copied. The overlay filtergraph is not run again."""
    cmd = ["ffmpeg", "-y", "-i", str(video)]
    if not voice_from_video:
        if voice is None:
            raise ValueError("voice file is required when it is not the picture")
        cmd += ["-i", str(voice)]
    for path in sfx_files:
        cmd += ["-i", str(path)]
    if music_file is not None:
        cmd += ["-i", str(music_file)]
    cmd += [
        "-filter_complex", graph,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        str(out),
    ]
    return cmd
