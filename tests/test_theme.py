import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


theme = load("video_use_theme", ROOT / "helpers" / "theme.py")
render = load("video_use_render_theme", ROOT / "helpers" / "render.py")


class LoadThemeTests(unittest.TestCase):
    def test_repo_theme_exposes_tokens(self):
        loaded = theme.load_theme(None)
        self.assertEqual(loaded.source, "repo")
        self.assertTrue(loaded.placeholders)
        self.assertEqual(loaded.channel_name, "Dan Tech")
        self.assertEqual(loaded.handle, "@dantech0xff")
        self.assertEqual(loaded.handles, ("@dantech0xff", "@dantech-0xff"))
        self.assertEqual(loaded.background, "#0B0F14")
        self.assertEqual(loaded.surface, "#141A22")
        self.assertEqual(loaded.text, "#F4F7FB")
        self.assertEqual(loaded.text_muted, "#9AA6B2")
        self.assertEqual(loaded.accent, "#3EE0B0")
        self.assertEqual(loaded.accent_alt, "#7AA2FF")
        self.assertEqual(loaded.margin_v, 90)
        self.assertEqual((loaded.frame_width, loaded.frame_height), (1920, 1080))
        self.assertEqual(loaded.fps, 30)
        self.assertEqual(loaded.frame_mode, "source")
        for role in ("display", "body", "mono"):
            self.assertTrue(loaded.font(role).file.is_file(), role)
        self.assertFalse(loaded.watermark.get("enabled"))
        self.assertFalse(loaded.intro.get("enabled"))
        self.assertFalse(loaded.music.get("enabled"))

    def test_edit_file_replaces_the_repo_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            override = json.loads((ROOT / "brand" / "theme.json").read_text())
            override["colors"]["accent"] = "#112233"
            override["captions"]["default"] = "sentence"
            override["meta"]["placeholders"] = False
            # A key that exists only on the repo file must not leak back in.
            del override["music"]
            (edit / "theme.json").write_text(json.dumps(override))
            candidates = theme.theme_candidates(edit)
            self.assertEqual(candidates, [("edit", edit / "theme.json")])
            loaded = theme.load_theme(edit)
            self.assertEqual(loaded.source, "edit")
            self.assertEqual(loaded.accent, "#112233")
            self.assertEqual(loaded.captions_default, "sentence")
            self.assertFalse(loaded.placeholders)
            self.assertEqual(loaded.music, {})
            self.assertNotEqual(loaded.accent, theme.load_theme(None).accent)

    def test_missing_font_names_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "theme.json"
            data = json.loads((ROOT / "brand" / "theme.json").read_text())
            data["fonts"]["body"]["file"] = "brand/fonts/does-not-exist.ttf"
            path.write_text(json.dumps(data))
            with self.assertRaises(theme.ThemeError) as caught:
                theme.load_theme_file(path)
            self.assertIn("does-not-exist.ttf", str(caught.exception))

    def test_missing_color_key_names_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "theme.json"
            data = json.loads((ROOT / "brand" / "theme.json").read_text())
            del data["colors"]["accent"]
            path.write_text(json.dumps(data))
            with self.assertRaises(theme.ThemeError) as caught:
                theme.load_theme_file(path)
            self.assertIn("colors.accent", str(caught.exception))
            self.assertIn(str(path), str(caught.exception))


class CaptionStyleTests(unittest.TestCase):
    def test_edl_without_captions_keeps_bold_overlay_force_style(self):
        loaded = theme.load_theme(None)
        style = render.resolve_caption_style({}, loaded)
        self.assertEqual(style, "bold-overlay")
        self.assertEqual(render.force_style_for(style), render.SUB_FORCE_STYLE)
        self.assertIn("MarginV=90", render.SUB_FORCE_STYLE)
        self.assertIn("FontName=Helvetica", render.SUB_FORCE_STYLE)

    def test_unknown_style_is_an_error(self):
        loaded = theme.load_theme(None)
        with self.assertRaises(SystemExit) as caught:
            render.resolve_caption_style({"captions": {"style": "comic-sans"}}, loaded)
        self.assertIn("comic-sans", str(caught.exception))


class FrameScaleTests(unittest.TestCase):
    def test_source_mode_preserves_orientation_scale(self):
        self.assertEqual(
            render.scale_filter_for(False, False, "source", 1920, 1080),
            "scale=1920:-2",
        )
        self.assertEqual(
            render.scale_filter_for(True, False, "source", 1920, 1080),
            "scale=-2:1920",
        )

    def test_force_mode_pads_to_the_theme_frame(self):
        scale = render.scale_filter_for(False, False, "force", 1920, 1080)
        self.assertIn("scale=1920:1080", scale)
        self.assertIn("pad=1920:1080", scale)


if __name__ == "__main__":
    unittest.main()
