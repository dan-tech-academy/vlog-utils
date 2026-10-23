"""Synthesize narration to a WAV plus a Scribe-shaped word list.

    python helpers/speak.py --text-file script.txt --out edit/audio/voice.wav \\
        --words edit/audio/voice.words.json

``--provider fake`` is the offline test double. The publish provider is Azure.
edge-tts runs when ``AZURE_SPEECH_KEY`` is absent. Gemini is not a provider.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_HELPERS = Path(__file__).resolve().parent
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))

from speech.base import synthesize_cached  # noqa: E402
from speech.fake import FakeSynthesizer  # noqa: E402


REPO = Path(__file__).resolve().parents[1]


def load_speech_config(edit_dir: Path | None = None) -> dict:
    if edit_dir is not None:
        override = Path(edit_dir) / "speech.json"
        if override.is_file():
            return json.loads(override.read_text())
    path = REPO / "brand" / "speech.json"
    if not path.is_file():
        path = REPO / "brand" / "speech.example.json"
    return json.loads(path.read_text())


def voice_for(config: dict, language: str) -> str:
    voices = config["tts"]["voices"]
    if language in voices:
        return voices[language]
    short = language.split("-")[0]
    if short in voices:
        return voices[short]
    raise SystemExit(f"no voice configured for language {language}")


def build_synthesizer(provider: str, config: dict):
    """Return ``(cache provider name, synthesizer)``."""
    if provider == "fake":
        return "fake", FakeSynthesizer()
    if provider == "gemini":
        raise SystemExit("Gemini TTS is not built. The provider interface is azure or edge.")
    if provider == "edge":
        from speech.edge import EdgeSynthesizer

        return "edge", EdgeSynthesizer()
    if provider == "azure":
        from speech.azure import credentials_present

        if credentials_present():
            from speech.azure import AzureSynthesizer

            return "azure", AzureSynthesizer()
        fallback = (config.get("tts") or {}).get("fallback") or {}
        if fallback.get("provider") == "edge":
            print(
                "AZURE_SPEECH_KEY absent; using edge-tts dev fallback",
                file=sys.stderr,
            )
            from speech.edge import EdgeSynthesizer

            return "edge", EdgeSynthesizer()
        raise SystemExit(
            "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION not found in .env or environment"
        )
    raise SystemExit(f"unknown tts provider '{provider}'")


def speak(
    text: str,
    out: Path,
    words_path: Path,
    *,
    edit_dir: Path,
    provider: str,
    voice: str,
    language: str,
    config: dict | None = None,
) -> dict:
    config = config if config is not None else load_speech_config(edit_dir)
    cache_provider, synth = build_synthesizer(provider, config)
    result = synthesize_cached(
        edit_dir,
        cache_provider,
        voice,
        language,
        text,
        synth.synthesize,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    words_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(result["audio"]).resolve() != out.resolve():
        shutil.copyfile(result["audio"], out)
    words_path.write_text(
        json.dumps({"words": result["words"]}, ensure_ascii=False, indent=2)
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize narration")
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--text", default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--words", type=Path, required=True)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--voice", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument("--edit-dir", type=Path, default=None)
    args = parser.parse_args()
    if args.text is None and args.text_file is None:
        raise SystemExit("pass --text or --text-file")
    text = args.text if args.text is not None else args.text_file.read_text()
    edit_dir = args.edit_dir or args.out.parent
    config = load_speech_config(edit_dir)
    language = args.language or config["tts"]["language"]
    voice = args.voice or voice_for(config, language)
    provider = args.provider or config["tts"]["provider"]
    result = speak(
        text,
        args.out,
        args.words,
        edit_dir=edit_dir,
        provider=provider,
        voice=voice,
        language=language,
        config=config,
    )
    print(f"voice → {args.out} ({len(result['words'])} words, provider {provider})")


if __name__ == "__main__":
    main()
