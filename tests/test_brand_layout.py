import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
HELPERS = ROOT / "helpers"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


brand = load("video_use_brand", HELPERS / "brand.py")
theme_mod = load("video_use_theme_brand", HELPERS / "theme.py")
render = load("video_use_render_brand", HELPERS / "render.py")


class LayoutTests(unittest.TestCase):
    def test_lower_third_clears_captions_in_both_orientations(self):
        for width, height in ((1920, 1080), (1080, 1920)):
            boxes = brand.layout_boxes(width, height, margin_v=90)
            self.assertFalse(
                boxes["caption"].intersects(boxes["lower_third"]),
                (width, height, boxes["caption"].as_tuple(), boxes["lower_third"].as_tuple()),
            )
            self.assertGreaterEqual(boxes["lower_third"].y, 0)
            self.assertLess(boxes["lower_third"].y + boxes["lower_third"].h, boxes["caption"].y)

    def test_disabled_brand_keeps_ranges(self):
        loaded = theme_mod.load_theme(None)
        edl = {"ranges": [{"source": "A", "start": 0, "end": 4}]}
        resolved = brand.with_brand_ranges(edl, loaded)
        self.assertEqual(resolved["ranges"], edl["ranges"])
        self.assertIsNone(brand.require_logo(loaded))

    def test_intro_shifts_content_caption_offset(self):
        loaded = theme_mod.load_theme(None)
        themed = copy.copy(loaded)
        themed.intro = {"enabled": True, "duration_s": 2.5}
        themed.outro = {"enabled": True, "duration_s": 3.5}
        themed.watermark = {"enabled": False, "file": "brand/logo.png"}
        edl = {"ranges": [{"source": "PLATE", "start": 1.0, "end": 5.0, "role": "content"}]}
        resolved = brand.with_brand_ranges(edl, themed)
        self.assertEqual(resolved["ranges"][0]["source"], "INTRO")
        self.assertEqual(resolved["ranges"][-1]["role"], "outro")
        offset = brand.content_segment_offset(resolved["ranges"])
        self.assertEqual(offset, 2.5)
        # Word at the content in-point lands intro_duration later on the output.
        self.assertEqual(brand.output_caption_time(1.0, 1.0, offset), 2.5)

    def test_missing_logo_names_the_path(self):
        loaded = theme_mod.load_theme(None)
        themed = copy.copy(loaded)
        themed.watermark = {"enabled": True, "file": "brand/logo.png"}
        themed.intro = {"enabled": False}
        with self.assertRaises(brand.BrandError) as caught:
            brand.require_logo(themed)
        self.assertIn("brand/logo.png", str(caught.exception))

    def test_watermark_is_under_the_subtitle_filter(self):
        loaded = theme_mod.load_theme(None)
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            subs = edit / "master.ass"
            subs.write_text(
                "[Script Info]\nPlayResX: 1920\nPlayResY: 1080\n"
                "[V4+ Styles]\nFormat: Name\nStyle: bold-overlay\n"
                "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            )
            logo = edit / "logo.png"
            logo.write_bytes(b"not-a-real-png")
            _inputs, graph, label = render.picture_filter_graph(
                [{"file": "card.mp4", "start_in_output": 0.0, "duration": 2.0}],
                subs,
                edit,
                style_id="bold-overlay",
                fontsdir=loaded.font("body").file.parent,
                watermark={"file": str(logo), "x": 1724, "y": 36},
            )
        pieces = graph.split(";")
        self.assertEqual(label, "[outv]")
        self.assertIn("subtitles=", pieces[-1])
        self.assertNotIn("force_style", pieces[-1])
        self.assertTrue(any("overlay=" in piece and "[wm]" in piece for piece in pieces))
        self.assertLess(graph.find("[wm]"), graph.rfind("subtitles="))

    def test_composite_stops_at_the_base_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            base = edit / "base.mp4"
            base.write_bytes(b"x")
            (edit / "card.mp4").write_bytes(b"x")
            with patch.object(render, "_probe_duration", return_value=2.4), patch.object(
                render.subprocess, "run"
            ) as run:
                render.build_final_composite(
                    base,
                    [{"file": "card.mp4", "start_in_output": 1.5, "duration": 3.0}],
                    None,
                    edit / "out.mp4",
                    edit,
                )
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("-t") + 1], "2.400")


if __name__ == "__main__":
    unittest.main()
