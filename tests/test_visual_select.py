import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

from visuals.select import (  # noqa: E402
    CATALOG,
    assign_phrases,
    clamp_duration,
    select_visual,
)


class SelectTests(unittest.TestCase):
    def test_table(self):
        self.assertEqual(select_visual("Latency dropped 40%"), "stat")
        self.assertEqual(select_visual("Python so với Java"), "comparison")
        self.assertEqual(select_visual("A hơn B"), "comparison")
        self.assertEqual(select_visual("Run `npm test` now"), "code")
        self.assertEqual(
            select_visual("1. one\n2. two\n3. three"),
            "list",
        )
        self.assertEqual(select_visual("What changed?"), "question")
        self.assertEqual(
            select_visual("A plain sentence.", beat="HOOK", first_in_beat=True),
            "section",
        )
        self.assertEqual(select_visual("A plain sentence."), "kinetic")

    def test_stat_beats_the_section_signal(self):
        self.assertEqual(
            select_visual("We saved 40%", beat="HOOK", first_in_beat=True),
            "stat",
        )

    def test_stickiness_keeps_the_current_template(self):
        first = select_visual("Open with the point.", beat="HOOK", first_in_beat=True)
        self.assertEqual(first, "section")
        stayed = select_visual("Then say it again.", previous=first)
        self.assertEqual(stayed, "section")
        interrupted = select_visual("Down 40% after that.", previous=first)
        self.assertEqual(interrupted, "stat")

    def test_same_inputs_are_stable(self):
        kwargs = {"text": "Python so với Java", "previous": "kinetic"}
        self.assertEqual(select_visual(**kwargs), select_visual(**kwargs))

    def test_explicit_id_must_be_in_the_catalog(self):
        self.assertEqual(select_visual("anything", explicit="quote"), "quote")
        self.assertEqual(select_visual("anything", explicit="custom"), "custom")
        with self.assertRaises(ValueError):
            select_visual("anything", explicit="sparkles")
        self.assertIn("quote", CATALOG)

    def test_custom_overlay_survives_and_duration_floor_holds(self):
        custom = {"template": "custom", "file": "edit/animations/slot_1/render.mp4"}
        assigned = assign_phrases(
            [
                {"id": "a", "text": "Hello there.", "beat": "HOOK", "start": 0, "end": 2,
                 "words": [{"start": 0.2}, {"start": 0.8}]},
                {"id": "b", "text": "Saved 40% of the wait.", "beat": "POINT", "start": 2, "end": 5,
                 "words": [{"start": 2.2}, {"start": 3.1}]},
            ],
            overlays=[custom],
        )
        self.assertEqual(assigned["overlays"], [custom])
        self.assertEqual([item["template"] for item in assigned["visuals"]], ["section", "stat"])
        self.assertEqual(assigned["events"][1]["kind"], "reveal")
        self.assertGreaterEqual(clamp_duration("stat", 1.2), 3.0)
        self.assertEqual(clamp_duration("kinetic", 2.0), 2.0)


if __name__ == "__main__":
    unittest.main()
