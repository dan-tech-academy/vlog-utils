"""Timeline mix: voice, SFX, and an optional ducked music bed.

Stems are resampled to 48 kHz stereo. ``amix`` is always ``normalize=0``.
SFX are delayed by ``at - attack`` unless the resolver already stored a
placed start. Loudnorm stays outside this module, on the mixed file.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


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
        gain = float(music.get("gain_db", -16.0))
        duck = float(music.get("duck_db", -13.0))
        spans = [(float(a), float(b)) for a, b in (music.get("voice_spans") or [])]
        parts.append(
            f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"volume={gain:.3f}dB,{duck_volume_expr(spans, duck)}[bed]"
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
