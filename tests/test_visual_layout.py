import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

from visuals.layout import fit_text, safe_rect  # noqa: E402
from visuals.render_slot import render_template, stat_glyph_box  # noqa: E402
from visuals.select import CATALOG  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


theme_mod = load("theme_visual", ROOT / "helpers" / "theme.py")


def probe(path: Path) -> tuple[int, int, float]:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1",
        str(path),
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    values = {}
    for line in out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return int(values["width"]), int(values["height"]), float(values["duration"])


class LayoutTests(unittest.TestCase):
    def test_stat_glyph_sits_inside_the_safe_rect(self):
        loaded = theme_mod.load_theme(None)
        report = stat_glyph_box(loaded, "40%")
        self.assertTrue(report["inside"])
        safe = safe_rect(loaded.frame_width, loaded.frame_height, loaded.margin_v)
        self.assertGreater(safe.w, 400)
        self.assertGreater(safe.h, 200)

    def test_a_line_that_cannot_fit_is_marked(self):
        loaded = theme_mod.load_theme(None)
        long_line = "công nghệ " * 40
        fitted = fit_text(long_line, loaded.font("body").file, 320, 64, 28)
        self.assertEqual(fitted["fallback"], "kinetic")
        self.assertLessEqual(fitted["width"], 320)

    def test_every_template_renders_a_silent_frame_at_theme_size(self):
        loaded = theme_mod.load_theme(None)
        fps = 8
        duration = 1.0
        params = {
            "kinetic": {"text": "Một ý"},
            "section": {"label": "HOOK"},
            "stat": {"value": "40%", "label": "ít chờ"},
            "list": {"items": ["một", "hai", "ba"]},
            "comparison": {"left": "cũ", "right": "mới"},
            "code": {"text": "npm test"},
            "question": {"text": "Vì sao?"},
            "quote": {"text": "Ship it", "attribution": "Dan Tech"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for template in sorted(CATALOG):
                path = folder / f"{template}.mp4"
                render_template(
                    template, params[template], loaded,
                    (loaded.frame_width, loaded.frame_height),
                    fps, duration, path,
                )
                width, height, got = probe(path)
                self.assertEqual((width, height), (1920, 1080), template)
                self.assertLessEqual(abs(got - duration), 1.0 / fps + 0.05, template)


if __name__ == "__main__":
    unittest.main()
