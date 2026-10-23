import importlib.util
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


captions = load("video_use_captions", ROOT / "helpers" / "captions.py")
theme_mod = load("video_use_theme_captions", ROOT / "helpers" / "theme.py")
render = load("video_use_render_captions_ass", ROOT / "helpers" / "render.py")


def word(text, start, end):
    return {"type": "word", "text": text, "start": start, "end": end}


class CaseAndChunkTests(unittest.TestCase):
    def test_bold_overlay_matches_the_english_chunker_and_is_uppercase(self):
        words = [
            word("90%", 0.1, 0.4),
            word("of", 0.42, 0.5),
            word("what", 0.55, 0.7),
            word("a", 0.72, 0.8),
        ]
        bold = captions.cues_from_words(words, "bold-overlay", "en")
        paired = render.chunk_words(words)
        self.assertEqual(
            [cue["text"] for cue in bold],
            [" ".join(w["text"] for w in chunk).upper() for chunk in paired],
        )
        self.assertTrue(all(cue["text"] == cue["text"].upper() for cue in bold))

    def test_vietnamese_uppercase_covers_d(self):
        self.assertEqual(captions.apply_case("đường", "bold-overlay"), "ĐƯỜNG")
        self.assertEqual(captions.apply_case("đường", "sentence"), "đường")

    def test_sentence_keeps_a_two_syllable_word_together(self):
        # Gaps are short and each token is long enough that the English
        # 2-word chunker closes "xem công" before "nghệ".
        tokens = ["xem", "công", "nghệ", "mới"]
        words = []
        t = 0.0
        for token in tokens:
            words.append(word(token, t, t + 0.4))
            t += 0.45
        bold_texts = [" ".join(w["text"] for w in c) for c in render.chunk_words(words)]
        self.assertTrue(any(part == "xem công" for part in bold_texts))
        self.assertFalse(any("công nghệ" in part for part in bold_texts))
        cues = captions.cues_from_words(words, "sentence", "vi")
        self.assertEqual(len(cues), 1)
        self.assertIn("công nghệ", cues[0]["text"])

    def test_vi_without_a_style_selects_sentence(self):
        loaded = theme_mod.load_theme(None)
        self.assertEqual(
            render.resolve_caption_style({"language": "vi"}, loaded),
            "sentence",
        )
        self.assertEqual(render.resolve_caption_style({}, loaded), "bold-overlay")


class KaraokeAndAssTests(unittest.TestCase):
    def test_kf_centiseconds_rounds_from_seconds(self):
        self.assertEqual(captions.kf_centiseconds(0.4), 40)
        self.assertEqual(captions.kf_centiseconds(1), 100)
        self.assertEqual(captions.kf_centiseconds(0.255), 26)

    def test_ass_file_pins_playres_and_karaoke_tag(self):
        loaded = theme_mod.load_theme(None)
        words = [word("Xin", 0.0, 0.4), word("chào", 0.4, 0.9)]
        cues = captions.cues_from_words(words, "karaoke", "vi")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "master.ass"
            captions.write_ass(cues, path, loaded, "karaoke")
            text = path.read_text()
        self.assertIn("PlayResX: 1920", text)
        self.assertIn("PlayResY: 1080", text)
        self.assertIn(r"{\kf40}", text)
        self.assertIn(r"{\kf50}", text)
        self.assertNotIn("force_style", text)

    def test_ass_filter_has_fontsdir_and_srt_filter_has_force_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ass = root / "master.ass"
            srt = root / "master.srt"
            ass.write_text("")
            srt.write_text("")
            fonts = root / "fonts"
            fonts.mkdir()
            ass_filter = captions.subtitle_filter(ass, fontsdir=fonts)
            srt_filter = captions.subtitle_filter(
                srt, force_style=render.SUB_FORCE_STYLE
            )
        self.assertIn("fontsdir=", ass_filter)
        self.assertNotIn("force_style", ass_filter)
        self.assertIn("force_style=", srt_filter)
        self.assertIn("MarginV=90", srt_filter)
        self.assertNotIn("fontsdir", srt_filter)


if __name__ == "__main__":
    unittest.main()
