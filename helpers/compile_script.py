"""Compile a script into a version-2 EDL, then render it.

A folder of camera files stays on the inventory path. This tool is only for a
folder that has ``script.json`` and no camera media.

    python helpers/compile_script.py script.json --edit-dir edit --plan
    python helpers/compile_script.py script.json --edit-dir edit --provider fake

``--plan`` prints the voice, each template id, the SFX kinds, and the music id.
It does not call ffmpeg or a speech API.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_HELPERS = Path(__file__).resolve().parent
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))

from audio import events_from_ranges  # noqa: E402
from brand import with_brand_ranges  # noqa: E402
from speak import build_synthesizer, load_speech_config, voice_for  # noqa: E402
from speech.base import synthesize_cached  # noqa: E402
from theme import load_theme  # noqa: E402
from visuals.select import UnknownVisual, assign_phrases, select_visual  # noqa: E402


def spoken_tokens(text: str) -> list[str]:
    cleaned = (text or "").replace("{{en:", "").replace("}}", "")
    return [token for token in cleaned.split() if token]


def load_script(source) -> dict:
    if isinstance(source, dict):
        return source
    return json.loads(Path(source).read_text())


def _choice(beat: dict, *, first: bool, previous: str | None) -> str:
    explicit = beat.get("visual")
    try:
        return select_visual(
            beat.get("text") or "",
            beat=beat.get("id"),
            first_in_beat=first,
            explicit=explicit,
            previous=None if previous == "custom" else previous,
        )
    except UnknownVisual as exc:
        raise SystemExit(str(exc)) from exc


def plan_script(script: dict, theme, config: dict) -> dict:
    """Voice, templates, SFX kinds, and music id. No audio and no ffmpeg."""
    language = script.get("language") or config["tts"]["language"]
    voice = voice_for(config, language)
    templates = []
    kinds: list[str] = []
    previous = None
    seen: set[str] = set()
    sfx_cfg = theme.sfx or {}
    cuts = sfx_cfg.get("preset", "generated") != "documentary"
    beats = list(script.get("beats") or [])
    if not beats:
        raise SystemExit("script has no beats")
    if (theme.intro or {}).get("enabled"):
        join = sfx_cfg.get("intro_join", "transition")
        if join not in ("", "none", None):
            kinds.append(str(join))
    for index, beat in enumerate(beats):
        beat_id = beat.get("id") or f"beat-{index}"
        first = beat_id not in seen
        seen.add(beat_id)
        choice = _choice(beat, first=first, previous=previous)
        templates.append({"id": beat_id, "template": choice})
        if index and cuts:
            kinds.append("cut")
        if choice != "custom":
            kinds.append("reveal")
        previous = choice
    if (theme.outro or {}).get("enabled"):
        kinds.append("stinger")
    if (theme.music or {}).get("enabled"):
        music = (theme.music or {}).get("id") or "unset"
    else:
        music = "none"
    return {
        "voice": voice,
        "language": language,
        "templates": templates,
        "sfx": kinds,
        "music": music,
    }


def format_plan(plan: dict) -> str:
    lines = [f"voice {plan['voice']}"]
    for item in plan["templates"]:
        lines.append(f"template {item['id']} {item['template']}")
    for kind in plan["sfx"]:
        lines.append(f"sfx {kind}")
    lines.append(f"music {plan['music']}")
    return "\n".join(lines) + "\n"


def _phrases(beats: list[dict], groups: list[list[dict]]) -> list[dict]:
    phrases = []
    for beat, words in zip(beats, groups):
        phrases.append(
            {
                "id": beat.get("id"),
                "text": beat.get("text") or "",
                "beat": beat.get("id"),
                "visual": beat.get("visual"),
                "words": words,
                "start": float(words[0]["start"]),
                "end": float(words[-1]["end"]),
            }
        )
    return phrases


def _groups(words: list[dict], beats: list[dict]) -> list[list[dict]]:
    spoken = [word for word in words if word.get("type", "word") == "word"]
    groups = []
    cursor = 0
    for beat in beats:
        count = len(spoken_tokens(beat.get("text") or ""))
        if count == 0:
            raise SystemExit(f"beat '{beat.get('id')}' has no words")
        chunk = spoken[cursor : cursor + count]
        if len(chunk) != count:
            raise SystemExit(
                f"beat '{beat.get('id')}' expected {count} words, synthesis returned {len(spoken) - cursor}"
            )
        groups.append(chunk)
        cursor += count
    if cursor != len(spoken):
        raise SystemExit(
            f"synthesis returned {len(spoken)} words and the beats use {cursor}"
        )
    return groups


def _safe_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value)
    return cleaned or "beat"


def write_plate(path: Path, theme, duration: float) -> None:
    """Brand-color plate with silent stereo audio. The narration is a separate stem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = int(theme.frame_width), int(theme.frame_height)
    fps = theme.fps
    color = str(theme.background).lstrip("#")
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x{color}:s={width}x{height}:r={fps}:d={duration:.3f}",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "ultrafast",
        "-c:a", "aac", "-ar", "48000",
        "-movflags", "+faststart",
        str(path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _materialize(edl: dict, edit_dir: Path, theme) -> dict:
    from visuals.render_slot import render_template

    edit_dir = Path(edit_dir)
    duration = float(edl["total_duration_s"])
    plate = edit_dir / "plate.mp4"
    write_plate(plate, theme, duration)
    edl["sources"]["PLATE"] = "plate.mp4"
    overlays = []
    width, height = int(theme.frame_width), int(theme.frame_height)
    fps = float(theme.fps)
    program = float(edl["total_duration_s"])
    for visual in edl.get("visuals") or []:
        if visual.get("template") == "custom":
            continue
        start = float(visual["start"])
        remain = program - start
        if remain <= 0.05:
            continue
        duration = min(float(visual["duration"]), remain)
        name = _safe_id(str(visual.get("id") or visual["template"]))
        path = edit_dir / "animations" / f"{name}.mp4"
        render_template(
            visual["template"],
            visual.get("params") or {},
            theme,
            (width, height),
            fps,
            duration,
            path,
            plate=True,
        )
        overlays.append(
            {
                "file": f"animations/{name}.mp4",
                "start_in_output": start,
                "duration": round(duration, 3),
                "template": visual["template"],
            }
        )
    edl["overlays"] = overlays
    return edl


def compile_script(
    source,
    edit_dir: Path,
    *,
    provider: str = "fake",
    synthesizer=None,
    theme=None,
    config: dict | None = None,
    materialize: bool = False,
    output: Path | None = None,
) -> dict:
    """Write the EDL, the voice stem, and the per-source transcript.

    ``materialize`` builds the plate and catalog overlays. ``output`` also
    runs ``render_edl``. Brand cards follow the theme; the committed theme
    leaves them off.
    """
    script = load_script(source)
    edit_dir = Path(edit_dir)
    edit_dir.mkdir(parents=True, exist_ok=True)
    theme = theme if theme is not None else load_theme(edit_dir)
    config = config if config is not None else load_speech_config(edit_dir)
    plan = plan_script(script, theme, config)
    beats = list(script["beats"])
    text = " ".join((beat.get("text") or "").strip() for beat in beats)
    cache_provider = provider
    if synthesizer is None:
        cache_provider, synthesizer = build_synthesizer(provider, config)
    result = synthesize_cached(
        edit_dir,
        cache_provider,
        plan["voice"],
        plan["language"],
        text,
        synthesizer.synthesize,
    )
    words = list(result["words"])
    groups = _groups(words, beats)
    ranges = []
    for beat, group in zip(beats, groups):
        ranges.append(
            {
                "source": "PLATE",
                "start": round(float(group[0]["start"]), 6),
                "end": round(float(group[-1]["end"]), 6),
                "role": "content",
                "beat": beat.get("id"),
                "quote": beat.get("text") or "",
            }
        )
    picked = assign_phrases(_phrases(beats, groups))
    branded = with_brand_ranges(
        {"ranges": ranges, "sources": {"PLATE": "plate.mp4"}},
        theme,
    )
    sfx_cfg = theme.sfx or {}
    events = events_from_ranges(
        branded["ranges"],
        intro_join=str(sfx_cfg.get("intro_join") or "transition"),
        cuts=sfx_cfg.get("preset", "generated") != "documentary",
    )
    events.extend(picked["events"])
    events.sort(key=lambda item: (float(item["at"]), str(item.get("kind"))))
    total = round(float(words[-1]["end"]), 6)
    voice_path = edit_dir / "audio" / "voice.wav"
    voice_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(result["audio"]).resolve() != voice_path.resolve():
        shutil.copyfile(result["audio"], voice_path)
    words_path = edit_dir / "audio" / "voice.words.json"
    payload = {"words": words}
    words_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    transcripts = edit_dir / "transcripts"
    transcripts.mkdir(parents=True, exist_ok=True)
    (transcripts / "PLATE.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    edl = {
        "version": 2,
        "plate": True,
        "language": plan["language"],
        "title": script.get("title") or "",
        "sources": branded["sources"],
        "ranges": branded["ranges"],
        "grade": "",
        "visuals": picked["visuals"],
        "overlays": list(picked["overlays"]),
        "subtitles": "master.ass",
        "captions": {"language": plan["language"]},
        "audio": {
            "voice": {
                "file": "audio/voice.wav",
                "start": 0.0,
                "sample_rate": result.get("sample_rate"),
            },
            "events": events,
        },
        "total_duration_s": total,
    }
    if not (theme.music or {}).get("enabled"):
        edl["audio"].pop("music", None)
    else:
        music_id = (theme.music or {}).get("id")
        if music_id:
            edl["audio"]["music"] = {"id": music_id}
    if materialize or output is not None:
        edl = _materialize(edl, edit_dir, theme)
    (edit_dir / "edl.json").write_text(json.dumps(edl, ensure_ascii=False, indent=2))
    if output is not None:
        from render import render_edl

        render_edl(
            edl,
            edit_dir,
            Path(output),
            build_subtitles=True,
            theme=theme,
        )
    return edl


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile script.json to an EDL and render")
    parser.add_argument("script", type=Path)
    parser.add_argument("--edit-dir", type=Path, required=True)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    script = load_script(args.script)
    theme = load_theme(args.edit_dir)
    config = load_speech_config(args.edit_dir)
    if args.plan:
        sys.stdout.write(format_plan(plan_script(script, theme, config)))
        return
    provider = args.provider or config["tts"]["provider"]
    output = args.output
    if output is None:
        output = Path(args.edit_dir) / "final.mp4"
    compile_script(
        script,
        args.edit_dir,
        provider=provider,
        theme=theme,
        config=config,
        materialize=True,
        output=output,
    )
    print(f"final → {output}")


if __name__ == "__main__":
    main()
