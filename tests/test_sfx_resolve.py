import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

from audio import (  # noqa: E402
    bind_sfx,
    cap_events,
    events_from_ranges,
    load_manifest,
    resolve_sfx,
)


def max_volume_db(path: Path) -> float:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    for line in proc.stderr.splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].replace("dB", "").strip())
    raise AssertionError(proc.stderr[-400:])


class SfxResolveTests(unittest.TestCase):
    def test_three_content_ranges_cut_on_the_internal_boundaries(self):
        ranges = [
            {"source": "A", "start": 0, "end": 2, "role": "content"},
            {"source": "A", "start": 2, "end": 5, "role": "content"},
            {"source": "A", "start": 5, "end": 9, "role": "content"},
        ]
        events = events_from_ranges(ranges, intro_join="transition", cuts=True)
        self.assertEqual([event["kind"] for event in events], ["cut", "cut"])
        self.assertEqual([event["at"] for event in events], [2.0, 5.0])

    def test_intro_join_follows_the_theme(self):
        ranges = [
            {"source": "INTRO", "start": 0, "end": 2.5, "role": "intro"},
            {"source": "A", "start": 0, "end": 4, "role": "content"},
        ]
        joined = events_from_ranges(ranges, intro_join="transition")
        self.assertEqual(joined, [{"kind": "transition", "at": 2.5}])
        quiet = events_from_ranges(ranges, intro_join="none")
        self.assertEqual(quiet, [])

    def test_reveal_at_is_earlier_by_the_measured_attack(self):
        manifest = load_manifest(ROOT / "brand" / "sfx" / "manifest.json")
        events = [{"kind": "reveal", "at": 6.0}]
        resolved = resolve_sfx(events, manifest, ROOT / "brand" / "sfx")
        self.assertEqual(len(resolved), 1)
        attack = resolved[0]["attack_s"]
        self.assertGreater(attack, 0.04)
        self.assertAlmostEqual(resolved[0]["at"], 6.0 - attack, places=4)
        self.assertLess(resolved[0]["at"], resolved[0]["visible_at"])
        self.assertTrue(resolved[0]["placed"])

    def test_dropped_ids_are_written_beside_the_edit(self):
        manifest = load_manifest(ROOT / "brand" / "sfx" / "manifest.json")
        events = [
            {"kind": "tick", "at": 0.2, "id": "drop-tick"},
            {"kind": "reveal", "at": 0.3, "id": "keep"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            kept = bind_sfx(
                events, manifest, ROOT / "brand" / "sfx", edit, min_gap=1.5
            )
            dropped = json.loads((edit / "audio" / "sfx-dropped.json").read_text())
        self.assertEqual([item["id"] for item in dropped["dropped"]], ["drop-tick"])
        self.assertEqual([item["kind"] for item in kept], ["reveal"])

    def test_over_budget_drops_tick_then_cut(self):
        events = [
            {"kind": "reveal", "at": 0.0, "id": "keep"},
            {"kind": "tick", "at": 0.2, "id": "drop-tick"},
            {"kind": "cut", "at": 0.4, "id": "drop-cut"},
            {"kind": "stinger", "at": 0.6, "id": "keep-sting"},
        ]
        kept, dropped = cap_events(events, min_gap=1.5, span=20, max_in_span=8)
        self.assertEqual([event["kind"] for event in dropped], ["tick", "cut"])
        self.assertEqual({event["kind"] for event in kept}, {"reveal", "stinger"})

    def test_sfx_peak_stays_under_the_voice_peak(self):
        voice = ROOT / "brand" / "sfx" / "stinger.wav"
        sfx = ROOT / "brand" / "sfx" / "tick.wav"
        with tempfile.TemporaryDirectory() as tmp:
            gained = Path(tmp) / "tick-gained.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(sfx), "-af", "volume=-14dB", str(gained)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.assertLess(max_volume_db(gained), max_volume_db(voice))

    def test_missing_kind_names_the_kind(self):
        with self.assertRaises(FileNotFoundError) as caught:
            resolve_sfx([{"kind": "nope", "at": 1}], {}, ROOT / "brand" / "sfx", optional=False)
        self.assertIn("nope", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
