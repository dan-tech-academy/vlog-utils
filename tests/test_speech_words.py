import importlib.util
import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).parents[1]
HELPERS = ROOT / "helpers"
sys.path.insert(0, str(HELPERS))

from speech.azure import credentials_present  # noqa: E402
from speech.base import (  # noqa: E402
    boundaries_to_words,
    cache_key,
    first_voice_with_words,
    join_chunk_words,
    synthesize_cached,
    text_to_ssml,
    voices_to_try,
    words_are_monotonic,
)
from speech.fake import FakeSynthesizer  # noqa: E402
import speak  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


captions = load("video_use_captions_speech", HELPERS / "captions.py")
transcribe = load("video_use_transcribe_speech", HELPERS / "transcribe.py")


class BoundaryTests(unittest.TestCase):
    def test_fixture_ticks_become_scribe_words(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "azure_word_boundary.json").read_text()
        )
        words = boundaries_to_words(fixture["events"])
        self.assertEqual(words, fixture["expected_words"])
        self.assertTrue(words_are_monotonic(words))
        shifted = boundaries_to_words(fixture["events"], time_offset=2.0)
        self.assertEqual(shifted[0]["start"], 2.5)
        self.assertEqual(shifted[1]["end"], 3.2)

    def test_later_sentence_is_offset_by_the_earlier_duration(self):
        first = [{"type": "word", "text": "Xin", "start": 0.0, "end": 0.4}]
        second = [{"type": "word", "text": "chào", "start": 0.1, "end": 0.5}]
        joined = join_chunk_words([first, second], [1.25, 0.8])
        self.assertEqual(joined[1]["start"], 1.35)
        self.assertTrue(words_are_monotonic(joined))

    def test_missing_boundaries_try_the_other_voice_then_fail(self):
        seen = []

        def once(voice):
            seen.append(voice)
            if voice == "vi-VN-Linh:MAI-Voice-2-Flash":
                return {"words": [{"type": "word", "text": "ok", "start": 0, "end": 0.2}]}
            return {"words": []}

        result = first_voice_with_words("vi-VN-NamMinhNeural", once)
        self.assertEqual(
            seen,
            [
                "vi-VN-NamMinhNeural",
                "vi-VN-HoaiMyNeural",
                "vi-VN-Linh:MAI-Voice-2-Flash",
            ],
        )
        self.assertEqual(result["voice"], "vi-VN-Linh:MAI-Voice-2-Flash")

        def empty(_voice):
            return {"words": []}

        with self.assertRaises(RuntimeError) as caught:
            first_voice_with_words("vi-VN-HoaiMyNeural", empty)
        message = str(caught.exception)
        self.assertIn("vi-VN-Linh:MAI-Voice-2-Flash", message)
        self.assertNotIn("Scribe", message)
        self.assertNotIn("Whisper", message)
        self.assertEqual(voices_to_try("en-US-AndrewNeural"), ["en-US-AndrewNeural"])

    def test_ssml_is_only_added_for_marked_english_tokens(self):
        self.assertIsNone(text_to_ssml("API của Azure", "vi"))
        ssml = text_to_ssml("Đây là {{en:Azure}} nhé.", "vi")
        self.assertIn('<lang xml:lang="en-US">Azure</lang>', ssml)
        self.assertIn('xml:lang="vi-VN"', ssml)


class CacheAndFakeTests(unittest.TestCase):
    def test_second_run_does_not_call_the_synthesizer(self):
        synth = FakeSynthesizer()
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            first = synthesize_cached(
                edit, "fake", "vi-VN-NamMinhNeural", "vi", "Xin chào", synth.synthesize
            )
            second = synthesize_cached(
                edit, "fake", "vi-VN-NamMinhNeural", "vi", "Xin chào", synth.synthesize
            )
            self.assertEqual(synth.calls, 1)
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            self.assertEqual(first["words"], second["words"])
            self.assertTrue(words_are_monotonic(first["words"]))
            self.assertTrue(first["audio"].read_bytes().startswith(b"RIFF"))

    def test_cache_key_changes_with_provider_voice_and_text(self):
        a = cache_key("azure", "vi-VN-NamMinhNeural", "vi", None, "Xin")
        b = cache_key("edge", "vi-VN-NamMinhNeural", "vi", None, "Xin")
        c = cache_key("azure", "vi-VN-NamMinhNeural", "vi", None, "Chào")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)

    def test_fake_words_feed_the_caption_writer(self):
        synth = FakeSynthesizer()
        result = synth.synthesize("Xin chào bạn", "vi-VN-NamMinhNeural", "vi")
        cues = captions.cues_from_words(result["words"], "sentence", "vi")
        self.assertEqual(len(cues), 1)
        self.assertIn("Xin chào", cues[0]["text"])

    def test_speak_cli_helper_writes_wav_and_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            edit = Path(tmp)
            out = edit / "audio" / "voice.wav"
            words = edit / "audio" / "voice.words.json"
            speak.speak(
                "Hello there",
                out,
                words,
                edit_dir=edit,
                provider="fake",
                voice="en-US-AndrewNeural",
                language="en",
                config={"tts": {"provider": "fake", "voices": {"en": "en-US-AndrewNeural"}}},
            )
            payload = json.loads(words.read_text())
            self.assertEqual([w["text"] for w in payload["words"]], ["Hello", "there"])
            self.assertTrue(out.is_file())
            self.assertTrue(out.read_bytes().startswith(b"RIFF"))


class ScribeTests(unittest.TestCase):
    def test_default_model_is_scribe_v2_and_overridable(self):
        previous = os.environ.pop("SCRIBE_MODEL_ID", None)
        try:
            self.assertEqual(transcribe.scribe_model_id(), "scribe_v2")
            os.environ["SCRIBE_MODEL_ID"] = "scribe_v1"
            self.assertEqual(transcribe.scribe_model_id(), "scribe_v1")
        finally:
            if previous is None:
                os.environ.pop("SCRIBE_MODEL_ID", None)
            else:
                os.environ["SCRIBE_MODEL_ID"] = previous

    def test_call_scribe_posts_word_fields(self):
        captured = {}

        class Response:
            status_code = 200

            def json(self):
                return {"words": []}

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            captured["url"] = url
            captured["data"] = data
            captured["header_names"] = sorted((headers or {}).keys())
            return Response()

        transcribe.requests.post = fake_post
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "a.wav"
            with wave.open(str(wav), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\x00\x01" * 160)
            os.environ.pop("SCRIBE_MODEL_ID", None)
            transcribe.call_scribe(wav, "super-secret-key", language="vi")
        self.assertEqual(captured["data"]["model_id"], "scribe_v2")
        self.assertEqual(captured["data"]["timestamps_granularity"], "word")
        self.assertEqual(captured["data"]["diarize"], "true")
        self.assertEqual(captured["data"]["tag_audio_events"], "true")
        self.assertNotIn("super-secret-key", json.dumps(captured["data"]))

    def test_silent_track_is_not_uploaded(self):
        uploaded = {"hit": False}

        def extract(_video, dest, audio_track=0):
            with wave.open(str(dest), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 1600)

        def boom(*_args, **_kwargs):
            uploaded["hit"] = True
            raise AssertionError("silent audio was uploaded")

        transcribe.extract_audio = extract
        transcribe.count_audio_tracks = lambda _path: 1
        transcribe.call_scribe = boom
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "take.mp4"
            video.write_bytes(b"placeholder")
            with self.assertRaises(RuntimeError) as caught:
                transcribe.transcribe_one(video, Path(tmp) / "edit", "key", verbose=False)
        self.assertIn("silent", str(caught.exception))
        self.assertFalse(uploaded["hit"])


class ProviderSurfaceTests(unittest.TestCase):
    def test_gemini_adapter_is_not_in_the_tree(self):
        speech = HELPERS / "speech"
        names = {path.name for path in speech.iterdir()}
        self.assertNotIn("gemini.py", names)
        for name in ("azure.py", "edge.py", "base.py", "fake.py"):
            text = (speech / name).read_text().lower()
            self.assertNotIn("speech-to-text", text)
            self.assertNotIn("import whisper", text)

    def test_committed_speech_config_is_azure_with_edge_fallback(self):
        config = json.loads((ROOT / "brand" / "speech.json").read_text())
        self.assertEqual(config["tts"]["provider"], "azure")
        self.assertEqual(config["tts"]["voices"]["vi"], "vi-VN-NamMinhNeural")
        self.assertEqual(config["tts"]["voices"]["en"], "en-US-AndrewNeural")
        self.assertEqual(config["tts"]["fallback"]["provider"], "edge")
        self.assertTrue(config["tts"]["fallback"]["dev_only"])
        self.assertEqual(config["stt"]["provider"], "scribe")
        self.assertFalse(credentials_present())


if __name__ == "__main__":
    unittest.main()
