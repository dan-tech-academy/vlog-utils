import importlib.util
import struct
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).parents[1]
HELPERS = ROOT / "helpers"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audio = load("video_use_audio", HELPERS / "audio.py")
render = load("video_use_render_audio", HELPERS / "render.py")


def write_click(path: Path, silence_s: float = 0.1, rate: int = 48000) -> None:
    silence = [0] * int(silence_s * rate)
    click = [20000] * int(0.01 * rate)
    pcm = b"".join(struct.pack("<h", sample) for sample in silence + click)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)


class AttackAndGraphTests(unittest.TestCase):
    def test_attack_is_the_first_sample_near_the_peak(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "click.wav"
            write_click(path, 0.1)
            attack = audio.measure_attack(path)
        self.assertAlmostEqual(attack, 0.1, places=3)

    def test_sfx_is_placed_at_minus_attack_and_resampled(self):
        graph = audio.build_mix_graph(
            sfx=[{"file": "hit.wav", "at": 4.20, "attack": 0.09, "gain_db": -8}],
            music=None,
            voice_sample_rate=24000,
            voice_input=1,
        )
        self.assertIn("aresample=48000", graph)
        self.assertIn("normalize=0", graph)
        self.assertIn("adelay=4110|4110", graph)
        self.assertNotIn("force_style", graph)
        self.assertNotIn("overlay", graph)

    def test_music_graph_contains_duck_automation(self):
        graph = audio.build_mix_graph(
            sfx=[],
            music={
                "file": "bed.wav",
                "gain_db": -16,
                "duck_db": -13,
                "voice_spans": [(1.0, 5.0)],
            },
            voice_sample_rate=48000,
            voice_input=0,
        )
        self.assertIn(r"between(t\,1.000\,5.000)", graph)
        self.assertIn("normalize=0", graph)
        self.assertIn("volume=", graph)

    def test_mix_command_copies_video(self):
        cmd = audio.mix_command(
            Path("picture.mp4"),
            Path("voice.wav"),
            [Path("hit.wav")],
            None,
            "anull[aout]",
            Path("out.mp4"),
            voice_from_video=False,
        )
        joined = " ".join(cmd)
        self.assertIn("-c:v", cmd)
        self.assertEqual(cmd[cmd.index("-c:v") + 1], "copy")
        self.assertNotIn("overlay", joined)
        self.assertNotIn("-vf", cmd)


class RenderOrderTests(unittest.TestCase):
    def _run(self, edl):
        calls = []

        def extract(*_a, **_k):
            calls.append("extract")
            return []

        def concat(*_a, **_k):
            calls.append("concat")

        def composite(*_a, **_k):
            calls.append("composite")

        def mix(*_a, **_k):
            calls.append(("mix", str(_a[1])))

        def loud(src, _dest, preview=False):
            calls.append(("loud", str(src)))
            return True

        render.extract_all_segments = extract
        render.concat_segments = concat
        render.build_final_composite = composite
        render.mix_stems = mix
        render.apply_loudnorm_two_pass = loud
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            render.render_edl(edl, edit, edit / "final.mp4", no_subtitles=True)
        return calls

    def test_version_1_does_not_mix_and_loudnorm_follows_composite(self):
        calls = self._run({"version": 1, "sources": {}, "ranges": [], "audio": {"voice": {}}})
        self.assertEqual(
            [name if isinstance(name, str) else name[0] for name in calls],
            ["extract", "concat", "composite", "loud"],
        )

    def test_version_2_loudnorm_reads_the_mixed_file(self):
        edl = {
            "version": 2,
            "sources": {},
            "ranges": [],
            "audio": {"voice": {"file": "voice.wav", "start": 0}},
        }
        calls = self._run(edl)
        names = [name if isinstance(name, str) else name[0] for name in calls]
        self.assertEqual(names, ["extract", "concat", "composite", "mix", "loud"])
        mix_out = calls[3][1]
        loud_in = calls[4][1]
        self.assertEqual(mix_out, loud_in)
        self.assertTrue(mix_out.endswith(".mixed.mp4"))


if __name__ == "__main__":
    unittest.main()
