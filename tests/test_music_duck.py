"""Measured ducking. The number is the test, not the filter name."""

import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

from audio import (  # noqa: E402
    MusicError,
    apply_music_policy,
    build_mix_graph,
    load_music_manifest,
    loop_pcm,
    music_gain_chain,
    prepare_bed,
    read_pcm,
    write_pcm,
)
import render as video_render  # noqa: E402


def write_sine(path: Path, duration: float, rate: int = 48000, freq: float = 440.0, amp: float = 0.4) -> None:
    count = int(round(duration * rate))
    times = np.arange(count) / rate
    write_pcm(path, amp * np.sin(2 * np.pi * freq * times), rate)


def render_chain(src: Path, chain: str, dest: Path) -> None:
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner",
            "-i", str(src),
            "-filter_complex", f"[0:a]{chain}[a]",
            "-map", "[a]",
            "-c:a", "pcm_s16le",
            str(dest),
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.decode("utf-8", "replace")[-800:])


def rms_db(samples: np.ndarray, rate: int, start: float, end: float) -> float:
    data = samples if samples.ndim == 1 else samples.mean(axis=1)
    lo = int(round(start * rate))
    hi = int(round(end * rate))
    chunk = data[lo:hi]
    rms = float(np.sqrt(np.mean(np.square(chunk))))
    return 20.0 * np.log10(max(rms, 1e-12))


def true_peak_db(path: Path) -> float:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    text = proc.stderr
    marker = text.rfind("True peak")
    block = text[marker:] if marker >= 0 else text
    for line in block.splitlines():
        if "Peak:" in line:
            return float(line.split("Peak:")[1].replace("dBFS", "").strip())
    raise AssertionError(text[-600:])


class DuckMeasurementTests(unittest.TestCase):
    def _bed(self) -> dict:
        return {
            "file": "bed.wav",
            "gain_db": -16,
            "duck_db": -13,
            "attack_s": 0.08,
            "release_s": 0.40,
            "fade_in_s": 0.15,
            "fade_out_s": 0.50,
            "voice_spans": [(3.0, 7.0)],
            "outro_start": 9.0,
        }

    def test_voice_window_is_12_to_15_db_under_the_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            src = folder / "bed.wav"
            ducked = folder / "ducked.wav"
            dry = folder / "dry.wav"
            write_sine(src, 10.0)
            bed = self._bed()
            render_chain(src, music_gain_chain(bed), ducked)
            render_chain(src, "volume=-16.000dB", dry)
            samples, rate = read_pcm(ducked)
            dry_samples, _rate = read_pcm(dry)
            gap = rms_db(samples, rate, 0.5, 2.5)
            voice = rms_db(samples, rate, 4.0, 6.0)
            dry_gap = rms_db(dry_samples, rate, 0.5, 2.5)
            self.assertAlmostEqual(gap, dry_gap, delta=0.4)
            difference = voice - gap
            self.assertGreaterEqual(difference, -15.0)
            self.assertLessEqual(difference, -12.0)
            self.assertAlmostEqual(difference, -13.0, delta=0.5)
            tail = samples if samples.ndim == 1 else samples.mean(axis=1)
            after = tail[int(9.05 * rate):]
            self.assertLess(float(np.max(np.abs(after))), 1.0 / 32768.0)

    def test_disabled_music_matches_the_graph_without_a_bed(self):
        sfx = [{"file": "hit.wav", "at": 1.0, "gain_db": -10, "placed": True}]
        plain = build_mix_graph(sfx, None, 48000, voice_input=0)
        edl = {
            "version": 2,
            "ranges": [],
            "audio": {
                "voice": {"file": "voice.wav"},
                "sfx": sfx,
                "music": {"file": "brand/music/bed.wav", "gain_db": -16, "voice_spans": [[0, 1]]},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            closed = apply_music_policy(
                edl,
                Path(tmp),
                {"enabled": False},
                {"enabled": False, "beds": []},
                ROOT / "brand" / "music",
                8.0,
            )
        self.assertNotIn("music", closed["audio"])
        gated = build_mix_graph(closed["audio"]["sfx"], closed["audio"].get("music"), 48000)
        self.assertEqual(gated, plain)
        self.assertNotIn("[bed]", gated)

    def test_vocals_true_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({
                "enabled": True,
                "beds": [{"id": "verse", "file": "verse.wav", "vocals": True}],
            }))
            with self.assertRaises(MusicError) as caught:
                load_music_manifest(path)
        self.assertIn("verse", str(caught.exception))
        self.assertIn("vocals", str(caught.exception))

    def test_loop_crossfade_removes_the_join_step(self):
        rate = 48000
        raw = np.linspace(-1.0, 1.0, rate // 5)
        looped = loop_pcm(raw, rate, 1.0, 0.05)
        self.assertEqual(looped.size, rate)
        self.assertLess(float(np.max(np.abs(np.diff(looped)))), 0.05)

    def test_prepare_bed_loops_to_the_output_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            src = folder / "short.wav"
            dest = folder / "bed.wav"
            write_sine(src, 0.25)
            prepare_bed(src, dest, 1.0, loop=True)
            with wave.open(str(dest), "rb") as handle:
                self.assertEqual(handle.getnframes(), 48000)
                self.assertEqual(handle.getnchannels(), 2)

    def test_full_mix_loudnorm_true_peak_is_at_most_minus_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            picture = folder / "picture.mp4"
            voice = folder / "voice.wav"
            bed = folder / "bed.wav"
            mixed = folder / "mixed.mp4"
            mastered = folder / "master.mp4"
            write_sine(voice, 4.0, amp=0.2)
            write_sine(bed, 8.0, freq=220.0, amp=0.35)
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner",
                    "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=8",
                    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-shortest", "-t", "8",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                    "-c:a", "aac", "-ar", "48000",
                    str(picture),
                ],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            music = self._bed()
            music["file"] = str(bed)
            graph = build_mix_graph([], music, 48000, voice_start=2.0, voice_input=1)
            from audio import mix_command

            cmd = mix_command(picture, voice, [], bed, graph, mixed, voice_from_video=False)
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            video_render.apply_loudnorm_two_pass(mixed, mastered)
            peak = true_peak_db(mastered)
        self.assertLessEqual(peak, -1.0)


class RepoManifestTests(unittest.TestCase):
    def test_committed_manifest_is_closed_and_empty(self):
        manifest = load_music_manifest(ROOT / "brand" / "music" / "manifest.json")
        self.assertFalse(manifest["enabled"])
        self.assertEqual(manifest["beds"], [])
        self.assertEqual(manifest["duck_db"], -13)


if __name__ == "__main__":
    unittest.main()
