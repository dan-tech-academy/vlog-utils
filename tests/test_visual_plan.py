"""Visual-plan guardrails. The checker does not map a digit to a template."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

from check_visual_plan import check_visual_plan  # noqa: E402
from orientation import resolve_orientation  # noqa: E402
from style import load_style, validate_style  # noqa: E402

STYLE = load_style()
MANIFEST = {
    "enabled": True,
    "beds": [
        {"id": "measured", "file": "measured.wav", "vocals": False, "license": "CC0-1.0"},
        {"id": "tense", "file": "tense.wav", "vocals": False, "license": "CC0-1.0"},
    ],
}


def _inventory(*roles):
    return {"files": [{"path": f"{role}.bin", "role": role} for role in roles]}


def _run(orientation="landscape", chrome="clean"):
    return {"style": "explainer", "orientation": orientation, "chrome": chrome}


def _segment(**overrides):
    segment = {
        "id": "s1",
        "start": 0.5,
        "end": 3.5,
        "quote": "nhanh hơn 40%",
        "intent": "comparison",
        "why": "The line contrasts speed and states a percent. The setup side is trước.",
        "treatment": {
            "layout": "side-card",
            "motion": "count-up",
            "data": {"type": "comparison", "before": "trước", "after": "40%"},
            "text": "40%",
            "overlay": "alpha-card",
            "sfx": "reveal",
            "transition": "cut",
        },
    }
    segment.update(overrides)
    return segment


def _plan(*segments, music=None, orientation="landscape"):
    body = {"style": "explainer", "orientation": orientation, "segments": list(segments)}
    if music is not None:
        body["music"] = music
    return body


def _edl(width=1920, height=1080, start=0.4, end=3.6):
    return {
        "frame": {"width": width, "height": height},
        "ranges": [{"source": "A", "start": start, "end": end}],
    }


WORDS = {"A": [
    {"start": 0.0, "end": 0.3, "text": "ừ"},
    {"start": 0.5, "end": 1.0, "text": "nhanh"},
    {"start": 1.0, "end": 1.4, "text": "hơn"},
    {"start": 1.4, "end": 1.9, "text": "40%"},
]}


def fields(errors):
    return [error.field for error in errors]


class StyleSchemaTests(unittest.TestCase):
    def test_committed_preset_passes(self):
        self.assertEqual(load_style()["id"], "explainer")

    def test_unknown_key_fails(self):
        data = json.loads((ROOT / "skills" / "style-explainer" / "style.json").read_text())
        data["sequence"] = ["stat", "list"]
        errors = validate_style(data)
        self.assertTrue(any(error.field == "sequence" for error in errors))


class OrientationTests(unittest.TestCase):
    def test_portrait_is_the_default(self):
        self.assertEqual(resolve_orientation("edit this")["orientation"], "portrait")
        self.assertEqual(resolve_orientation("edit this")["chrome"], "clean")

    def test_landscape_only_when_asked(self):
        self.assertEqual(resolve_orientation("make it 16:9")["orientation"], "landscape")
        self.assertEqual(resolve_orientation("landscape please")["orientation"], "landscape")
        self.assertEqual(resolve_orientation("YouTube widescreen")["orientation"], "landscape")

    def test_shorts_stays_portrait_with_platform_chrome(self):
        run = resolve_orientation("cut a TikTok")
        self.assertEqual(run["orientation"], "portrait")
        self.assertEqual(run["chrome"], "shorts")


class VisualPlanTests(unittest.TestCase):
    def test_comparison_on_a_percent_passes(self):
        errors = check_visual_plan(
            _plan(_segment(), music={"source": "library", "id": "measured"}),
            STYLE,
            _run(),
            _inventory("talking_head"),
            words_by_source=WORDS,
            edl=_edl(),
            manifest=MANIFEST,
            face_center_x=400,
        )
        self.assertEqual(fields(errors), [])

    def test_same_card_on_a_warning_fails_for_lack_of_a_datum(self):
        warning = _segment(
            quote="đừng đẩy secret lên git",
            intent="warning",
            why="The line is a warning, not a figure.",
        )
        errors = check_visual_plan(
            _plan(warning),
            STYLE,
            _run(),
            _inventory("talking_head"),
            edl=_edl(),
            manifest=MANIFEST,
        )
        self.assertIn("segments.s1.treatment.data", fields(errors))

    def test_warning_may_be_a_punch_in(self):
        warning = _segment(
            quote="đừng đẩy secret lên git",
            intent="warning",
            why="The face sells the warning. On-screen text is the word secret.",
            treatment={"layout": "clean", "motion": "punch-in", "text": "secret"},
        )
        errors = check_visual_plan(
            _plan(warning, music={"source": "library", "id": "tense"}),
            STYLE,
            _run(),
            _inventory("talking_head"),
            edl=_edl(),
            manifest=MANIFEST,
        )
        self.assertEqual(fields(errors), [])

    def test_repeated_treatment_fails(self):
        first = _segment()
        second = _segment(id="s2", start=5.0, end=8.0)
        errors = check_visual_plan(
            _plan(first, second),
            STYLE,
            _run(),
            _inventory("talking_head"),
            edl=_edl(),
            manifest=MANIFEST,
            face_center_x=400,
        )
        self.assertTrue(any(field.endswith("treatment") for field in fields(errors)))

    def test_cut_sfx_fails(self):
        segment = _segment()
        segment["treatment"]["sfx"] = "cut"
        errors = check_visual_plan(
            _plan(segment), STYLE, _run(), _inventory("talking_head"), manifest=MANIFEST,
        )
        self.assertIn("segments.s1.treatment.sfx", fields(errors))

    def test_cut_inside_a_word_fails(self):
        errors = check_visual_plan(
            _plan(_segment(), music={"source": "library", "id": "measured"}),
            STYLE,
            _run(),
            _inventory("talking_head"),
            words_by_source=WORDS,
            edl=_edl(start=0.1, end=3.6),
            manifest=MANIFEST,
            face_center_x=400,
        )
        self.assertIn("ranges[0].start", fields(errors))

    def test_library_bed_loses_to_a_folder_file(self):
        errors = check_visual_plan(
            _plan(_segment(), music={"source": "library", "id": "measured"}),
            STYLE,
            _run(),
            _inventory("talking_head", "music"),
            manifest=MANIFEST,
            face_center_x=400,
        )
        self.assertIn("music.source", fields(errors))

    def test_portrait_frame_rejects_a_landscape_edl(self):
        segment = _segment(treatment={
            "layout": "lower-card",
            "motion": "count-up",
            "data": {"type": "comparison", "before": "trước", "after": "40%"},
            "text": "40%",
        })
        errors = check_visual_plan(
            _plan(segment, music={"source": "library", "id": "measured"}, orientation="portrait"),
            STYLE,
            _run("portrait"),
            _inventory("talking_head"),
            edl=_edl(1920, 1080),
            manifest=MANIFEST,
        )
        self.assertIn("frame", fields(errors))

    def test_index_lists_only_this_skill(self):
        index = json.loads((ROOT / "skills" / "index.json").read_text())
        self.assertEqual(index["core"]["name"], "video-use")
        self.assertEqual([item["name"] for item in index["styles"]], ["style-explainer"])
        install = (ROOT / "install.md").read_text()
        self.assertIn("skills/style-explainer", install)


if __name__ == "__main__":
    unittest.main()
