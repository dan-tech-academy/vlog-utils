"""Fixture renders for the talking-head explainer. No Scribe, no face detector."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

from audio import MusicError, apply_music_policy, load_music_manifest  # noqa: E402
from check_visual_plan import check_visual_plan  # noqa: E402
from explainer_layout import card_rect, delivery  # noqa: E402
from render import crop_filter, render_edl  # noqa: E402
from style import load_style  # noqa: E402

STYLE = load_style()
MANIFEST = load_music_manifest(ROOT / "brand" / "music" / "manifest.json")
ARTIFACTS = Path("/opt/cursor/artifacts/explainer")


def write_video(path: Path, size: tuple[int, int], ellipse, seconds: float = 3.2) -> None:
    png = path.with_suffix(".png")
    image = Image.new("RGB", size, (17, 17, 17))
    if ellipse:
        cx, cy, rx, ry = ellipse
        ImageDraw.Draw(image).ellipse(
            (cx - rx, cy - ry, cx + rx, cy + ry),
            fill=(240, 196, 138),
        )
    image.save(png)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(png),
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}",
            "-t", f"{seconds}", "-r", "30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


def words_a():
    return [
        {"type": "word", "start": 0.00, "end": 0.28, "text": "ừ"},
        {"type": "word", "start": 0.50, "end": 0.95, "text": "nhanh"},
        {"type": "word", "start": 1.00, "end": 1.40, "text": "hơn"},
        {"type": "word", "start": 1.45, "end": 2.00, "text": "40%"},
    ]


def words_b():
    return [
        {"type": "word", "start": 0.50, "end": 0.90, "text": "đừng"},
        {"type": "word", "start": 0.95, "end": 1.30, "text": "đẩy"},
        {"type": "word", "start": 1.35, "end": 1.80, "text": "secret"},
        {"type": "word", "start": 1.85, "end": 2.20, "text": "lên"},
        {"type": "word", "start": 2.25, "end": 2.60, "text": "git"},
    ]


def probe(path: Path) -> dict:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height:format=duration",
            "-of", "json", str(path),
        ],
        text=True,
    )
    data = json.loads(out)
    stream = data["streams"][0]
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "duration": float(data["format"]["duration"]),
    }


def frame_at(video: Path, dest: Path, when: float = 1.6) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{when}", "-i", str(video), "-frames:v", "1", str(dest)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    return dest


def beige_count(path: Path) -> int:
    image = Image.open(path).convert("RGB")
    count = 0
    for pixel in image.getdata():
        red, green, blue = pixel
        if red > 170 and green > 120 and blue < 180 and red > blue + 30:
            count += 1
    return count


def region_hash(path: Path, box) -> int:
    image = Image.open(path).convert("RGB")
    crop = image.crop((int(box.x), int(box.y), int(box.x + box.w), int(box.y + box.h)))
    return hash(crop.tobytes())


class CropMathTests(unittest.TestCase):
    def test_static_crop_is_applied_before_scale(self):
        text = crop_filter({"x": 200, "y": 0, "w": 608, "h": 1080, "source": "look"})
        self.assertEqual(text, "crop=608:1080:200:0")

    def test_keyframes_move_x(self):
        text = crop_filter({
            "y": 0, "w": 608, "h": 1080,
            "keyframes": [{"t": 0, "x": 100}, {"t": 1, "x": 180}],
        })
        self.assertIn(r"\,", text)
        self.assertIn("180", text)


class MusicLibraryTests(unittest.TestCase):
    def test_explicit_id_survives_a_closed_theme_lock(self):
        edl = {
            "version": 2,
            "ranges": [{"source": "A", "start": 0.0, "end": 2.0, "role": "content"}],
            "audio": {"music": {"id": "tense"}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            resolved = apply_music_policy(
                edl, Path(tmp), {"enabled": False}, MANIFEST,
                ROOT / "brand" / "music", 2.0,
            )
        self.assertEqual(resolved["audio"]["music"]["id"], "tense")
        self.assertTrue(resolved["audio"]["music"]["requested_file"].endswith("tense.wav"))

    def test_folder_file_wins_over_a_library_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            bed = folder / "room.wav"
            bed.write_bytes((ROOT / "brand" / "music" / "light.wav").read_bytes())
            edl = {
                "version": 2,
                "ranges": [{"source": "A", "start": 0.0, "end": 2.0, "role": "content"}],
                "audio": {"music": {"file": str(bed), "picked_from": "folder"}},
            }
            resolved = apply_music_policy(
                edl, folder, {"enabled": False}, MANIFEST,
                ROOT / "brand" / "music", 2.0,
            )
        self.assertEqual(resolved["audio"]["music"]["requested_file"], str(bed))
        self.assertNotIn("id", resolved["audio"]["music"])

    def test_empty_license_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({
                "enabled": True,
                "beds": [{"id": "bare", "file": "bare.wav", "vocals": False, "license": ""}],
            }))
            with self.assertRaises(MusicError) as caught:
                load_music_manifest(path)
        self.assertIn("license", str(caught.exception))


class ExplainerRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.tmp.name)
        cls.wide = cls.folder / "wide.mp4"
        cls.tall = cls.folder / "tall.mp4"
        cls.plain = cls.folder / "plain.mp4"
        write_video(cls.wide, (1920, 1080), (480, 320, 90, 120))
        write_video(cls.tall, (1080, 1920), (540, 700, 180, 260))
        write_video(cls.plain, (1920, 1080), None)
        ARTIFACTS.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _edit(self, name, source, transcript, plan, run, crop):
        edit = self.folder / name
        edit.mkdir()
        (edit / "transcripts").mkdir()
        (edit / "transcripts" / "A.json").write_text(json.dumps({"words": transcript}))
        (edit / "style-run.json").write_text(json.dumps(run))
        (edit / "visual_plan.json").write_text(json.dumps(plan))
        start, end = 0.40, 3.20
        edl = {
            "version": 1,
            "sources": {"A": str(source)},
            "ranges": [{
                "source": "A",
                "start": start,
                "end": end,
                "quote": plan["segments"][0]["quote"],
                "crop": crop,
            }],
            "total_duration_s": round(end - start, 3),
            "frame": {
                "width": 1920 if run["orientation"] == "landscape" else 1080,
                "height": 1080 if run["orientation"] == "landscape" else 1920,
            },
        }
        (edit / "edl.json").write_text(json.dumps(edl))
        return edit, edl

    def _render(self, edit, edl, loudnorm=True):
        out = edit / "final.mp4"
        render_edl(
            edl, edit, out,
            build_subtitles=True,
            no_loudnorm=not loudnorm,
        )
        return out

    def test_portrait_and_landscape_and_the_two_transcripts(self):
        look = {
            "x": 200, "y": 0, "w": 608, "h": 1080,
            "source": "look", "why": "Face sits left of center on the filmstrip.",
        }
        center = {
            "x": 656, "y": 0, "w": 608, "h": 1080,
            "source": "center", "why": "No face on the filmstrip.",
        }
        segment_a = {
            "id": "s1",
            "start": 0.2,
            "end": 2.6,
            "quote": "nhanh hơn 40%",
            "intent": "comparison",
            "why": "The line contrasts speed and states a percent. Setup is trước.",
            "face_center_x": 480,
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
        portrait_a = json.loads(json.dumps(segment_a))
        portrait_a["treatment"]["layout"] = "lower-card"
        segment_b = {
            "id": "s1",
            "start": 0.2,
            "end": 2.6,
            "quote": "đừng đẩy secret lên git",
            "intent": "warning",
            "why": "The face carries the warning. The word on screen is secret.",
            "treatment": {"layout": "clean", "motion": "punch-in", "text": "secret"},
        }
        inventory = {"files": [{"path": "wide.mp4", "role": "talking_head"}]}
        plan_land = {
            "style": "explainer", "orientation": "landscape",
            "music": {"source": "library", "id": "measured"},
            "segments": [segment_a],
        }
        plan_port = {
            "style": "explainer", "orientation": "portrait",
            "music": {"source": "library", "id": "measured"},
            "segments": [portrait_a],
        }
        plan_warn = {
            "style": "explainer", "orientation": "landscape",
            "music": {"source": "library", "id": "tense"},
            "segments": [segment_b],
        }
        self.assertEqual(check_visual_plan(
            plan_land, STYLE, {"orientation": "landscape", "chrome": "clean"},
            inventory, edl={"frame": {"width": 1920, "height": 1080}, "ranges": [{"source": "A", "start": 0.4, "end": 3.2}]},
            words_by_source={"A": words_a()}, manifest=MANIFEST, face_center_x=480,
        ), [])
        self.assertEqual(check_visual_plan(
            plan_warn, STYLE, {"orientation": "landscape", "chrome": "clean"},
            inventory, edl={"frame": {"width": 1920, "height": 1080}, "ranges": [{"source": "A", "start": 0.4, "end": 3.2}]},
            words_by_source={"A": words_b()}, manifest=MANIFEST,
        ), [])
        self.assertNotEqual(
            segment_a["treatment"]["layout"],
            segment_b["treatment"]["layout"],
        )

        land_edit, land_edl = self._edit(
            "land", self.wide, words_a(), plan_land,
            {"style": "explainer", "orientation": "landscape", "chrome": "clean"},
            None,
        )
        port_edit, port_edl = self._edit(
            "port", self.wide, words_a(), plan_port,
            {"style": "explainer", "orientation": "portrait", "chrome": "clean"},
            look,
        )
        warn_edit, warn_edl = self._edit(
            "warn", self.wide, words_b(), plan_warn,
            {"style": "explainer", "orientation": "landscape", "chrome": "clean"},
            None,
        )
        tall_plan = {
            "style": "explainer", "orientation": "portrait",
            "music": {"source": "library", "id": "light"},
            "segments": [{
                "id": "s1", "start": 0.2, "end": 2.6,
                "quote": "xin chào", "intent": "story",
                "why": "A greeting. The face is the picture.",
                "treatment": {"layout": "clean"},
            }],
        }
        tall_edit, tall_edl = self._edit(
            "tall", self.tall, [{"type": "word", "start": 0.5, "end": 1.2, "text": "xin"},
                                {"type": "word", "start": 1.3, "end": 2.0, "text": "chào"}],
            tall_plan,
            {"style": "explainer", "orientation": "portrait", "chrome": "clean"},
            None,
        )
        plain_edit, plain_edl = self._edit(
            "plain", self.plain, words_a(), plan_port,
            {"style": "explainer", "orientation": "portrait", "chrome": "clean"},
            center,
        )

        land = self._render(land_edit, land_edl)
        port = self._render(port_edit, port_edl)
        warn = self._render(warn_edit, warn_edl, loudnorm=False)
        tall = self._render(tall_edit, tall_edl, loudnorm=False)
        plain = self._render(plain_edit, plain_edl, loudnorm=False)

        land_probe = probe(land)
        self.assertEqual((land_probe["width"], land_probe["height"]), (1920, 1080))
        self.assertAlmostEqual(land_probe["duration"], 2.8, delta=0.1)
        port_probe = probe(port)
        self.assertEqual((port_probe["width"], port_probe["height"]), (1080, 1920))
        ass = (port_edit / "master.ass").read_text()
        self.assertIn("hơn", ass)
        self.assertIn("40%", ass)
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn(",220,1", ass)
        resolved = json.loads((port_edit / "edl.resolved.json").read_text())
        self.assertEqual(resolved["audio"]["music"]["id"], "measured")
        self.assertTrue(resolved["audio"]["music"]["requested_file"].endswith("measured.wav"))
        kinds = [item.get("kind") for item in resolved["audio"].get("events") or []]
        self.assertNotIn("cut", kinds)
        self.assertIn("reveal", kinds)
        reframe = json.loads((port_edit / "reframe.json").read_text())
        self.assertEqual(reframe["ranges"][0]["crop"]["source"], "look")
        self.assertEqual(reframe["ranges"][0]["crop"]["x"], 200)
        tall_reframe = json.loads((tall_edit / "reframe.json").read_text())
        self.assertIsNone(tall_reframe["ranges"][0]["crop"])
        plain_reframe = json.loads((plain_edit / "reframe.json").read_text())
        self.assertEqual(plain_reframe["ranges"][0]["crop"]["source"], "center")
        plain_note = (plain_edit / "project.md").read_text().lower()
        self.assertIn("no face", plain_note)
        self.assertIn("centered", plain_note)
        warn_reframe = json.loads((warn_edit / "reframe.json").read_text())
        self.assertGreaterEqual(warn_reframe["ranges"][0]["crop"]["zoom"], 1.15)

        land_png = frame_at(land, ARTIFACTS / "landscape-a.png")
        warn_png = frame_at(warn, ARTIFACTS / "landscape-b.png")
        port_png = frame_at(port, ARTIFACTS / "portrait-a.png")
        tall_png = frame_at(tall, ARTIFACTS / "portrait-native.png")
        plain_png = frame_at(plain, self.folder / "plain-frame.png")

        box = delivery(STYLE, "landscape", "clean")
        card = card_rect(box, "side-card", face_center_x=480)
        self.assertGreater(beige_count(port_png), 200)
        self.assertLess(beige_count(plain_png), 50)
        self.assertNotEqual(region_hash(land_png, card), region_hash(warn_png, card))
        port_box = delivery(STYLE, "portrait", "clean")
        port_card = card_rect(port_box, "lower-card")
        self.assertGreaterEqual(port_card.y, 960)
        self.assertLess(port_card.y + port_card.h, port_box["height"] - 220)
        portrait = Image.open(port_png).convert("RGB")
        sample = portrait.getpixel((int(port_card.x + 8), int(port_card.y + 40)))
        self.assertGreater(sample[1], sample[2])


if __name__ == "__main__":
    unittest.main()
