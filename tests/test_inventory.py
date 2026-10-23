"""Inventory roles from canned probes. No network, no Scribe."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "helpers"))

from inventory import (  # noqa: E402
    apply_look,
    build_inventory,
    roles_present,
    speech_ratio,
)


def _words(spans):
    return [{"start": a, "end": b, "text": "x"} for a, b in spans]


class SpeechRatioTests(unittest.TestCase):
    def test_overlap_is_merged(self):
        ratio = speech_ratio(_words([(0.0, 2.0), (1.0, 3.0)]), 10.0)
        self.assertAlmostEqual(ratio, 0.3)


class InventoryTests(unittest.TestCase):
    def test_roles_match_the_explainer_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "music").mkdir()
            (folder / "sfx").mkdir()
            (folder / "talk.mp4").write_bytes(b"video")
            (folder / "music" / "bed.wav").write_bytes(b"music")
            (folder / "shot.png").write_bytes(b"png")
            (folder / "sfx" / "hit.wav").write_bytes(b"sfx")
            (folder / "edit").mkdir()
            (folder / "edit" / "notes.txt").write_text("skip")
            (folder / ".hidden.mp4").write_bytes(b"nope")
            probes = {
                "talk.mp4": {
                    "kind": "video", "duration_s": 8.0,
                    "width": 1920, "height": 1080, "fps": 30, "has_audio": True,
                },
                "music/bed.wav": {"kind": "audio", "duration_s": 30.0, "has_audio": True},
                "shot.png": {"kind": "image", "duration_s": 0, "has_audio": False},
                "sfx/hit.wav": {"kind": "audio", "duration_s": 0.4, "has_audio": True},
            }
            transcripts = {
                "talk.mp4": {"path": "edit/transcripts/talk.json", "words": _words([(0.0, 6.0)])},
            }
            inventory = build_inventory(folder, probes=probes, transcripts=transcripts)
        by_path = {entry["path"]: entry for entry in inventory["files"]}
        self.assertEqual(set(by_path), {"talk.mp4", "music/bed.wav", "shot.png", "sfx/hit.wav"})
        self.assertEqual(by_path["talk.mp4"]["role"], "talking_head")
        self.assertEqual(by_path["talk.mp4"]["source"], "scribe")
        self.assertAlmostEqual(by_path["talk.mp4"]["speech_ratio"], 0.75)
        self.assertEqual(by_path["music/bed.wav"]["role"], "music")
        self.assertEqual(by_path["music/bed.wav"]["source"], "folder")
        self.assertEqual(by_path["shot.png"]["role"], "photo")
        self.assertEqual(by_path["sfx/hit.wav"]["role"], "sfx")
        self.assertNotIn("music", {by_path["talk.mp4"]["role"], by_path["shot.png"]["role"]})

    def test_missing_music_file_does_not_invent_a_music_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "talk.mp4").write_bytes(b"video")
            probes = {
                "talk.mp4": {
                    "kind": "video", "duration_s": 4.0,
                    "width": 1920, "height": 1080, "fps": 30, "has_audio": True,
                },
            }
            transcripts = {"talk.mp4": {"words": _words([(0.0, 3.0)])}}
            inventory = build_inventory(folder, probes=probes, transcripts=transcripts)
        self.assertEqual(roles_present(inventory), {"talking_head"})

    def test_screen_folder_is_broll_and_quiet_video_is_broll(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "screen").mkdir()
            (folder / "screen" / "code.mp4").write_bytes(b"v")
            (folder / "room.mp4").write_bytes(b"v")
            probes = {
                "screen/code.mp4": {
                    "kind": "video", "duration_s": 5, "width": 1920, "height": 1080,
                    "fps": 30, "has_audio": True,
                },
                "room.mp4": {
                    "kind": "video", "duration_s": 5, "width": 1920, "height": 1080,
                    "fps": 30, "has_audio": True,
                },
            }
            transcripts = {
                "room.mp4": {"words": _words([(0.0, 0.2)])},
            }
            inventory = build_inventory(folder, probes=probes, transcripts=transcripts)
        by_path = {entry["path"]: entry for entry in inventory["files"]}
        self.assertEqual(by_path["screen/code.mp4"]["role"], "broll")
        self.assertEqual(by_path["screen/code.mp4"]["source"], "folder")
        self.assertFalse(by_path["screen/code.mp4"]["needs_transcript"])
        self.assertEqual(by_path["room.mp4"]["role"], "broll")
        self.assertEqual(by_path["room.mp4"]["source"], "scribe")

    def test_mid_ratio_stays_ambiguous_until_a_look(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "maybe.mp4").write_bytes(b"v")
            probes = {
                "maybe.mp4": {
                    "kind": "video", "duration_s": 10, "width": 1920, "height": 1080,
                    "fps": 30, "has_audio": True,
                },
            }
            transcripts = {"maybe.mp4": {"words": _words([(0.0, 3.0)])}}
            inventory = build_inventory(folder, probes=probes, transcripts=transcripts)
        self.assertEqual(inventory["files"][0]["role"], "ambiguous")
        apply_look(inventory, "maybe.mp4", "talking_head")
        self.assertEqual(inventory["files"][0]["role"], "talking_head")
        self.assertEqual(inventory["files"][0]["source"], "look")

    def test_video_without_a_transcript_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "talk.mp4").write_bytes(b"v")
            probes = {
                "talk.mp4": {
                    "kind": "video", "duration_s": 8, "width": 1920, "height": 1080,
                    "fps": 30, "has_audio": True,
                },
            }
            inventory = build_inventory(folder, probes=probes)
        entry = inventory["files"][0]
        self.assertIsNone(entry["role"])
        self.assertTrue(entry["needs_transcript"])
        self.assertNotIn("talking_head", roles_present(inventory))


if __name__ == "__main__":
    unittest.main()
