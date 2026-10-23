# Dan Tech brand and media upgrade

Planning document only. No feature work is in this change.

- Repo: `dan-tech-academy/video-use` (fork of browser-use/video-use)
- Branch: `feat/dantech-brand-and-media-upgrade`
- Date: 2026-10-23
- Audience: Dan Tech (`@dantech0xff`, `@dantech-0xff`) and whoever implements the phases

This plan turns the existing conversation-driven editor into a channel pipeline that can still cut footage and can also generate narrated tech videos. Brand, caption variety, per-segment graphics, sound effects, music, and speech synthesis land in an order where each phase has something real to call.

Effort key, used on every phase:

| Size | Meaning |
| --- | --- |
| S | One module or a thin adapter, unit-tested, no new runtime |
| M | New module plus a change to the render path, fixtures, and `SKILL.md` |
| L | New subsystem (schema, planner or provider, render integration, a listened-to sample) |

## 1. Current architecture

video-use is an agent skill plus a handful of Python CLIs. The model never watches the file. It reads a packed transcript, writes an edit decision list, and `helpers/render.py` produces the MP4. There is no application server, no theme file, and no speech synthesizer.

### Pipeline

```
footage → transcribe.py (ElevenLabs Scribe)
       → pack_transcripts.py → takes_packed.md
       → agent writes edl.json and optional overlay clips
       → render.py
            1. per-segment extract (scale, grade, 30 ms audio fades)
            2. lossless concat
            3. overlays (PTS-shifted), then subtitles
            4. two-pass loudnorm (−14 LUFS, −1 dBTP, LRA 11)
       → agent self-checks cut boundaries with timeline_view.py
```

Session output is required to live in `<videos_dir>/edit/`, not in this repo (`SKILL.md` hard rule 12).

### Modules

| Path | Role |
| --- | --- |
| `SKILL.md` | Agent contract. Hard rules, EDL example, caption and animation guidance, music and SFX *rules of thumb*. |
| `install.md` | Clone, `uv sync` / pip, ffmpeg, skill symlink, `ELEVENLABS_API_KEY`. |
| `helpers/transcribe.py` | Extract 16 kHz mono WAV, POST to `https://api.elevenlabs.io/v1/speech-to-text` (`scribe_v1`, word timestamps, diarization, audio events). Cache `edit/transcripts/<stem>.json`. |
| `helpers/transcribe_batch.py` | Four-worker wrapper. Same Scribe call. |
| `helpers/pack_transcripts.py` | Group Scribe words into phrases on silence ≥ 0.5 s or speaker change. Writes `takes_packed.md`. |
| `helpers/render.py` | The whole picture and soundtrack assembly path. ~800 lines. |
| `helpers/grade.py` | Named ffmpeg grade presets (`subtle`, `neutral_punch`, `warm_cinematic`, `none`) plus a bounded auto grade. |
| `helpers/timeline_view.py` | Filmstrip + waveform PNG for QC. `--edl` is accepted and exits unimplemented. |
| `skills/manim-video/` | Separate Manim explainer skill. Optional `manim-voiceover` (ElevenLabs, gTTS, Azure). Its music example is a one-shot `amix`, disconnected from `render.py`. |
| `tests/` | Unit tests for caption chunking, SRT offsets, fps, portrait rotation. Loaded by file path, not as a package. |
| `pyproject.toml` | Runtime deps: `requests`, `librosa`, `matplotlib`, `pillow`, `numpy`. Optional extra: `manim`. `librosa` and `matplotlib` are not imported anywhere. |
| `.env.example` | `ELEVENLABS_API_KEY=` only. |

Helpers are scripts. `render.py` imports `grade` by bare name because running `python helpers/render.py` puts `helpers/` on `sys.path`. Tests load that file with `importlib`. New code should keep that import style, or become a real package and update the tests in the same phase. Do not leave a half-package that only imports on one of the two paths.

### EDL, the only config

`SKILL.md` documents version 1:

```json
{
  "version": 1,
  "sources": {"C0103": "/abs/path/C0103.MP4"},
  "ranges": [{"source": "C0103", "start": 2.42, "end": 6.85, "beat": "HOOK"}],
  "grade": "warm_cinematic",
  "overlays": [{"file": "edit/animations/slot_1/render.mp4", "start_in_output": 0.0, "duration": 5.0}],
  "subtitles": "edit/master.srt",
  "total_duration_s": 87.4
}
```

`render.py` reads `sources`, `ranges`, `grade`, `overlays`, `subtitles`. Unknown keys are ignored, so additive fields are safe. There is no brand, font, caption-style, music, or SFX field.

### How timing, captions, and visuals actually work

- **Word times** come from Scribe. `build_master_srt` maps them onto the output timeline as `word.start - segment_start + segment_offset`. That formula is hard rule 5 and is already tested (`tests/test_render_captions.py`).
- **Chunking** is fixed in code: about 2 words, grow to 3 if the cue would flash under 0.35 s, break on `. , ! ? ; :` or a gap ≥ 0.3 s. The SRT text is always uppercased inside `build_master_srt`.
- **Caption look** is the module constant `SUB_FORCE_STYLE`: `FontName=Helvetica`, size 18, bold, white with black outline, `Alignment=2`, `MarginV=90`. It is passed as ffmpeg `force_style` on every render. The EDL cannot select another style. `SKILL.md` still shows `MarginV=35` in the worked example; the code comment treats 90 as the vertical-video safe zone. The code is the one that ships.
- **Helvetica is a portability bug waiting.** libass resolves `FontName` through fontconfig. On Linux (and any machine without Helvetica) the face silently falls back. `SKILL.md` already warns that failed font loads ship "almost Arial". Vietnamese diacritics are the first thing a fallback face gets wrong.
- **Overlays** are pre-rendered clips. The agent authors each one in HyperFrames, Remotion, Manim, or PIL, in parallel, one sub-agent per slot. `render.py` only knows `file`, `start_in_output`, and `duration`. It shifts the overlay with `setpts=PTS-STARTPTS+T/TB` (hard rule 4) and enables it with `overlay=enable='between(t,…)'`. Nothing picks a template from the words on screen.
- **Overlay audio is discarded.** The composite maps `[outv]` and `0:a` and copies the base audio. A whoosh baked into an animation MP4 never reaches the output.
- **Grade** is a global EDL string, applied per segment at extract time. It is a color-correction chain, not a brand palette.
- **Audio assembly** is: 30 ms `afade` in and out on every segment (hard rule 3), AAC 192 kbit/s at 48 kHz, concat with `-c copy`, then two-pass `loudnorm` on the finished file (`-c:v copy`). There is no stem, no `amix`, no sidechain, no music input, no SFX input.
- **Loudnorm targets** match the skill's publish rule (−14 LUFS, true peak ≤ −1 dBTP). The skill's music notes ("duck −12 to −15 dB under speech", "hit SFX on the frame", "fewer effects") are instructions to the agent, not code.

### What ElevenLabs is doing here

ElevenLabs is speech-to-text. `transcribe.py` calls Scribe and stores word-level verbatim JSON, speaker ids, and audio events such as `(laughter)`. Nothing in `helpers/` calls an ElevenLabs TTS endpoint. The only TTS mention is inside `skills/manim-video/references/rendering.md`, as an optional Manim plugin, and that path does not feed `render.py`.

So "replace ElevenLabs TTS" is a new capability, not a swap. Scribe should stay the footage transcriber until a separate decision says otherwise. The word JSON shape (`type`, `text`, `start`, `end`) is the integration contract. A TTS provider is useful here only if its adapter emits that same shape, in seconds, on the narration timeline.

### The five outcomes, against today's code

| Outcome | Today |
| --- | --- |
| Brand in frame (logo, colors, fonts, intro, outro, lower-thirds), configurable | No theme file. Palette and font are prose in `SKILL.md` plus one hardcoded caption style. No watermark, intro, outro, or lower-third primitive. |
| Several text styles; infographics from text; a graphic chosen per spoken segment | One caption style. Overlays are hand-specified clips. No template catalog and no selector. |
| Transition, cut, and infographic SFX | Skill text only. Composite drops non-base audio. |
| Music with ducking under the voice | Skill text only. `manim-video` shows a static `volume` + `amix` that does not duck and does not run before loudnorm. |
| TTS other than ElevenLabs, pluggable, Vietnamese and English | No TTS in the render pipeline. |

## 2. Target shape

Two ways to produce an EDL, one way to render it.

```
camera footage ── Scribe ── takes_packed.md ── agent cuts ─┐
                                                           ├─ edl.json + theme ─ render
script.json ── TTS (wav + word JSON) ── phrase list ──────┘
                 │                         │
                 │                         └─ visual selector → silent overlay clips
                 └─ voice stem ─┐
cut / reveal events → SFX ─────┼─ mix (normalize=0) → loudnorm → final.mp4
music bed, ducked to voice ────┘
```

Picture order stays the one the hard rules require:

1. Base segments (camera, or a generated brand-color plate).
2. Content overlays (infographics, intro/outro only if they are not their own segments).
3. Watermark and lower-thirds.
4. Subtitles last.

Audio order:

1. Voice stem, with the existing 30 ms segment fades already baked in.
2. SFX placed on the output timeline, each shifted early by its measured attack.
3. Music bed, attenuated while the voice envelope is hot.
4. One two-pass loudnorm on the full mix. Stems are not normalized individually.

`theme.json` is channel config (colors, fonts, logo, caption styles, watermark, intro/outro, lower-third). It lives in the repo as the Dan Tech default and may be overridden by `<edit>/theme.json`. The EDL stays the per-video timeline. Speech provider and voice ids live in `speech.json` next to the theme, so a palette tweak does not re-synthesize audio.

Versioning: keep accepting EDL `version` 1. Add fields additively. Bump to `version` 2 in the audio-timeline phase, and keep the version-1 renderer working for old session files.

## 3. Invariants

These are existing production rules. Phases add behavior around them.

1. Subtitles are the last filter. Watermark, lower-thirds, and infographics are overlays underneath. `force_style` must not be passed on an ASS file, because it overrides the styles embedded in the file.
2. Per-segment extract, then lossless concat. Do not collapse the pipeline into one filtergraph.
3. 30 ms audio fades stay on voice-segment boundaries. They do not chop the music bed at every cut.
4. Overlays still use `setpts=PTS-STARTPTS+T/TB`.
5. Caption times stay on the output timeline: `word.start - segment_start + segment_offset`.
6. Cuts snap to word boundaries, with 30–200 ms pad, for footage. Generated videos do not cut inside a TTS word either.
7. Word-level verbatim timestamps. Phrase-only TTS is not enough.
8. Transcript and TTS caches key off the source bytes or the text+voice hash. Do not re-call a paid API when the input is unchanged.
9. Strategy confirmation before an edit. Generated videos get the same confirm step on the script and the selected visuals.
10. Session artifacts stay in `<videos_dir>/edit/`. The repo holds theme defaults, the template catalog, and small CC0 SFX if the license decision allows. It does not hold rendered videos or API keys.
11. Loudnorm remains the last audio process, at the current social targets, unless the owner picks a different publish target.
12. Overlay clips stay silent. Sound is a timeline event so the mix can level it.

## 4. Phases

### Phase 1 — Theme and style contract

**Effort:** M

**Goal:** One theme document supplies colors, fonts, frame size, and safe zones. Render and future templates read it. No logo is drawn yet.

**Why now:** Branding, caption styles, and infographics all need the same tokens. Putting Dan's hex values into `render.py` the way Helvetica is hard-coded today would make the next three phases fight each other.

**Tasks:**

1. Add `brand/theme.schema.json` (JSON Schema) and `brand/theme.example.json`. Colors start as `null` until the brand-asset decision is filled in. Include channel name `Dan Tech` and both handles as strings, without guessing which handle belongs to which site.
2. Add `helpers/theme.py` with `load_theme(edit_dir) -> Theme`. Search order: `<edit>/theme.json`, then `brand/theme.json` beside the repo, then the built-in example. Fail with a path and a missing key, not a silent default font.
3. Resolve fonts to files on disk. A style that names a family also names a file. Missing file is an error that names the path.
4. Teach `render.py` to load the theme and to resolve caption style from `edl["captions"]["style"]` or `theme.captions.default`. The first implementation may still emit today's `SUB_FORCE_STYLE` when the style id is `bold-overlay`, so current output stays stable.
5. Record frame size and fps on the theme (`1920×1080`, `30`) and thread them into extract scale only when the EDL says `plate` or the theme sets `frame.mode: "force"`. Footage keeps today's "scale to 1080 on the long side, preserve portrait, preserve source fps" behavior.
6. Document the theme in `SKILL.md` as a required input for any new branded render, and point the `MarginV=35` example at the theme safe-zone value (code default 90).
7. Unit-test loading, override order, missing font, and unknown style id. No ffmpeg in these tests.

**Files:** `brand/theme.schema.json`, `brand/theme.example.json`, `helpers/theme.py`, `helpers/render.py`, `SKILL.md`, `tests/test_theme.py`.

**New dependencies:** none.

**Acceptance:**

- A theme file with a missing font aborts before ffmpeg.
- `<edit>/theme.json` overrides the repo theme key by key, or replaces the file, and the test shows which.
- An EDL without caption fields still renders `bold-overlay` with the current force-style string (existing caption tests pass).
- `Theme` exposes background, surface, text, muted, accent, accent alt, font files, `margin_v`, frame width, frame height, fps.

**Risks:**

- Deep-merge of theme overrides is easy to get subtly wrong. Prefer whole-file override in v1 (`<edit>/theme.json` replaces the repo file) and leave merge for later.
- Agents will keep inventing palettes in prose unless `SKILL.md` tells them to read the theme and stop.

### Phase 2 — Caption and text styles

**Effort:** M

**Goal:** More than one caption treatment, selected by the theme or the EDL, rendered through a bundled font. Layout for later infographic text uses the same style table.

**Why now:** This is the first consumer of the theme, and it is on screen in every video. Lower-thirds and infographics should call the same text metrics instead of growing a second font system. It does not need TTS: Scribe words already drive it, so footage edits improve before generation exists.

**Tasks:**

1. Ship an OFL face that covers Vietnamese diacritics and English, plus a mono face for code. Recommended files: Be Vietnam Pro (display and body) and JetBrains Mono (code), under `brand/fonts/`, with the OFL license text beside them. Theme paths point at those files.
2. Replace the single SRT + `force_style` path with an ASS writer, `helpers/captions.py`. Styles are ASS style lines filled from the theme (font file via `fontsdir`, primary color, outline, alignment, margin).
3. Keep a `.srt` fallback: if the EDL points at an existing `.srt`, burn it with the named style's force-style, and do not require a re-chunk. New builds write `.ass`.
4. Implement these styles as data, not as copies of `build_master_srt`:

    | Id | Chunking | Case | Look |
    | --- | --- | --- | --- |
    | `bold-overlay` | Current `chunk_words` (2–3 words, pause and punctuation) | Uppercase | White fill, black outline, bottom center. This is today's look, with the bundled font. |
    | `sentence` | Break on punctuation and pauses; 4–7 English words, or a syllable/character budget for Vietnamese | As spoken | Larger, higher margin, muted outline. Long-form explainer. |
    | `karaoke` | One phrase on screen | As spoken | Upcoming words in muted text, the active word in the accent color. Uses per-word times and ASS `\kf`. |
    | `terminal` | Phrase or code token | As spoken | Mono, accent caret, dark surface box. For command lines. |
    | `emphasis` | Short chunk around one payoff word | As spoken | Payoff word in accent, the rest white. |

5. Stop uppercasing inside the shared SRT builder. Case is a style flag.
6. Vietnamese: whitespace separates syllables, not words, so `CHUNK_WORDS = 2` cuts "công nghệ" in half and then uppercases it. `sentence` is the default style when `speech.language` is `vi`. The chunker takes a `language` argument and, for `vi`, budgets syllables per cue (start at 12–18, break on `.,!?;:` and pauses) instead of English word pairs.
7. Pass `fontsdir` to ffmpeg. Do not pass `force_style` when the file is ASS.
8. Extend caption tests for case, Vietnamese syllable budget, karaoke tag timing, and "ASS path does not include force_style".

**Files:** `helpers/captions.py`, `helpers/render.py` (call the writer; composite uses `fontsdir`), `brand/fonts/*`, `brand/theme.example.json`, `SKILL.md`, `tests/test_render_captions.py`, `tests/test_captions_ass.py`.

**New dependencies:** none. Fonts are files. libass is part of a normal ffmpeg build; the phase must detect a build without libass and say so.

**Acceptance:**

- The existing English chunking test still describes `bold-overlay` output, now tagged with that style.
- A Vietnamese fixture with syllable spacing does not split a two-syllable lexical item when the style is `sentence` (use a hand-written word list, not a live API).
- Render command for an `.ass` file contains `fontsdir` and does not contain `force_style`.
- A machine without the bundled font fails in `theme.py`, before ffmpeg.

**Risks:**

- libass `MarginV` and `\pos` interact with `PlayRes`. Pin `PlayResX/Y` to the frame size so theme margins mean pixels.
- Karaoke `\kf` timing is in centiseconds. Round from the word JSON in one function and test that function.
- Uppercase Vietnamese is a different string (`đ` / `Đ`). The uppercase flag must use Unicode casefold rules, and `sentence` mode should be the one published for Vietnamese until someone proofreads an uppercase sample.

### Phase 3 — Pluggable TTS, Scribe left in place

**Effort:** L

**Goal:** A provider interface whose default implementation is Azure Speech neural TTS. Output is a WAV plus a Scribe-shaped word list. Footage transcription stays on Scribe, behind a thin adapter of its own.

**Why now:** Generated pictures need word times, and the mix needs a voice stem that is not glued to a camera file. SFX and music should be written against that stem and this interface, not against a one-off `ffmpeg -i narration.mp3` in a Manim note. Caption styles already exist, so the first TTS sample can be captioned immediately.

**Tasks:**

1. Add `helpers/speech/base.py` with two small protocols, not one combined class.

    ```text
    synthesize(text, voice, language, style=None) ->
        {audio: wav Path, words: [{type, text, start, end}], sample_rate, voice, language}

    transcribe(media, language=None, num_speakers=None, audio_track=0) ->
        Scribe-shaped dict   # existing transcribe.py moves behind this
    ```

    Word `start` and `end` are seconds. Adapters convert provider-native units inside the adapter.

2. Add `brand/speech.example.json`:

    ```json
    {
      "stt": {"provider": "scribe"},
      "tts": {
        "provider": "azure",
        "language": "vi",
        "voices": {
          "vi": "vi-VN-NamMinhNeural",
          "en": "en-US-AndrewNeural"
        }
      }
    }
    ```

    Voice ids are defaults the owner can reject after the listening test in the open decisions. The example must not be treated as a locked brand voice.

3. Azure adapter (`helpers/speech/azure.py`):
    - Auth from `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` in `.env`. Same "missing key" behavior as `load_api_key` in `transcribe.py`.
    - Prefer the Speech SDK (`azure-cognitiveservices-speech`) so `synthesis_word_boundary` arrives during a synchronous synth. Microsoft documents those events for Azure Speech voices, and documents that OpenAI voices on the same service do not emit them. Dragon HD Omni documents the payload (`text`, `audio_offset`, `text_offset`).
    - First task of the phase, before any caption wiring: synthesize a 10-second Vietnamese sample and a 10-second English sample, print the raw offset unit, and lock the seconds conversion in a test fixture checked into `tests/fixtures/`. Azure SDK offsets are 100-nanosecond ticks. Do not guess from a blog post if the probe disagrees.
    - If `vi-VN-HoaiMyNeural` or `vi-VN-NamMinhNeural` omits boundaries, try `vi-VN-Linh:MAI-Voice-2-Flash`, then fall back to forced alignment for that voice only. Alignment is a provider-internal detail. Callers still receive seconds.
    - Split text on sentence boundaries so each request stays under the real-time 10-minute output cap. Offset later chunks by the running duration. Cache each chunk under `<edit>/audio/tts/<sha256>.wav` plus `.words.json`, keyed by provider, voice, language, style, and text.
    - For mixed lines, allow SSML `<lang xml:lang="en-US">…</lang>` around English product tokens when the narration language is `vi`. The script format in phase 9 can mark those tokens; the adapter must not invent pronunciations.

4. Scribe adapter: move `call_scribe` behind `transcribe()` without changing the CLI of `transcribe.py`. `ELEVENLABS_API_KEY` stays required for footage.

5. A second TTS adapter, `edge`, for local development when no Azure key is present. `edge-tts` already surfaces WordBoundary messages from the same Microsoft voices. Mark it `dev_only` in `speech.json`. It is an unofficial client of the Edge read-aloud endpoint and is not the publish path.

6. CLI: `python helpers/speak.py --text-file script.txt --out edit/audio/voice.wav --words edit/audio/voice.words.json`. `--provider` overrides the config.

7. Document `.env.example` keys. Do not log key values.

8. Tests use a fake provider. One fixture test converts a recorded Azure word-boundary payload (from the probe) into the Scribe word shape. No test hits the network.

**Files:** `helpers/speech/base.py`, `helpers/speech/azure.py`, `helpers/speech/edge.py`, `helpers/speech/scribe.py`, `helpers/speak.py`, `helpers/transcribe.py` (delegate), `brand/speech.example.json`, `.env.example`, `install.md`, `SKILL.md`, `pyproject.toml`, `tests/test_speech_words.py`.

**New dependencies:**

- Default extra `tts`: `azure-cognitiveservices-speech`.
- Dev extra `tts-edge`: `edge-tts`.
- Not in the default install: Kokoro, Piper, Coqui, F5-TTS, OpenAI, Google client libraries. Add a provider later by implementing `synthesize` and a word-time adapter. The comparison is in section 5; the owner decision is in section 6.

Forced alignment, only if a voice returns bare audio: `faster-whisper` (large-v3, or a Vietnamese model such as PhoWhisper) as an optional extra `align`. It is not a dependency of the Azure path if the probe shows boundaries.

**Acceptance:**

- `speak.py` with the fake provider writes a WAV header and a words file that `build_master_srt` / the phase 2 ASS writer can turn into cues.
- Swapping `tts.provider` does not change `render.py` call sites.
- A second run with the same text, voice, and language does not call the adapter's network function (cache hit).
- `transcribe.py` still sends Scribe requests and still refuses a silent track.
- Word times are monotonic, non-overlapping, and in seconds.

**Risks:**

- Vietnamese "words" from the synthesizer may be syllables. The phase 2 `vi` chunker has to consume that token stream. Save the probe JSON and build the chunker fixture from it.
- SDK wheels are large and platform-specific. If the Linux wheel fails in this environment, switch the adapter to batch synthesis (`wordBoundaryEnabled`) and keep the same output shape. Batch is slower and asynchronous; the cache hides that on the second run.
- Voice quality is a listening decision. The phase is done when the contract works, not when the voice is "the" Dan Tech voice. Leave the chosen id in `speech.json` after the owner listens.
- Do not route TTS through `manim-voiceover`. That plugin is Manim-only and its examples default to ElevenLabs.

### Phase 4 — Audio timeline and mix foundation

**Effort:** M

**Goal:** The EDL can name a voice stem, a list of SFX events, and a music bed. `render.py` mixes them after the picture composite and before loudnorm. Music and SFX files may be absent; the graph builder and the voice path must exist.

**Why now:** Cut SFX, infographic SFX, and ducking are all "put this clip at this time at this gain". Building each as its own ffmpeg invocation will drop the attack offset, hit `amix`'s default normalize, or loudnorm the voice before the bed exists. The TTS phase provides a stem for generated video; footage already has a stem inside the concat result.

**Tasks:**

1. Extend the EDL. Version 2 when `audio` is present. Version 1 still renders exactly as today.

    ```json
    {
      "version": 2,
      "audio": {
        "voice": {"file": "edit/audio/voice.wav", "start": 0.0},
        "events": [
          {"kind": "cut", "at": 4.20},
          {"kind": "reveal", "at": 6.00, "id": "slot_3"}
        ],
        "sfx": [
          {"file": "brand/sfx/whoosh.wav", "at": 4.11, "gain_db": -8}
        ],
        "music": {
          "file": "brand/music/bed.wav",
          "gain_db": -16,
          "duck_db": -13,
          "attack_ms": 80,
          "release_ms": 400
        }
      }
    }
    ```

    `events` are semantic. `sfx` are resolved files. Phase 7 fills `sfx` from `events`. Phase 4 can mix a hand-written `sfx` list so the graph is testable before the library exists.

2. Add `helpers/audio.py`:
    - Measure attack as the first sample within 30 dB of the file peak (the rule already written in `SKILL.md`). Return seconds.
    - Place a clip at `at - attack` so the transient hits `at`.
    - Build the ffmpeg filtergraph as data and as a string. Voice is split into a mix copy and an envelope key. Music is delayed and gained. SFX are delayed, gained, and mixed. `amix=normalize=0` (the default `normalize=1` divides by the number of inputs and quietly ruins the levels).
    - Ducking knob exists in the graph builder in this phase: a volume automation from the voice envelope, target `duck_db` below the music's own gain while voice RMS is above a threshold, with attack and release ramps. A phase 4 test can feed a synthetic tone and check that the filter string contains the automation. Perceptual tuning is phase 8, once a real bed exists.
    - Write the voice envelope with the stdlib `wave` module and `numpy`. Do not take a new dependency on `librosa`.

3. Render order change in `main`:
    - Extract, concat, composite picture exactly as now (`-c:a copy` through composite).
    - If `audio` is present, run a mix pass with `-c:v copy` onto a new file.
    - For footage with no separate voice WAV, the concat audio *is* the voice stem. Demux it in the mix pass; do not require TTS.
    - For a generated plate, `voice.file` is the TTS wav and the plate's audio track is silent.
    - Then the existing `apply_loudnorm_two_pass`. `--no-loudnorm` still skips that last pass.
    - 30 ms fades remain inside `extract_segment` and therefore on the voice stem only.

4. Keep overlay inputs video-only in the composite. Document in `SKILL.md` that animation slots must be silent.

5. Tests: attack measurement on a synthetic WAV (silence, then a click); graph builder sets `normalize=0`; a version-1 EDL does not enter the mix pass; loudnorm is still after the mix function in `main` (assert call order with a fake).

**Files:** `helpers/audio.py`, `helpers/render.py`, `SKILL.md` (EDL v2), `tests/test_audio_mix.py`.

**New dependencies:** none. ffmpeg `amix`, `adelay`, `volume`, and `aeval`/`volume` automation are already required by the install.

**Acceptance:**

- Version-1 fixture EDLs follow the old path (test by mocking `extract` / `composite` / `loudnorm` and asserting the mix function is not called).
- A synthetic voice tone plus one SFX produces a mix command whose SFX start is `at - attack`.
- The mix pass copies video (`-c:v copy`) and does not re-run the overlay filtergraph.
- Loudnorm, when enabled, reads the mixed file, not the pre-mix composite.
- `amix` is passed `normalize=0`.

**Risks:**

- Sample-rate mismatch (TTS often 24 kHz, segments are 48 kHz). Resample every stem to 48 kHz before the mix. Test that the graph contains `aresample=48000` for a 24 kHz input.
- `adelay` takes milliseconds and has a per-channel syntax (`delays|delays` for stereo). Centralize that format in one function.
- Sidechain compress looks simpler than envelope automation and does not hit a dB target. Keep the dB automation even if the first graph is longer. Phase 8 checks the number, not the filter name.

### Phase 5 — Brand package

**Effort:** M

**Goal:** Watermark, intro, outro, and a lower-third, all driven by the theme, on by default for a Dan Tech render and switchable off per video.

**Why now:** The theme tokens and the text styles exist, so these assets are parameters rather than a one-off PIL script. The audio timeline exists, so an intro sting and an outro music ramp have an `events` list to join. The graphics themselves do not wait on the SFX library.

**Tasks:**

1. Theme fields:

    ```json
    {
      "watermark": {"file": "brand/logo.png", "enabled": true, "corner": "top-right", "width_px": 160, "margin_px": 36, "opacity": 0.85},
      "lower_third": {"enabled": true, "name": "Dan Tech", "handle": "@dantech0xff", "duration_s": 4.0, "at": "first-speech"},
      "intro": {"enabled": true, "duration_s": 2.5, "title": null},
      "outro": {"enabled": true, "duration_s": 3.5, "lines": ["Dan Tech", "@dantech0xff"]}
    }
    ```

    `handle` is a single on-screen string. Both public handles stay available; the owner picks the one burned into the frame (open decision).

2. Watermark: PIL scales the PNG once, ffmpeg `overlay` for the whole timeline, above content overlays and below subtitles. Disable it during intro and outro ranges so the end card is not double-branded. Missing logo file with `enabled: true` is an error that tells the owner to drop a PNG at the theme path.

3. Intro and outro are synthetic sources, not overlays. Generate `edit/brand/intro.mp4` and `outro.mp4` (brand background, logo, optional title, silent audio) and insert them as EDL ranges before and after the content ranges. Caption offset math then stays correct with no special case, and the 30 ms fades apply at those boundaries too. Hold the outro's final composition for the whole outro duration (the skill's "hold the last frame" rule).

4. Lower-third: one silent overlay clip, bottom-left, inside the safe margin, using the `sentence` / display font and the accent bar color from the theme. Default timing: from the first content word, for `duration_s`. EDL may override with `lower_third: {name, handle, start, duration}` per range for a guest. It must not occupy the caption band; caption `margin_v` and the lower-third box are computed from the same safe rect and the test checks they do not overlap at 1920×1080 or 1080×1920.

5. PNG logo, not SVG, so the phase does not add a SVG renderer. The source SVG can sit beside it for the owner; render reads the PNG.

6. `SKILL.md`: when the theme enables these, the agent includes them in the strategy proposal instead of inventing a title card.

**Files:** `helpers/brand.py`, `helpers/render.py` (range insertion and watermark overlay), `brand/theme.example.json`, `brand/theme.schema.json`, `SKILL.md`, `tests/test_brand_layout.py`.

**New dependencies:** none. Pillow and ffmpeg are already required. Logo PNG is an owner asset, gitignored if it is not ready (`brand/logo.png` in `.gitignore` until he adds one, with `brand/logo.README` pointing at the decision). A tiny generated placeholder PNG is worse than a hard failure; fail until the file exists and the theme opts in. Default example theme ships with `watermark.enabled: false` and `intro.enabled: false` so stock footage renders do not crash. Dan's real `brand/theme.json`, added when assets arrive, turns them on.

**Acceptance:**

- With brand features off, frame count and EDL ranges match today's render.
- With them on, the compiled range list starts with `intro` and ends with `outro`, and content caption offsets shift by the intro duration (unit test the offset helper).
- Watermark overlay is not the last filter; the subtitle filter is.
- Lower-third rectangle and caption rectangle do not intersect in both orientations.
- Absent logo and `watermark.enabled: true` exits with the path it looked for.

**Risks:**

- Inserting intro/outro ranges after the agent has written timestamps will desync a hand-written EDL. Generate the bookends inside `render.py` from the theme at compile time, and write the resolved ranges next to the output (`edit/edl.resolved.json`) so QC sees what was actually rendered.
- A watermark on top of a face is a taste problem the theme cannot fully solve. Default corner is top-right; the owner can move it. Do not auto-track a face in this phase.

### Phase 6 — Dynamic infographics

**Effort:** L

**Goal:** Each spoken phrase gets a visual treatment chosen from a closed catalog. The treatment is parameterized by the theme and the phrase text. The catalog is not one template stretched across the video, and it is not a fresh sub-agent program for every line.

**Why now:** It needs theme tokens, the text style table, and word times (Scribe or TTS). It should land before SFX so a reveal has a real timestamp to hang a sound on. The brand package has already claimed the corners and the safe area, so templates can lay out inside a known rect.

**Tasks:**

1. Phrase records gain an optional `visual` block, produced by `helpers/visuals/select.py` and stored on the EDL:

    ```json
    {"template": "stat", "start": 12.40, "duration": 4.0, "params": {"value": "40%", "label": "less waiting"}, "sfx": "reveal"}
    ```

    `start` leads the payoff word by the template's reveal duration, matching the timing rule already in `SKILL.md`.

2. Deterministic selector, in order, first match wins:

    | Signal | Template |
    | --- | --- |
    | Digit, `%`, currency | `stat` |
    | Three or more list items, or a line that is a sequence | `list` |
    | Backticks or a shell-looking token | `code` |
    | Contrast cue (`vs`, `versus`, `so với`, `hơn`) | `comparison` |
    | First phrase of a beat, or a beat named `HOOK` / `INTRO` | `section` |
    | Question, short | `question` |
    | Anything else | `kinetic` |

    An explicit `visual` on the script or EDL overrides the selector. The selector never returns a template name outside the catalog. An LLM hint, if the agent wants one, is only allowed to be one of those ids and is stored as `visual.reason`. Re-running the selector on the same phrase yields the same id.

3. Catalog, each a function `(params, theme, size, fps, duration) -> silent mp4` in `helpers/visuals/templates/`:

    | Template | On-screen behavior |
    | --- | --- |
    | `kinetic` | Phrase set in the display font, one idea, accent on the payoff word, ease-out cubic. |
    | `section` | Beat label plus a rule in the accent color. |
    | `stat` | Big numeral counting up, short label, nothing else. |
    | `list` | Items appear one at a time, never two new items in the same beat. |
    | `comparison` | Two columns, left then right. |
    | `code` | Mono panel, type-on, caret. |
    | `question` | Single line, holds through the answer phrase if the next phrase is short. |
    | `quote` | Quoted span, attribution in the muted color if present. |

    Render with Pillow frames and ffmpeg (both already dependencies). Transparent background when the template is an overlay on footage; solid `theme.colors.background` when the video is a generated plate. Duration floor: 3 s for anything with a number or a list, otherwise hold through the phrase and at least 1 s on the settled frame.

4. Layout rect is the theme safe area minus the watermark box minus the caption band minus the lower-third box. A template that cannot fit emits a shorter `kinetic` fallback and records `visual.fallback` on the EDL. It does not draw under the captions.

5. Wire selected clips into `overlays[]` with the existing PTS shift. They stay silent. Each clip also appends an `audio.events[]` entry `{kind: "reveal", at: <payoff time>, id}`.

6. Escape hatch: an overlay already authored in HyperFrames, Remotion, or Manim is left untouched when its EDL entry has `"template": "custom"`. The parallel sub-agent workflow in `SKILL.md` stays for diagrams the catalog cannot express (state machines, equation derivations). The selector must not call those agents.

7. Tests: selector table (including a Vietnamese `so với` line and an English `40%` line); a layout test that the stat template's glyph box sits inside the safe rect at 1920×1080; fallback when the phrase is too long; custom overlays are not replaced.

**Files:** `helpers/visuals/select.py`, `helpers/visuals/templates/*.py`, `helpers/visuals/render_slot.py`, `helpers/render.py` (consume `visuals` if overlays were not pre-baked), `SKILL.md`, `tests/test_visual_select.py`, `tests/test_visual_layout.py`.

**New dependencies:** none.

**Acceptance:**

- Given a fixed phrase list, the selector output is stable across runs.
- Every catalog template renders a silent file whose duration matches the request within one frame, at the theme frame size.
- A phrase with a percentage becomes `stat`; a phrase with `so với` becomes `comparison`; a plain sentence becomes `kinetic`.
- Captions still composite after these overlays.
- A `custom` overlay survives compilation.

**Risks:**

- A template per line can flicker if every adjacent phrase switches template. Add a stickiness rule: stay on the current template through a beat unless the signal changes class (a `stat` may interrupt; `kinetic` does not replace `kinetic`).
- Pillow text layout will wrap badly on long Vietnamese lines. The fit test is part of acceptance, not a follow-up. If a line does not fit, fall back to `kinetic` with a smaller size once, then truncate with an ellipsis and a warning in the EDL.
- Do not generate icons from the network or from an image model in this phase. Shapes and type only. Icon sets are a later asset drop with a license.

### Phase 7 — Sound effects

**Effort:** M

**Goal:** Cut, transition, reveal, tick, and stinger events trigger clips from a replaceable library, hit on the frame, and sit in the phase 4 mix.

**Why now:** The mix can already place a file at `at - attack`, and phase 6 writes `reveal` events. This phase is the binding from event kind to file, plus gain defaults. Doing it earlier would hard-code paths that the catalog does not emit yet. Cut events can be derived from EDL range boundaries even when no infographic exists, so footage-only edits get sounds too.

**Tasks:**

1. Add `brand/sfx/manifest.json`:

    ```json
    {
      "cut": {"file": "cut.wav", "gain_db": -10},
      "transition": {"file": "whoosh.wav", "gain_db": -12},
      "reveal": {"file": "pop.wav", "gain_db": -8},
      "tick": {"file": "tick.wav", "gain_db": -14},
      "impact": {"file": "impact.wav", "gain_db": -6},
      "stinger": {"file": "stinger.wav", "gain_db": -4}
    }
    ```

    Paths are relative to the manifest. Replacing a file does not require a code change.

2. Resolver in `helpers/audio.py`: walk `audio.events`, append concrete `audio.sfx` entries, skip a kind whose file is missing only if the theme says `sfx.optional: true`; otherwise fail with the kind name and path. Default `optional` to false once a library is checked in, true while the license decision is open, so renders do not break before the owner supplies files.

3. Emit events automatically:
    - `cut` at each content range boundary after the first, not at intro/outro joins (those get `transition` or `stinger` if the theme asks).
    - `reveal` from phase 6 visuals, at the payoff time.
    - `tick` optionally on `list` item reveals, capped.
    - `stinger` at the outro start.

4. Density cap, from the existing skill rule: default maximum of one SFX per 1.5 s, and no more than about 8 in a 20 s span. When over budget, keep payoff `reveal` and `stinger`, drop `tick`, then drop `cut`. Write the dropped ids into `edit/audio/sfx-dropped.json` so the agent can explain them.

5. Measure attack at resolve time and store it on the event. The mix stage from phase 4 consumes it.

6. Gains are per kind, in dB, applied before the final loudnorm. Acceptance includes a synthetic render where the SFX peak is below the voice peak (compare `astats` on each stem, not on the loudnormed mix).

7. Library contents wait on the license decision (section 6). The code lands with the manifest and a test tone per kind in `tests/fixtures/sfx/`, not with downloaded packs.

**Files:** `brand/sfx/manifest.json`, `helpers/audio.py`, `helpers/render.py`, `SKILL.md`, `tests/test_sfx_resolve.py`, `tests/fixtures/sfx/`.

**New dependencies:** none. Audio files are assets, not packages.

**Acceptance:**

- A three-range EDL produces `cut` events at the two internal boundaries and a `transition` or none at the intro join, according to the theme.
- A `reveal` event becomes an `sfx` entry whose `at` is earlier than the visible time by the fixture's known attack.
- Over-budget events drop in the documented order.
- Resolved SFX go through the phase 4 mix (`normalize=0`, video copy, loudnorm last).
- No SFX file is committed unless its license file is committed next to it.

**Risks:**

- Stock whooshes on every cut are the failure mode the skill already names. The density cap is the mitigation; do not "fix" a quiet video by removing the cap.
- Stereo SFX against a mono voice stem need an explicit channel layout in the graph. Downmix SFX to the voice layout before `amix`.

### Phase 8 — Music and ducking

**Effort:** M

**Goal:** A bed under the whole piece, quieter by a measured 12–15 dB while the voice is present, ramped out before the outro stinger, then loudnormed with everything else.

**Why now:** Ducking needs the voice envelope and the mix pass from phase 4. It should see the SFX stem too, so the master measurement in phase 9 is the real mix rather than a temporary one. Music does not depend on infographic templates, but putting it after SFX avoids tuning ducking twice.

**Tasks:**

1. Theme or EDL selects a bed id. File resolution is `brand/music/manifest.json` (id, file, gain_db, loop). Beds are instrumental. The resolver loops or trims to the output duration, with a short fade-in at 0 and a fade-out that finishes at the outro start (not at the end of the file's own tail).
2. Implement the phase 4 ducking parameters for real: while voice RMS is above threshold, music gain is `gain_db + duck_db` with `duck_db` defaulting to −13 (the middle of the skill's −12 to −15 window). Attack 80 ms, release 400 ms, both theme-overridable. While the voice is silent (gaps, intro), music sits at `gain_db`.
3. Calibrate on a fixture: 4 s of voice tone, 8 s of bed. Measure integrated loudness of the music stem alone in the voice window and in the gap. The voice-window reading is 12–15 dB below the gap reading. Adjust the automation if it misses; do not switch the acceptance to "sidechaincompress is present".
4. `SKILL.md` music section: the agent offers the beds in the manifest and waits. It does not generate a bed and it does not claim the mix sounds good. It reports the ebur128 numbers the self-eval already asks for.
5. Default `music.enabled` is false until at least one licensed file is on disk. Same fail-closed rule as the watermark.

**Files:** `brand/music/manifest.json`, `helpers/audio.py`, `helpers/render.py`, `SKILL.md`, `tests/test_music_duck.py`.

**New dependencies:** none.

**Acceptance:**

- Fixture measurement lands in the −12 to −15 dB duck window.
- Music is at `gain_db` during a 2 s silent gap and is ramped out by the outro start.
- The full-mix loudnorm still reports a true peak at or under −1 dBTP on the fixture (or the phase records the ffmpeg measurement and fails the test on a peak over that).
- A render with `music.enabled: false` is bit-identical in its filter graph to the phase 7 graph (no music input).

**Risks:**

- Loop points click. Require the manifest to name files that already loop cleanly, and apply a 50 ms crossfade at the loop join inside the resolver if the bed is shorter than the video.
- Vocal beds fight TTS. The manifest schema has `"vocals": false`. The resolver rejects `"vocals": true` until a later decision.
- Ducking a compressed music master can pump. If the fixture pumps (release bringing the bed back during commas), lengthen the default release before adding a more complex detector. Keep the dB target.

### Phase 9 — Script-to-video, and QC that covers the new stems

**Effort:** M

**Goal:** A script file compiles to a version-2 EDL using the pieces above. The agent skill learns that path. Self-eval checks brand, captions, SFX level, and ducking, not only cut pops.

**Why now:** This phase is composition. Building it earlier would invent a second renderer. Doing the foundations first means the compiler is mostly glue.

**Tasks:**

1. `script.json` (or a markdown file with a tiny front matter; pick JSON so the compiler does not grow a parser):

    ```json
    {
      "language": "vi",
      "title": "Example",
      "beats": [
        {"id": "hook", "text": "…", "visual": null},
        {"id": "point", "text": "…", "visual": "stat"}
      ]
    }
    ```

    `visual: null` means "run the selector". A string must be a catalog id or `custom`.

2. `helpers/compile_script.py` writes `<edit>/`:
    - TTS wav + words, via phase 3, cached.
    - A brand-color plate source of that duration (ffmpeg `color=` plus silent stereo at 48 kHz), registered in `sources`.
    - Ranges covering the narration (one range per beat, edges on word times).
    - Visual overlays from phase 6.
    - Intro, outro, watermark, lower-third from phase 5.
    - Audio events for phase 7 and the music id from phase 8.
    - `edl.json` version 2, then the normal render.

3. Footage path stays. `compile_script.py` is a sibling of `render.py`, not a mode flag that changes extract behavior for camera files.

4. `SKILL.md` process: if the folder has footage, use the existing inventory path. If the folder has `script.json` and no camera media, compile. Confirm the strategy (language, voice id, template choices, bed id, runtime) before synthesis when the text is new. Cache hits may render without a new confirm.

5. Extend the self-eval notes:
    - Sample a frame in the intro, on a content beat, and on the outro. Watermark present only where the theme says. Captions inside the safe band. Diacritics visible (the agent looks at the timeline PNG; a missing glyph usually shows as a box).
    - `ebur128` on the voice stem, the music stem, and the full mix, for a voice section and a music-only section. Fail the eval if ducked music is not about 12–15 dB down from its dry level, or if an SFX stem's peak exceeds the voice stem's peak.
    - `ffprobe` duration matches `total_duration_s` within 0.1 s.

6. `timeline_view.py --edl` can stay unimplemented. Do not block this phase on a full timeline UI. Optional small addition: draw event ticks if the EDL is passed and a transcript exists. Only if it stays an S-sized change; otherwise leave it.

**Files:** `helpers/compile_script.py`, `SKILL.md`, `README.md` (short "generate from a script" usage, after the footage path), `tests/test_compile_script.py`.

**New dependencies:** none beyond the optional TTS extra from phase 3.

**Acceptance:**

- A two-beat fixture script, fake TTS provider, and brand features off produces an EDL whose ranges, word-timed captions, and one selected visual match the fixture exactly.
- The same compiler pointed at a directory of camera files is not the path `SKILL.md` tells the agent to use (the footage steps remain).
- A dry run (`--plan`) prints voice id, template ids, SFX kinds, and music id without calling ffmpeg or the network.

**Risks:**

- Plate videos plus many short overlays will be slower than a single HyperFrames composition. That is acceptable for v1. If render time becomes the pain, a later phase can bake all graphics into one overlay. Do not start there.
- The agent may still hand-author every slot because that is what `SKILL.md` teaches today. Phase 9 has to rewrite that section so the catalog is the default and custom slots are the exception.

## 5. TTS research

Checked against vendor docs and current model cards on 2026-10-23. Prices move. Azure's public pricing page currently prints "$-" and tells you to use the calculator; the free tier on that page is concrete (0.5 million neural characters per month). Google's prices below are from the Cloud TTS pricing page. Re-check before anyone budgets a year of uploads.

What this codebase needs from a provider, in order: word timestamps in a form we can convert to seconds, a real Vietnamese voice and a real English voice, a commercial license that covers a monetized channel, and an API we can call from `helpers/` without a GPU. Naturalness matters, and it is the thing a 30-second listening test decides.

Worked cost example, 12,000 characters (roughly an 8–12 minute tech script, depending on language):

| Provider | Published unit price | That script | Word times | Vietnamese | License for a monetized channel |
| --- | --- | --- | --- | --- | --- |
| Azure Speech, standard neural (`vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`; also `vi-VN-Linh:MAI-Voice-2-Flash`) | Free 0.5M chars/month, then a paid per-1M rate the calculator must confirm. The long-standing public list price for standard neural was about $16/1M; do not budget from memory. | A few cents at $16/1M, inside the free tier while prototyping | SDK word-boundary events for Azure voices. Confirm on the vi-VN standard voices with the phase 3 probe. OpenAI voices hosted by Azure do not emit them | Dedicated `vi-VN` voices, plus SSML `lang` for English tokens inside a Vietnamese line | Azure speech terms. The straightforward commercial option |
| Google Cloud Neural2 | $16 / 1M chars after 1M free / month. `vi-VN` Neural2 voices exist | about $0.19 | SSML `<mark>` timepoints on the classic SSML tiers | Dedicated Vietnamese Neural2 voices | Google Cloud terms |
| Google Cloud Chirp 3 HD | $30 / 1M after 1M free / month. `vi-VN` is in the language list | about $0.36 | The published Chirp 3 HD SSML tag list has no `<mark>`. Plan on a forced aligner | Dedicated Vietnamese HD voices, 30 speaker styles | Google Cloud terms |
| Google Cloud WaveNet / Standard | $4 / 1M after 4M free / month | about $0.05 | Mark timepoints | Vietnamese standard voices exist; they sound older than Neural2 / Chirp | Google Cloud terms |
| OpenAI speech API (`tts-1`, `tts-1-hd`, `gpt-4o-mini-tts`) | Token pricing on the current guide; those three model ids are deprecated and scheduled to shut down on 2027-01-06, with migration toward a Realtime model | Same order of cents, and the API shape is changing | Audio only. Align afterwards | Whisper's language list includes Vietnamese. The voices are optimized for English, so Vietnamese is a generalization, not a locale voice | OpenAI API terms, until the shutdown date |
| edge-tts | $0 | $0 | WordBoundary messages in the stream, same voice names as Azure (`vi-VN-HoaiMyNeural` and others) | Those same locale voices | Wrapper is a client of an undocumented Edge read-aloud endpoint. Fine as a dev fallback. A weak publish dependency: it can break or violate the service terms without a contract |
| Kokoro-82M | Local compute | $0 marginal | No native word times. Needs alignment | Official model covers a handful of languages (English and several others) and does not include Vietnamese. Community Vietnamese checkpoints exist; read that checkpoint's model card and training-data license before using one. Some official training data requires attribution (CC BY) | Apache-2.0 for the official weights, plus attribution where the card says so |
| Piper | Local CPU | $0 marginal | No native word times | Community `vi_VN` voices exist. Each voice has its own data license; some are non-commercial | Original rhasspy/piper was MIT and was archived in October 2025. The maintained engine, OHF-Voice `piper1-gpl`, is GPL-3.0. Usable commercially, awkward to embed in a closed tool. Voice licenses still vary |
| XTTS v2 (Coqui) | Local GPU | $0 marginal | No native word times | Not in the official language set (that set is the usual European set plus a few Asian languages, and it does not include Vietnamese) | Coqui Public Model License: non-commercial, and the generated audio is restricted too. Coqui shut down in January 2024 and no longer sells a commercial license |
| F5-TTS | Local GPU | $0 marginal | No native word times | Official checkpoints are English and Chinese. Vietnamese finetunes exist and often carry the same non-commercial weight license, or an unclear one | Code is MIT. The published weights are CC-BY-NC. The audio inherits the non-commercial term |

### Recommendation

Default provider: **Azure Speech, standard neural**, behind `synthesize()`.

Reasons that are specific to this repo:

- Word-boundary events line up with the Scribe word JSON that captions, cuts, and overlay timing already consume. Chirp 3 HD and OpenAI do not give that natively. A nicer waveform that then needs a second alignment model will drift, and drift breaks hard rules 5 and 6.
- `vi-VN` has its own voices, and SSML can pronounce an English product name inside a Vietnamese sentence. Kokoro's official checkpoint and XTTS's official language list do not cover that mix. Piper's Vietnamese voices are a quality and licensing patchwork.
- The commercial terms are a contract, which XTTS and F5 weights are not. edge-tts is the same voices without the contract; keep it as the dev adapter.
- A 10-minute video is well inside the free monthly character grant while the pipeline is being built. Paid cost stays in cents per video at the historical neural rate.
- Integration is a Python extra on top of `requests`-era install. No GPU on the render machine. The heavy local models also need an aligner, so they are two new systems rather than one.

Use Google Chirp 3 HD as the planned alternate if a blind listening test prefers it for Vietnamese. The adapter would synth phrase by phrase and align. Do not make it the default until that aligner is part of the same phase, because captions are the product.

Use Kokoro later as an optional local English preview provider if Azure latency or cost ever matters. It is not the default, because this channel asked for Vietnamese and English together.

Leave XTTS and F5-TTS off the implementation list for published videos. The weight licenses do not cover a monetized channel, and the companies do not offer a clean way to buy that right.

OpenAI is a poor default for a pipeline we will still be running after 2027-01-06, and it does not return word times. Revisit only if a future speech model on that API grows timestamps and a Vietnamese locale voice.

Scribe stays the footage STT. Replacing it is not required for any phase above. `SKILL.md` already rejects local Whisper on CPU as the footage transcriber because it is slow and it normalizes fillers.

Voice cloning (Azure personal voice, or a MIT local cloner such as Chatterbox for English) is out of these phases. Add it as another `synthesize()` implementation after the stock voice is in production and the owner has a consent recording he is willing to ship.

## 6. Open decisions

Each one blocks a specific phase. None of them block writing phase 1's schema.

### 6.1 Which TTS provider is the default?

| Option | What you get |
| --- | --- |
| A. Azure standard neural | Locale voices for Vietnamese and English, word-boundary events, commercial terms, free tier for development. Recommended. |
| B. Google Chirp 3 HD | Strong HD voices including `vi-VN`, higher published price, no mark-level timestamps in the current SSML list, so we add an aligner. |
| C. Google Neural2 | $16/1M published, `vi-VN` voices, mark timepoints, a step down in naturalness from Chirp. |
| D. OpenAI speech models | Easy HTTP, English-first voices, no word times, current model ids shut down 2027-01-06. |
| E. edge-tts | $0 and the Azure voice names, unofficial endpoint. Dev only. |
| F. Kokoro or Piper locally | $0 and offline. Official Kokoro has no Vietnamese. Piper's Vietnamese quality and per-voice licenses are the problem. GPL-3.0 on the maintained Piper engine. |
| G. XTTS or F5-TTS | Cloning quality, non-commercial weights. Not for this channel. |

**Recommendation:** A, with E as a dev fallback behind the same interface, and B as the listening-test challenger. Phase 3 ships A and E. B is a later adapter only if you prefer the Chirp sample.

**Needs from you:** an Azure Speech resource key and region, or a "use edge-tts until I have one". And a 60-second listen of `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`, and one English voice (`en-US-AndrewNeural` is only a placeholder) before `speech.json` is treated as final.

### 6.2 Vietnamese, English, or both?

| Option | Consequence |
| --- | --- |
| A. One primary language per video, chosen in `script.json` | Clean captions, one voice, one chunker. A Vietnamese video may still contain English tokens via SSML. Recommended. |
| B. English narration only | Simplest captions (today's chunker). Drops the Vietnamese requirement. |
| C. Vietnamese narration only | Use the `sentence` chunker. English videos stay on the footage path with Scribe. |
| D. Two full narrations of every video | Two renders, two mixes. Later. The compiler can grow a language loop after one language works. |

**Recommendation:** A. Default `language` in the example speech config can be `vi` if that is the channel's main spoken language; say so and we set it. Until you say so, the example uses `vi` because that is the harder requirement and the one the English-only tools fail. Change the default in `speech.json` without a code change if the channel is actually English-first.

**Needs from you:** which language a typical upload is spoken in, and whether on-screen captions match the narration or are translated. Translation is a different pipeline (we would caption in a language we did not synthesize) and is not in these phases.

### 6.3 Stock voice or a clone of your voice?

| Option | Consequence |
| --- | --- |
| A. Stock neural voice | Ships inside phase 3. Sounds like a narrator, not like you. Recommended for v1. |
| B. Azure personal voice | Your timbre, extra enrollment and consent, limited access, different price. A later adapter. |
| C. Local clone | English is feasible with a MIT cloner. Vietnamese clones add a finetune and a license review. Not in v1. |

**Recommendation:** A. Record the listening samples, pick the vi voice and the en voice by ear, and only then talk about a clone. A clone still has to emit the same word JSON, so it does not change the later phases.

### 6.4 Keep Scribe for footage?

| Option | Consequence |
| --- | --- |
| A. Keep Scribe | Diarization, audio events, verbatim fillers, the cache you already have. Recommended. |
| B. Replace with local Whisper / PhoWhisper | Drops the ElevenLabs key for footage. Loses the filler and audio-event behavior the skill is built around, and CPU Whisper is already listed as an anti-pattern. |

**Recommendation:** A. TTS work does not require touching Scribe. If you want the key gone anyway, that is a separate project with its own accuracy check on a real take.

### 6.5 Music source and license

| Option | Consequence |
| --- | --- |
| A. You supply 2–3 instrumental beds you already have the right to post on YouTube, TikTok, and anywhere else you publish | Manifest entries point at the files. Recommended. |
| B. A subscription library (Epidemic Sound, Artlist, or similar) | You confirm the license covers those platforms and monetization. We store files locally, not in git, unless the license allows redistribution. |
| C. CC0 beds | Rarely as polished. Fine if you find ones you like. |
| D. Generative music (Suno, Udio, and similar) | Only with a written commercial grant from the plan you pay for. Contested licenses stay out of the repo. |

**Recommendation:** A or B. The repo gets `brand/music/manifest.json` and a `.gitignore` for the audio. You drop files on the machine that renders. Vocals off. Phase 8 stays dark until the first file is real.

**Needs from you:** the files, or a subscription export, plus a one-line note of where they may be published. Two contrasting beds are enough (a calm explainer, a slightly driven one). The skill already says to offer two and let you listen.

### 6.6 SFX source and license

| Option | Consequence |
| --- | --- |
| A. A small CC0 set (Kenney interface sounds, Freesound CC0, or your own recordings) mapped to cut, transition, reveal, tick, impact, stinger | We can commit the WAVs and a `LICENSE` file beside them. Recommended starter. |
| B. A paid pack | Same manifest, files gitignored, you keep the receipt. |

**Recommendation:** A for the six roles, replaced later by swapping files. One clip per role is enough. Phase 7's density cap matters more than the size of the pack.

**Needs from you:** a yes on CC0-in-repo, or a pack you prefer. Also a yes/no on whether cut SFX should be on by default or only when the strategy asks. Recommendation: off for documentary footage, on for generated explainers (`theme.sfx.preset: "generated"`).

### 6.7 Brand assets

The implementation can paint rectangles and type without these. It cannot put your mark on screen until they exist.

| Asset | Notes |
| --- | --- |
| Logo PNG with transparency, about 1024 px on the long side | Required for the watermark and the intro. SVG source beside it is welcome and is not what ffmpeg reads. |
| 3–5 hex colors: background, surface, text, accent, optional second accent | Required before `brand/theme.json` replaces the example. Do not invent a palette in code. |
| On-screen handle | One of `@dantech0xff` and `@dantech-0xff`, or both in different corners. The theme has a single `lower_third.handle` and an outro line list. |
| Font preference | Default plan bundles Be Vietnam Pro and JetBrains Mono (both OFL, Vietnamese coverage, redistributable). If you have a commercial face, you also need an embed license. Otherwise we do not wait. |
| Watermark policy | Recommended: top-right, about 160 px wide, opacity 0.85, hidden on intro and outro. Say if you want it off on long-form and on for shorts only. |
| Intro and outro length | Recommended: 2.5 s intro (logo), 3.5 s outro (name, handle, nothing else). |
| Lower-third | Recommended: "Dan Tech" plus the chosen handle, first 4 s of the first content beat, bottom-left, clear of captions. |

**Recommendation:** bundle the OFL fonts now, and block only the logo-on switch on the PNG and the five colors. Send those whenever you have them; phases 1–4 and 6–9 can be built against the example theme with brand features turned off.

### 6.8 Frame format

| Option | Consequence |
| --- | --- |
| A. 1920×1080 at 30 fps for generated videos | Matches a tech explainer. Theme default. Recommended for v1. |
| B. 1080×1920 shorts | Safe zones and the lower-third already have to be tested here because footage can be vertical. A generated-shorts profile is a second theme, not a crop of A. |
| C. Both from one timeline | Two layouts per template. After the landscape catalog looks right. |

**Recommendation:** A for `compile_script.py`. Footage keeps the source orientation, as `render.py` does today. Add a shorts theme after the landscape templates pass the safe-rect tests.

### 6.9 Infographic engine

| Option | Consequence |
| --- | --- |
| A. Pillow frames + ffmpeg for the catalog | Already installed, deterministic, theme fonts via file path, no Node. Recommended. |
| B. HyperFrames or Remotion for every line | Heavier, better motion, another runtime (Node 22 for HyperFrames), and a failure mode where a web font falls back. |
| C. Manim for every line | Right for equations, slow and wrong for a lower-third and a stat card. |

**Recommendation:** A for the catalog, with the existing custom-slot escape hatch for B and C when a beat actually needs them. One catalog engine, otherwise the accent color and the type ramp drift per slot.

### 6.10 Where config lives

**Recommendation:** `brand/theme.json` and `brand/speech.json` in this repo are the channel defaults. `<edit>/theme.json` replaces the theme for one session when present. Secrets stay in `.env` and out of both JSON files.

No other placement is worth a fork in the code. Per-video voice or language overrides belong on `script.json`, not in a third config.

## 7. Suggested build order once this plan is accepted

1. You answer 6.1 (provider), 6.2 (language), and 6.7 (colors and logo, even roughly). The rest have recommendations that can ship as defaults.
2. Phase 1, then 2. Footage captions can use the new styles before any TTS key exists.
3. Phase 3 probe (the 10-second boundary dump) before the rest of phase 3. If the Vietnamese voice does not emit boundaries, the plan's fallback is already written; we do not discover it after captions are wired.
4. Phases 4, then 5 and 6. Phase 5 and phase 6 can be split across two changes; 6 depends on 5's safe rect.
5. Phases 7 and 8 after the asset decisions 6.5 and 6.6. The code can land with test tones earlier.
6. Phase 9 last, then one real script rendered end to end and listened to. The self-eval numbers go into `project.md` for that session.

Out of scope until the above is in: talking-head avatars, automatic stock B-roll, translated subtitles, voice cloning, replacing Scribe, and a timeline GUI.
