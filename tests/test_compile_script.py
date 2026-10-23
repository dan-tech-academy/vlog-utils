"""Script compiler: plan stays offline, the EDL matches the fake-TTS fixture."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

import compile_script  # noqa: E402
from captions import cues_for_edl  # noqa: E402
from speech.fake import FakeSynthesizer  # noqa: E402


SCRIPT = {
    "language": "en",
    "title": "Fixture",
    "beats": [
        {"id": "hook", "text": "Hello there", "visual": None},
        {"id": "point", "text": "Saved 40 percent", "visual": "stat"},
    ],
}


class PlanTests(unittest.TestCase):
    def test_plan_prints_voice_templates_sfx_and_music_without_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            with patch.object(compile_script.subprocess, "run", side_effect=AssertionError("ffmpeg")):
                plan = compile_script.plan_script(
                    SCRIPT,
                    compile_script.load_theme(edit),
                    compile_script.load_speech_config(edit),
                )
                text = compile_script.format_plan(plan)
        self.assertEqual(text, (
            "voice en-US-AndrewNeural\n"
            "template hook section\n"
            "template point stat\n"
            "sfx reveal\n"
            "sfx cut\n"
            "sfx reveal\n"
            "music none\n"
        ))

    def test_skill_keeps_footage_on_the_inventory_path(self):
        skill = (ROOT / "SKILL.md").read_text()
        self.assertIn(
            "A folder of camera files stays on the inventory path. "
            "`compile_script.py` is only for a folder that has `script.json` and no camera media.",
            skill,
        )


class CompileTests(unittest.TestCase):
    def test_two_beats_match_ranges_captions_and_the_selected_visual(self):
        synth = FakeSynthesizer()
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            with patch.object(compile_script.subprocess, "run", side_effect=AssertionError("ffmpeg")):
                edl = compile_script.compile_script(
                    SCRIPT,
                    edit,
                    provider="fake",
                    synthesizer=synth,
                    materialize=False,
                )
            self.assertEqual(synth.calls, 1)
            self.assertEqual(edl["version"], 2)
            self.assertTrue(edl["plate"])
            self.assertEqual(
                [(item["beat"], item["start"], item["end"], item["role"]) for item in edl["ranges"]],
                [("hook", 0.0, 0.8, "content"), ("point", 0.8, 2.0, "content")],
            )
            self.assertEqual([item["template"] for item in edl["visuals"]], ["section", "stat"])
            self.assertEqual(edl["visuals"][1]["params"]["value"], "40")
            self.assertEqual(edl["visuals"][0]["params"]["label"], "hook")
            self.assertNotIn("music", edl["audio"])
            self.assertEqual(
                [item["kind"] for item in edl["audio"]["events"]],
                ["reveal", "cut", "reveal"],
            )
            cues = cues_for_edl(edl, edit, "bold-overlay", "en")
            self.assertEqual(
                [(round(cue["start"], 3), round(cue["end"], 3), cue["text"]) for cue in cues],
                [(0.0, 0.8, "HELLO THERE"), (0.8, 1.6, "SAVED 40"), (1.6, 2.0, "PERCENT")],
            )
            stored = json.loads((edit / "edl.json").read_text())
            self.assertEqual(stored["ranges"], edl["ranges"])


if __name__ == "__main__":
    unittest.main()
