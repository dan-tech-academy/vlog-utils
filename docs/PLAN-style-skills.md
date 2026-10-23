# Talking-head explainer — one finished skill

Planning only. This file is the design. Nothing in `helpers/` or `skills/` changes until the owner approves it.

- Repo: `dan-tech-academy/video-use`
- Branch: `feat/style-skills`, cut from `main` at `b75c1dd` (the squash of PR #1)
- Date: 2026-10-23
- Audience: Dan Tech (`@dantech0xff`) and whoever implements it

The goal of this work is one style skill, done completely and to a high standard: the talking-head explainer. It is not a platform, and it is not the first of several styles built in parallel. The skill is finished only when the definition of done below is true. A landscape-only cut, a fixture that never leaves the test suite, or a core that could host four future styles does not count.

The owner opens an agent (Claude Code or Codex) in a folder that already holds the assets, invokes `style-explainer`, and the agent analyzes that folder and finishes a polished video. The delivery is portrait 9:16 (1080×1920) unless the prompt asks for landscape 16:9 (1920×1080). The picture comes from those assets plus the channel brand, type, and composable visual primitives. The bed is a file in the folder or, if there is none, one track from the built-in music library. SFX come from the CC0 set already in the repo.

What appears on screen is chosen per segment from what that sentence means. The skill sets taste and limits. It does not set a template sequence.

Scope is the footage and pre-recorded-audio path. `compile_script.py` and Azure / edge-tts narration stay in the repo and are not part of this work. This skill does not synthesize a voice.

## Definition of done

The skill is done when every line below is true. Partial credit does not close the work. A phase can land in git before this list is complete. The skill is not complete until the list is.

1. **Real folder, both deliveries.** From a real asset folder (one or more talking-head takes, optional b-roll, photos, a voice file, music, SFX — nothing synthesized), an agent following `skills/style-explainer/SKILL.md` produces `edit/final.mp4`. With no orientation in the prompt, that file is 1080×1920. When the prompt asks for landscape, a second file is 1920×1080. The owner can watch both. The landscape file is the same editorial cut, not a second script.
2. **Context-driven visuals.** `edit/visual_plan.json` exists for each delivery. Every segment names an intent, a treatment composed of primitives (or an explicit clean face), the on-screen text or data, and a rationale tied to the words in context. The checker accepts the plan. The same footage with a different transcript yields a different plan and a visibly different picture (acceptance test in section 3.10).
3. **Captions.** Sentence-length ASS, Be Vietnam Pro, spoken case, diacritics intact, inside the safe band for that orientation. Subtitles are the last filter.
4. **SFX.** Jump cuts are dry. Any effect that fires is one the visual plan named, from the CC0 set or a same-named file in the folder, inside the density cap. A folder with no SFX files still finishes.
5. **Music.** A music file in the folder is the bed and ducks under speech. With no file in the folder, the bed is one track from the built-in library, chosen from the piece's mood and energy and named in the plan. The skill does not generate music.
6. **Brand.** Lower-third shows "Dan Tech" and `@dantech0xff` for the short window in section 3.5. Watermark, intro, and outro stay off. Colors and fonts come from `brand/theme.json`, including the labeled placeholders.
7. **Self-eval loop.** The agent runs the checklist in section 2.4 and writes what it saw in `edit/project.md`. It stops when the checks pass. It stops early when a new pass leaves the same failures. It will not render more than `self_eval.max_passes` times (default 3). Anything still wrong is listed for the user along with the preview. A failed relevance check changes the visual plan. It does not swap in a keyword-mapped card.
8. **Docs.** Core `SKILL.md` tells a styled run to follow this skill. `skills/style-explainer/SKILL.md` is enough to run the edit without this plan open. `install.md` registers the core and this one skill.
9. **Tests and fixture renders.** The suite in section 3.10 is green without a network call: inventory, plan check, reframe, both frame sizes, the two-transcript difference, captions, a dry cut, music absent and music present. Sample frames from the fixtures are kept with the test output so a reviewer can see the card, the face, and the portrait crop.

"Polished" means those nine lines, not a separate grade. A file that is the right size and the wrong graphic has failed item 2.

## Design principle — visuals follow the words

Effects, imagery, layout, animation, and on-screen information are chosen for each segment from the meaning of what is said there, in the context of the segments around it.

The explainer skill is taste and guardrails: pacing range, the channel palette and brand, typography, energy, density, and a short do/don't list. It names no sequence of templates and no rule of the form "a digit always becomes the stat card."

The agent does that choice in the creative-direction step (section 2.5). It writes `edit/visual_plan.json`. `helpers/check_visual_plan.py` enforces the guardrails and the orientation safe zones. It does not pick a substitute template. Render bakes the plan. Self-eval checks that each graphic is still about the words under it.

`helpers/visuals/select.py` maps keywords onto a closed catalog. That map is a hard-wired director. This skill does not call it. Drawing code in the catalog may remain as a primitive the plan names by id. Whether a graphic runs, and which primitives compose it, stays with the transcript.

## Locked for this plan

| Topic | Decision |
| --- | --- |
| Scope | One skill, the talking-head explainer, finished to the definition of done. The core is only what that skill calls. |
| Visuals | Decided per segment from the spoken meaning. The skill sets guardrails only. |
| Orientations | Both work. Default is portrait 1080×1920. Landscape 1920×1080 only when the prompt asks for it. |
| Face crop | The agent looks at `timeline_view` frames and writes a crop. No face-detection library. See section 3.4. |
| Music | A file in the folder wins. Otherwise the agent picks one bed from `brand/music/` by the piece's mood and energy. |
| Self-eval | Stop when the checks pass. Stop early when a pass changes nothing. Hard cap defaults to 3 and is configurable. Leftover issues go to the user with the preview. |
| Core vs skill | One engine and the core `SKILL.md`. This skill is `skills/style-explainer/SKILL.md` plus `style.json`. It does not fork `render.py`. |
| Speech source | Camera audio, or a voice file already in the folder. No TTS. |
| Channel look | `brand/theme.json` still owns colors, fonts, and the handle. Colors stay the labeled placeholders. |
| Logo | Watermark and intro stay off until `brand/logo.png` exists. |

Effort key:

| Size | Meaning |
| --- | --- |
| S | One module or a thin adapter, unit-tested, no new runtime |
| M | A new module plus a render-path change, fixtures, and skill text |
| L | A subsystem this skill needs: schema, agent contract, render integration, and a fixture render |

## 1. What already exists

The engine on `main` is an agent skill plus Python CLIs. The model reads a packed transcript, writes an EDL, and `helpers/render.py` makes the MP4. Session files stay in `<videos_dir>/edit/` (core hard rule 12).

This skill calls these pieces and does not rewrite them except where section 5 names a hook:

| Piece | Role today |
| --- | --- |
| `SKILL.md` | The only editing skill. Hard rules, inventory-by-hand, EDL, self-eval. It tells the agent not to assume a video type. |
| `install.md` | Symlinks the whole repo to `~/.claude/skills/video-use` or `~/.codex/skills/video-use`, so `SKILL.md` and `helpers/` stay siblings. |
| `helpers/transcribe.py` | ElevenLabs Scribe, word timestamps, diarization, audio events. Cache `edit/transcripts/<stem>.json`. Model id `scribe_v2`. |
| `helpers/pack_transcripts.py` | Phrases on silence ≥ 0.5 s or a speaker change. |
| `helpers/render.py` | Extract, 30 ms fades on voice segments, lossless concat, overlays, subtitles last, optional v2 mix, loudnorm last. |
| `helpers/audio.py` | v2 mix, SFX resolve, music duck (−13 dB, 80 ms attack, 400 ms release). |
| `helpers/brand.py` | `layout_boxes`: caption band, lower-third above it, watermark corner. |
| `helpers/visuals/` | Closed catalog drawn as full-frame opaque plates, chosen by keyword. The keyword map is not the director. Plates hide a talking head, so a graphic in this skill is an alpha card. |
| `brand/theme.json` | Frame default 1920×1080, mode `source`. Caption margin 90. Music off. SFX preset `generated`. |
| `brand/sfx/` | CC0 clips: cut, transition, reveal, tick, impact, stinger. |

Two engine facts shape the skill:

- `frame.mode: source` keeps orientation. `force` letterboxes into the theme size. Neither crops a 16:9 frame to 9:16, and neither follows a face.
- Catalog cards are opaque full-frame videos. On a talking head they hide the person.

Hard rules stay in the core. This skill cannot move subtitles earlier, cut inside a word, loudnorm before the mix, or write output into the repo.

## 2. Core, scoped to this skill

The core is the engine plus `SKILL.md`, extended only where the explainer cannot finish without the extension. A general style framework is out of scope. There is no plugin loader, no second preset, and no registry beyond the core and this one skill.

Built because the explainer needs it:

- Inventory of `talking_head`, `broll`, `photo`, `voice`, `music`, `sfx`, plus `ambiguous` when a file is unclear.
- A visual-plan schema and a checker for this skill's guardrails and safe zones.
- A per-range crop field, applied in extract, holding the window the agent chose by looking at the frames.
- Alpha-card overlay so a graphic can sit beside or under the face.
- One symlink in `install.md` for `skills/style-explainer`.

Left as they are: Scribe, pack, EDL v1/v2, concat, the 30 ms fades, subtitles last, the mix graph, loudnorm, `brand/theme.json`, the CC0 set, `compile_script.py`.

```
folder of assets
    → inventory (classify; Scribe only what can hold speech)
    → takes_packed.md
    → style-run.json (orientation, chrome) and the editorial cut
    → creative direction: visual_plan.json, one entry per segment
    → check guardrails and safe zones
    → render.py bakes that plan (the agent's crop, when a 16:9 source is delivered as 9:16)
    → mix, loudnorm
    → self-eval, including whether the graphics still match the speech
    → edit/final.mp4
```

### 2.1 Asset inventory

New module `helpers/inventory.py`. It writes `<edit>/inventory.json` and does not move or rename the owner's files. It ignores `edit/`, dotfiles, and anything under the video-use repo.

Classification is deterministic. The agent reads the result and looks at a `timeline_view` only when a file is marked `ambiguous`. Folder names win when the file lives in a directory named `voice`, `music`, `sfx`, `broll`, `photos`, or `screen`. `screen` is filed as `broll` for this skill: the explainer does not have a screen-recording mode.

Probe every file with `ffprobe` (duration, size, fps, audio stream, rotation). Then:

| File | Role |
| --- | --- |
| Image (png, jpg, webp) | `photo` |
| Audio under 3 s, or a file in `sfx/` | `sfx` |
| Audio in `music/`, or audio-only longer than 20 s with no speech once transcribed | `music` |
| Other audio-only | Transcribe. Speech ratio > 0.40 → `voice`. Speech ratio < 0.05 and duration > 20 s → `music`. Else `ambiguous`. |
| Video in `broll/` | `broll`, after a transcript if it has audio. |
| Video with an audio stream | Transcribe. Speech ratio > 0.45 → `talking_head`. Speech ratio < 0.15 → `broll`. Between those → `ambiguous`. |
| Video with no audio | `broll` |

Speech ratio is voiced time divided by duration, from the Scribe words. A video the agent must look at stays `ambiguous` until a `timeline_view` of the middle 4 s is enough to pick `talking_head` or `broll`. The agent writes that choice back into `inventory.json` with `"source": "look"`. The classifier does not load a face model. Face geometry belongs to the portrait reframe.

Scribe is not called on `music/` or `sfx/`. An unlabeled audio file is transcribed only when it is the candidate voice or the audio of a video. If the folder has one unlabeled audio file and no video with speech, the agent asks once whether it is the voice or a bed, then records the answer.

`inventory.json` entries: `path`, `role`, `duration_s`, `width`, `height`, `fps`, `has_audio`, `speech_ratio`, `transcript` (path or null), `source` (`probe`, `folder`, `scribe`, `look`, `ask`).

### 2.2 Transcription, EDL, render, mix

Transcription stays `transcribe_batch.py` / `transcribe.py` on the files inventory marked for Scribe. Cache key is unchanged: one JSON per source stem under `edit/transcripts/`. `pack_transcripts.py` still builds `takes_packed.md`.

The EDL stays version 2 when the edit has SFX, a separate voice file, or a music bed, and version 1 when the camera audio is the whole soundtrack and no SFX fire. Ranges still snap to word edges. Caption time is still `word.start - segment_start + segment_offset`. Overlay in and out points come from the visual plan, snapped to the same word edges.

`render.py` remains the only compositor. This skill does not shell out to its own ffmpeg graph. Mix and loudnorm stay where they are: overlays silent, `amix=normalize=0`, loudnorm last at −14 LUFS / −1 dBTP / LRA 11.

When the voice is a separate file, the v2 mix uses that file as `audio.voice` and the picture's audio is not the voice. B-roll audio is dropped in that case, so a room tone under a recorded voice does not fight the take. When the voice is the camera audio, the concat stem is the voice and `audio.voice` is omitted.

For that run only, the in-memory theme takes its frame size from `edit/style-run.json`. Colors, fonts, handle, and the placeholder flag stay on the channel theme. An `<edit>/theme.json` still replaces the channel file wholesale if the owner put one there. The run's frame then wins over that file's frame, so a portrait delivery does not require a second palette.

### 2.3 The one contract

```
skills/style-explainer/
  SKILL.md      how to cut, how to direct the picture, what to ask
  style.json    machine-checked guardrails for this skill only
```

`style.json` is validated by `helpers/style.py` against `skills/style.schema.json`. Unknown keys fail. The schema describes this skill's fields. It is not a vocabulary for other styles.

The agent-facing contract:

1. `skills/style-explainer/SKILL.md` starts by requiring a read of the core `SKILL.md` and of its own `style.json`.
2. The agent writes `edit/style-run.json` before the plan: `style` (`explainer`), `orientation` (`portrait` unless the prompt asked for landscape), `chrome` (`clean`, or `shorts` when the prompt says Shorts, TikTok, or Reels).
3. The agent writes `edit/visual_plan.json` (section 2.5), then `edl.json` whose overlays, SFX, and frame match that plan.
4. `helpers/check_visual_plan.py` reads the inventory, `style.json`, the run file, the packed words, and the plan. It exits non-zero with the field name when a guardrail or a safe zone is broken. It does not reject a plan for using an "unexpected" graphic on a sentence that contains a digit. Relevance rules are in section 2.5.
5. Render runs only after the check passes.

`style.json` fields this skill uses:

| Field | Meaning |
| --- | --- |
| `id`, `title` | `explainer`, "Talking-head explainer". |
| `language` | `vi`. Caption chunking uses it. |
| `frames` | `landscape` and `portrait`: width, height, `margin_v`, caption size. |
| `chrome` | `clean` (default) and `shorts` insets. |
| `captions` | Style id `sentence`, font role `body`. |
| `pacing` | Pad window, silence cut, max hold, filler policy, b-roll length, hook window. |
| `energy` | `measured`. The face is the picture. Graphics are rare and earned by the words. |
| `guardrails` | Density, minimum clean-face gap, no identical treatment back to back, do/don't. |
| `primitives` | The vocabulary the plan may compose. Not a sequence. |
| `sfx` | Jump-cut effects off. Which kinds exist. Density cap (the core cap still applies). |
| `music` | Folder file wins. Otherwise one library id. Duck numbers when a bed plays. |
| `self_eval` | `max_passes`, default 3. The loop still stops earlier when the checks pass or a pass changes nothing. |
| `brand` | Lower-third on. Watermark, intro, outro off. |
| `requires` | `talking_head` must be ≥ 1 or the run stops. |
| `optional` | `broll`, `photo`, `voice`, `music`, `sfx`. |
| `missing` | `talking_head` → stop, with a sentence. No synthesized speech. |

### 2.4 Self-eval

The core checklist still applies: `timeline_view` on the rendered file at every cut, caption readable and inside the safe band, diacritics drawn, `ffprobe` duration within 0.1 s of `total_duration_s`, `ebur128` on the mix. The agent still cannot claim the mix sounds good. It reports the numbers.

The loop stops on purpose, not on a magic third try:

- The number 3 is the original video-use rule. `SKILL.md` says "Cap at 3 self-eval passes — if issues remain after 3, flag them to the user rather than looping forever." The README draws the same cap. Nothing in the repo measures that edits stop improving at pass 3. Each pass is a full re-render plus a filmstrip at every cut, so the cap is a cost stop. The sentence that mattered, and that this plan had shortened away, is the flag-to-the-user part.
- Stop as soon as the checks pass. Unused passes do not run.
- Stop early when a pass leaves the same failures as the pass before it. Another render will not invent a new idea.
- `style.json` `self_eval.max_passes` is the hard backstop. Default 3, the same number as the core, so a long explainer cannot wander into five full renders. A run may set it lower. It may not set it to unlimited.
- When the loop stops with failures still open, `edit/project.md` lists them with timecodes and the preview is shown anyway. The core line "only present the preview once the self-eval passes" hides a file the owner needs to see. The issues travel with the file.

This skill adds:

- Every on-screen string is grounded in that segment's quote (section 2.5).
- A data graphic is absent when the quote has no datum.
- The face the plan promised to leave visible is still visible. Eyes are not under a card.
- Portrait: `edit/reframe.json` matches the crop the agent wrote (`source: look` or `source: center`), and the rendered frame shows that window.
- `edit/project.md` records each pass: what failed, what changed in the plan, the loudness numbers.

### 2.5 Creative direction

After the cut is chosen, and before `edl.json` overlays are written, the agent directs the picture.

1. Split the kept speech into segments on sentence or beat boundaries. Edges snap to words.
2. Read each segment with the topic and with the previous and next segment. Assign one intent: `claim`, `number`, `comparison`, `steps`, `warning`, `joke`, `question`, `story`, `code`, `emphasis`.
3. Compose a treatment from primitives, or mark the segment `clean` (captions only), or mark it `bespoke` when no composition fits. Write why, in one or two sentences that quote or paraphrase the line.
4. Apply variety while composing, not afterwards as a coat of paint: do not repeat the same treatment on the next segment, leave the clean-face gap the guardrails require, and spend a stronger motion on the hook and on the final claim because those lines carry the argument.
5. Write `edit/visual_plan.json`. Run the checker. Revise the plan until it passes. Then compile the EDL from the plan.

A treatment is a bundle of primitives, not a closed template. The plan may set any of these, and may leave one out:

| Primitive | Examples the plan can name |
| --- | --- |
| Text | A short on-screen line, an emphasized word, a terminal line. Caption style stays `sentence` either way. |
| Motion | Hold, fade, slide, count-up, draw-on, punch-in on the face, Ken Burns on a photo. |
| Layout | `side-card` (landscape), `lower-card` (portrait), `split` with a photo, `lower-third`, `clean`. |
| Data | A single figure, a comparison, a step list, a short code block. |
| Overlay | Alpha card, b-roll cutaway, photo still. |
| Transition | Cut, which is the default on the face. |
| Sound | One SFX kind at a payoff word, or silence. |
| Bespoke | A one-off animation rendered with HyperFrames, Remotion, Manim, or Pillow, only when the rationale says why the primitives cannot carry the line. The file lands in `edit/visuals/` and the plan points at it. |

`clean` is a complete treatment. A story or a joke often needs the face and no card.

Two segments have the same treatment when `layout`, `motion`, and `data.type` match (a clean segment's signature is `clean`). The next segment must differ. Two numbers in a row can both be data; they need different motion or layout (count-up, then a comparison). The checker rejects an identical signature on adjacent segments.

`edit/visual_plan.json`:

```json
{
  "style": "explainer",
  "orientation": "landscape",
  "segments": [
    {
      "id": "s3",
      "quote": "nhanh hơn 40%",
      "intent": "comparison",
      "why": "The line contrasts speed and states a percent. The previous line was only setup, so this is the payoff.",
      "treatment": {
        "layout": "side-card",
        "motion": "count-up",
        "data": {"type": "comparison", "before": "trước", "after": "40%"},
        "text": "40%",
        "overlay": "alpha-card",
        "sfx": "reveal",
        "transition": "cut"
      }
    }
  ]
}
```

A clean segment sets `"treatment": {"layout": "clean"}` and still has `intent` and `why`. A bespoke segment sets `"treatment": {"layout": "bespoke", "engine": "pillow", "path": "edit/visuals/s3.mov"}` and the `why` names the missing primitive.

The checker fails the plan when:

- A segment lacks `intent`, `why`, or `treatment`.
- On-screen `text` or a data label is not a substring of `quote`, aside from a shortening the `why` names and whose numerals still occur in the quote.
- `data` is set and the quote contains no number, percent, currency, or explicit contrast (`vs`, `versus`, `so với`, `hơn`).
- Adjacent segments share a treatment signature.
- A graphic starts before the previous graphic's clean gap (`guardrails.min_clean_s`) has elapsed.
- Graphic count in any 10 s window exceeds `guardrails.max_graphics_per_10s`.
- The card rect, computed for this orientation (section 3.5), intersects the caption band, the lower-third while it is on screen, or the face box expanded by 24 px.
- `sfx` names `cut`, or a kind outside `style.json`.
- A library bed is named while the folder already has a `music` file, or the named id is absent from `brand/music/manifest.json`, or that bed's `vocals` is true or its `license` is empty.
- The run is portrait and the frame in the EDL is 1920×1080, or the reverse.
- A range edge falls inside a word.

The checker does not fail a plan because a `number` intent used a comparison layout, or because a `warning` used a punch-in and no card. That choice is the agent's, and self-eval reviews it against the `why`.

### 2.6 How the agent finds the skill

Claude Code and Codex discover a directory that contains a `SKILL.md` with `name` and `description`. The core stays the repo root so `helpers/` remain siblings of `SKILL.md`. This skill is one more directory.

`install.md` links both:

```bash
ln -sfn ~/Developer/video-use ~/.claude/skills/video-use
ln -sfn ~/Developer/video-use/skills/style-explainer ~/.claude/skills/style-explainer
```

The same two links under `${CODEX_HOME:-$HOME/.codex}/skills/`. The skill symlink points at the real directory, so `SKILL.md` can read `../../SKILL.md` and `../../helpers/` through the link.

`skills/index.json` lists the core and `style-explainer` so the core description can name the skill when the user asks for an edit and does not name one. The index is that list, not a loader.

The core description says: a footage edit uses `style-explainer`. The explainer description says: use it for a talking-head tech explainer. Delivery is 9:16 unless the user asks for 16:9. Visuals are chosen from the words. A 16:9 camera is cropped from the filmstrip, not by a face detector.

Core `SKILL.md` keeps the hard rules and the helper list. For a footage run, pacing, frame, graphics, SFX, and music policy live in this skill. `compile_script.py` is documented as a separate tool and is not a step in the run.

## 3. Talking-head explainer

Directory: `skills/style-explainer/`. Skill name: `style-explainer`. Preset id: `explainer`.

A person talks to camera about a technical idea, in Vietnamese or mixed Vietnamese and English, and the edit keeps their face as the A-roll. Fillers and dead air go. Each kept sentence is directed from what it means: a figure may become a card, a warning may become a punch-in, a story may stay a clean face, and the next sentence does not reuse that treatment. Captions are sentence-length in Be Vietnam Pro. Jump cuts stay dry. A music file in the folder is the bed; otherwise the agent picks one instrumental from the built-in library to match the piece. The bed ducks under speech. The default delivery is 1080×1920. A 16:9 camera is cropped to the face by the window the agent reads off the frames. 1920×1080 is rendered only when the prompt asks for landscape.

### 3.1 Inputs

Required: at least one `talking_head` video whose transcript has speech. The camera may be 16:9, 9:16, or another frame. Phone rotation metadata counts, using the same display rotation `is_portrait_source` already trusts.

Optional:

| Asset | Use |
| --- | --- |
| More talking-head takes | Retakes. The cleaner complete sentence wins. False starts go. |
| `broll` | Available to the visual plan as a cutaway when the words need a picture the face does not show. |
| `photo` | Available as a still, made into a silent clip at the run's frame rate. |
| `voice` | Replaces camera audio as the voice stem when the file is present. |
| `music` | Wins over the library. Ducked. |
| `sfx` | A file whose name matches a kind (`reveal`, `tick`, …) overrides the CC0 clip for that kind. |

Missing:

| Gap | Behavior |
| --- | --- |
| No `talking_head` | Stop. Name the missing role. Do not synthesize speech. Photos and a voice file are not a substitute. This skill is a face on camera. |
| No b-roll and no photos | Normal. The plan uses the face, type, and cards. |
| No music in the folder | Pick one bed from `brand/music/` (section 3.8). Do not generate a bed. Do not leave the mix silent. |
| No SFX files | The CC0 set, only kinds the plan names and `style.json` allows. |
| Ambiguous file | One question, then inventory is updated. |

A separate voice file wins over camera audio for the stem. The camera picture stays. If both exist and their durations differ by more than 0.5 s, stop and ask which timeline is the cut. Do not stretch one to the other.

### 3.2 Guardrails

`skills/style-explainer/style.json`:

```json
{
  "id": "explainer",
  "title": "Talking-head explainer",
  "language": "vi",
  "frames": {
    "landscape": {"width": 1920, "height": 1080, "margin_v": 90, "font_size": 22},
    "portrait": {"width": 1080, "height": 1920, "margin_v": 220, "font_size": 28}
  },
  "chrome": {
    "clean": {"top": 120, "side": 64, "right_extra": 0, "bottom_extra": 0},
    "shorts": {"top": 160, "side": 48, "right_extra": 96, "bottom_extra": 120}
  },
  "captions": {"style": "sentence", "font": "body"},
  "energy": "measured",
  "pacing": {
    "pad_ms": [80, 140],
    "cut_silence_s": 0.4,
    "keep_breath_s": 0.15,
    "max_hold_s": 20,
    "broll_s": [2, 5],
    "hook_s": 8
  },
  "primitives": {
    "text": ["line", "emphasis", "terminal"],
    "motion": ["hold", "fade", "slide", "count-up", "draw-on", "punch-in", "ken-burns"],
    "layout": ["clean", "side-card", "lower-card", "split", "lower-third", "bespoke"],
    "data": ["figure", "comparison", "steps", "code"],
    "overlay": ["alpha-card", "broll", "photo"],
    "transition": ["cut"],
    "sfx": ["reveal", "tick", "impact"]
  },
  "guardrails": {
    "max_graphics_per_10s": 2,
    "min_clean_s": 1.0,
    "min_graphic_s": 2.0,
    "no_same_treatment_back_to_back": true,
    "do": [
      "Show the payload of the line: a figure, a contrast, the steps, the warning, the term.",
      "Leave the face clean when the line is a story, a joke, or a question the face already carries.",
      "Spend a stronger motion on the hook and on the final claim."
    ],
    "dont": [
      "Do not play a fixed sequence of templates.",
      "Do not cover the eyes.",
      "Do not put a whoosh on a jump cut.",
      "Do not repeat the same layout and motion on the next segment.",
      "Do not put a number on screen that this segment did not say."
    ]
  },
  "sfx": {"cuts": false, "kinds": ["reveal", "tick", "impact"]},
  "self_eval": {"max_passes": 3},
  "music": {"policy": "library", "folder_wins": true, "duck_db": -13, "attack_s": 0.08, "release_s": 0.4},
  "brand": {"watermark": false, "intro": false, "outro": false, "lower_third": true},
  "requires": ["talking_head"],
  "optional": ["broll", "photo", "voice", "music", "sfx"],
  "missing": {"talking_head": "stop"}
}
```

`chrome.shorts` adds its `bottom_extra` to the portrait `margin_v` (220 + 120 = 340) and its `right_extra` to the right inset, so a TikTok / Reels / Shorts rail does not cover the card or the caption. The default chrome is `clean`. Landscape ignores the Shorts right-rail padding beyond the normal 80 px side inset. The run file records the chrome the owner asked for.

fps stays the source fps so a 24 fps or 30 fps camera is not retimed. The fixture cameras are 30 fps. A mixed-fps folder uses the rate `render.py` already locks from the first segment.

These lists are the legal ingredients and the limits. They are not an order of appearance.

### 3.3 Orientation for a run

The default is portrait, 1080×1920, chrome `clean`. The agent does not ask. Landscape, 1920×1080, is used only when the prompt asks for it: 16:9, landscape, horizontal, or YouTube widescreen. "Shorts", "TikTok", or "Reels" stays portrait and sets `chrome: shorts`. The answer is `edit/style-run.json`. A folder whose only camera is already 16:9 still delivers portrait unless the prompt asked for landscape. The crop in section 3.4 is what makes that delivery a face, not a letterbox.

One editorial cut serves both orientations. A portrait run is the same ranges, captions, and plan times, rendered into 1080×1920. Layout primitives follow the orientation: a `side-card` in the landscape plan becomes a `lower-card` in the portrait plan so the face keeps the upper frame. The agent rewrites that layout field when the run orientation changes. The intent, the quote, and the rationale stay. The owner who wants a shorter vertical cut asks for that as a second edit.

How a source meets the frame:

| Source | Landscape run | Portrait run |
| --- | --- | --- |
| Already 16:9 | Scale to 1920×1080. | Crop with the window the agent wrote (section 3.4), then scale to 1080×1920. |
| Already 9:16 | Pad to 1920×1080 (letterbox). Do not crop the head. | Scale to 1080×1920. No face crop. |
| Other portrait | Pad to 1920×1080. | Scale to fit 1080×1920, pad the remainder. No side crop. |
| Wider than 16:9 | Scale to fit 1920×1080, pad. | Crop with the agent's window to 9:16, then scale. |

`force` letterbox remains the tool for "pad". The face crop is used only when the run is portrait and the source is wider than 9:16.

### 3.4 Reframe — look, then crop

The current engine already puts the face in frame when an agent edits with it. It does not do that with a detector. Reuse that path.

What `main` actually does:

- Nothing in `helpers/` detects a face. There is no OpenCV, MediaPipe, YuNet, or Haar cascade. `is_portrait_source` in `helpers/render.py` is only "displayed height greater than width," including a 90° or 270° display-matrix rotation. `scale_filter_for` then scales the long side (`scale=-2:1920` for a portrait source, `scale=1920:-2` for a landscape source) or letterboxes when `frame.mode` is `force`. That scale never recenters on a person.
- The picture the model sees is `helpers/timeline_view.py`. `extract_frames` pulls real JPEGs with ffmpeg (`scale=320:-2`) and composites a filmstrip. `SKILL.md` tells the agent to look at that filmstrip at decision points, and principle 6 tells it to invent the technique with ffmpeg when the format can do it.
- The EDL `grade` field is a preset name or a raw ffmpeg filter. `extract_segment` appends that filter after the scale. A crop written there is how a 16:9 frame becomes a 9:16 frame centered on the face. The coordinates come from the model reading the filmstrip, not from a box a library returned. That is the reframe the owner already saw work.
- `grade` is one string for the whole EDL. `extract_all_segments` reads `edl.get("grade")` and applies it to every range. One crop for every shot is the concrete gap: a subject who sits somewhere else in the next take gets the first take's window, and a crop stuffed into `grade` is mixed up with the color grade.

This skill keeps the model's eye and gives the crop its own field. It does not add YuNet. A detector would repeat a job the model already does, and it would be a new weight file for a miss the self-eval filmstrip already catches. The 320 px filmstrip is coarse. For a talking head the face is large enough that the model can place the window, and the rendered filmstrip is the check. Tests do not need a detector: they pass an authored crop, the same shape the model writes, and assert the ellipse survives.

Per range, when the run is portrait and the source is wider than 9:16:

1. The agent runs `timeline_view` on the in-point, the middle, and the out-point of the range. One filmstrip is enough when the face does not move.
2. It writes a crop in source pixels: full source height, width = height × 9/16, x chosen so the face sits in the window. A 1920×1080 camera is a 608×1080 window. The window is clamped inside the source. The field lives on the range, not inside `grade`:

```json
{"crop": {"x": 120, "y": 0, "w": 608, "h": 1080, "source": "look",
          "why": "Face is left of center on the filmstrip at 1.2s."}}
```

3. `extract_segment` applies that crop before the scale and before the grade. The scaled frame is 1080×1920. `edit/reframe.json` copies the crop and the `why`.
4. If the three looks disagree by more than about a fifth of the frame, the face is moving inside the shot. The agent writes one crop per second as keyframes, and x may move by at most 40% of the crop width per second. Across an edit cut the next shot has its own crop. A jump cut may change the window instantly because the picture already cuts.
5. If the agent cannot see a face, the window is centered, `source` is `center`, and the `why` says so. Self-eval says so too.

A source that is already 9:16 is scaled, not cropped. `reframe.json` has no crop for that range. Vertical tracking stays out. A punch-in the plan asks for is a further scale around the crop the agent already wrote.

The fixture ellipse sits at a known x. The portrait test's plan contains the crop that keeps it inside 1080×1920, and the render asserts the ellipse is fully inside the frame. A second plan with a center crop on that off-center ellipse fails that assert. A clip with no ellipse uses `source: center` and the self-eval note is written. No test loads a face model.

### 3.5 Safe zones

Safe areas are the existing `layout_boxes` idea, with the run's `margin_v` and chrome insets. A graphic's glyphs stay inside its rect. The rect stays out of the caption band, the lower-third (when it is on screen), and the face box expanded by 24 px. A segment whose treatment is `clean` has no graphic rect.

These boxes are the legal region when the plan asks for a card. They are not an instruction to put a card on every sentence.

Landscape 1920×1080, margin 90:

- Side inset 80 px. Top inset at least 116 px, clearing the watermark slot even while the watermark is off, so a later logo does not land on a card.
- Caption band is the theme band: 72 px tall, sitting above the 90 px margin (top of band at y = 918). Style `sentence`, Be Vietnam Pro, size 22, spoken case. Alignment bottom-center.
- Lower-third, first 4 s of speech: the existing bottom-left box above the captions (name "Dan Tech", handle `@dantech0xff`). It does not need a logo file.
- Card, when the plan uses `side-card`: 640×520 max, inside the safe rect, on the side opposite the face center. Right side when the face is left of center or unknown. Left side when the face center is in the right half. Vertically centered in the safe rect above the lower-third.
- The face box and the card do not intersect. If they would, shrink the card to 480 px wide once. If they still would, the checker rejects the plan and the agent picks another layout or `clean`. The drop is recorded in `edit/visuals-dropped.json` only after the agent has tried that revision. A silent drop inside render is a failed check.

Portrait 1080×1920, clean chrome, margin 220:

- Top inset 120 px. Side inset 64 px. Bottom caption band sits above the 220 px margin (top of band at y = 1628 for a 72 px band).
- Captions: `sentence`, size 28, bottom-center, inside that band. Two lines maximum. A third line waits for the next cue instead of climbing into the face.
- Lower-third moves to the top-left, under the top inset, for 3 s. A bottom lower-third would collide with a card and the caption. Landscape keeps the bottom lower-third.
- Card, when the plan uses `lower-card`: full width of the safe column, height at most 38% of the frame (about 730 px, less if the caption band starts higher). It sits on the bottom of the safe rect, directly above the caption band. The face keeps the upper portion of the frame.
- `chrome: shorts` uses top 160, right inset 64+96, and margin_v 340. The card and the captions both move up. The right rail stays empty.

Cards are alpha overlays, not full-frame plates. The renderer draws the plan's text and data into the card rect on a transparent raster, encodes an alpha intermediate (png sequence or qtrle), and overlays with `format=auto`. The A-roll remains visible around the card. A card that would still cover the eyes after placement is a failed plan, not a sliver.

### 3.6 Filler, silence, and pacing

The agent cuts on the transcript. The checker rejects a range edge that falls inside a word.

Remove:

- Filler tokens, verbatim, when they are their own word: `ừ`, `ừm`, `à`, `ờ`, `ơ`, `um`, `uh`. `thì` and `kiểu` go only when they are a stall (surrounded by a pause ≥ 0.15 s), because both are also real grammar.
- A false start: the same three-word opening twice, keep the later complete one.
- Silence ≥ 0.4 s inside a take. Keep breaths under 0.15 s. Between sentences, leave 120–200 ms, which is inside the pad window of 80–140 ms on each side of the cut (the pad eats into the gap, it does not add a new hold).
- A cold open that is only a slate, a clap, or "ok so" / "ờ thì" before the claim. The first words of the output should be the claim or the question, and they should land inside 8 s.

Keep:

- Laughs, audio events, and the payoff word of a sentence.
- A hold up to 20 s when one sentence is one argument. Do not cut on a timer.
- The speaker's rate. Do not speed the voice.

When the plan uses b-roll or a photo, it covers 2–5 s of a sentence and returns to the face on the payoff word. A graphic tied to a spoken datum stays on the face, not on the b-roll. Pad on cuts is 80–140 ms (inside the core 30–200 ms window). Same setup may jump-cut. No dip to black and no crossfade on the face; `transition` in the primitive list is `cut` only.

### 3.7 Directing a segment

The skill text walks the agent through section 2.5 with this energy: measured, face-forward, graphics only where the line would be poorer as a face alone.

Worked examples the skill includes, as illustrations of judgment, not as a lookup table:

| The line, in context | A treatment that fits | Why this one |
| --- | --- | --- |
| "nhanh hơn 40%" after a setup line | `side-card` or `lower-card`, motion `count-up`, data `comparison`, text `40%`, sfx `reveal` | The payload is the contrast and the figure. |
| "đừng đẩy secret lên git" | Punch-in on the face, text `secret` for under 2 s, or `clean` if the face already sells the warning | A stat card would invent a number. |
| Three short steps in one sentence | Data `steps`, motion `draw-on`, then the next segment `clean` | The list is the payload. The following line needs air. |
| A joke or a story with no figure | `clean` | The face is the joke. |
| A hook that is the claim | Stronger motion than the next segment (punch-in or a single card), landing inside 8 s | Escalation belongs on the claim, then the energy drops. |
| A shell token or a backtick | Data `code`, text the token, motion `hold` | The term is the payload. |

Timing: a graphic's landing is the last word of its quote, and it may start up to 0.45 s earlier. It holds at least `min_graphic_s` (2 s) and at least until the quote ends. Then the face is clean for at least `min_clean_s` (1 s). A second graphic that would break the gap waits, or the agent marks that segment `clean` and says so in `why`.

The card uses theme colors (placeholder accent, text, surface) and Be Vietnam Pro. It does not recolor itself per video.

### 3.8 Captions, SFX, music, brand

Captions: `sentence`. Vietnamese chunks stay on syllable bounds (12–18). English chunks stay on words (4–7). Case stays as spoken, so diacritics are not uppercased into a different letter. Font file is the theme body face. PlayRes is the run's frame size. Subtitles are still the last filter. Portrait size and margin come from section 3.5. A cue does not sit under a card: the card rect is above the caption band in both orientations.

SFX: `cuts` is false. Jump cuts are silent apart from the 30 ms voice fades. A plan may name `reveal`, `tick`, or `impact` at a payoff word, attack subtracted once, gain from the manifest. It may name none. Density still drops extras. Folder files named for a kind replace that kind's CC0 clip. No stinger, because outro is off.

Music is one bed for the whole piece. The mix graph has a single `audio.music` slot, and a bed change mid-sentence is not this skill.

Priority:

1. A `music` file in the folder is the bed. The plan records `"source": "folder"` and the path. The library is not also mixed.
2. Otherwise the agent reads the kept transcript and picks one id from `brand/music/manifest.json`. The pick follows the piece, not a rotation: a calm explanation, a warning, a question-led hook, a light story. The style's energy is `measured`, and the library has no trailer bed. The plan records the id, the mood it matched, and why.
3. The skill does not compose or generate a bed. If the manifest is empty the run stops and says the library is missing. It does not ship silent and call that a choice.

The library is small and committed with the repo. Four instrumentals is enough for this skill:

| Id | Mood | Energy | Role |
| --- | --- | --- | --- |
| `measured` | explanatory, calm | low | The ordinary Dan Tech explainer. |
| `curious` | question, hook | low-medium | A piece that opens on a question and stays there. |
| `tense` | warning | medium | "Don't do this" pieces. |
| `light` | story, joke | low-medium | A piece whose payload is a story, not a figure. |

Each bed in the manifest has `id`, `file`, `mood` (list), `energy`, `bpm`, `length_s`, `license`, `license_file`, `vocals: false`, `loop`, and `gain_db`. `license` is `CC0-1.0` or another license that allows commercial use with no royalty. The license text sits beside the audio. `load_music_manifest` already rejects `vocals: true`. A bed with an empty `license` fails the same way. Files are long enough to cover a few minutes by the loop `prepare_bed` already does, or they are short loops with the existing crossfade.

`apply_music_policy` today drops `audio.music` whenever `brand/theme.json` has `music.enabled: false` or the manifest is disabled. Both are false on `main` because no licensed file was committed. Once these four files exist, the manifest's `enabled` becomes true. The theme lock stays false so a core run that never named a bed still stays silent. The policy change is: an EDL that names a file or a library id keeps that bed; the theme lock only blocks a bed nobody asked for. Duck stays −13 dB, attack 80 ms, release 400 ms. There is no outro card. The bed fades out over the last 0.5 s. The two transcripts in section 3.10 must not pick the same id.

Brand: lower-third on, as specified per orientation. Watermark, intro, and outro off. If the owner later enables the watermark in the theme and the logo file exists, the core watermark path draws it and the card layout already clears that corner. This skill does not turn the watermark on by itself.

### 3.9 Pacing summary

The edit should sound like the person explaining, with the stalls removed. A finished piece is as long as the kept speech. The hook is the claim inside the first 8 s. Graphics are rare enough that the face is the picture: one earned by the line, then a clean second, then a different treatment if the next line earns one. B-roll is a breath the words asked for, not a second movie.

### 3.10 Acceptance

Fixtures live in `tests/fixtures/styles/explainer/` and are generated in the test with ffmpeg (color, a beige ellipse as the face, a silent or tone audio track) plus checked-in transcript JSON. The suite does not call Scribe. The real-folder run in the definition of done is separate, and it is required before the skill is called done.

Shared picture:

- One 16:9 clip, 8 s, 30 fps, ellipse left of center.
- The same picture is paired with two transcripts. Transcript A includes a filler, a 0.6 s silence, and the phrase `nhanh hơn 40%`. Transcript B has no number and no contrast; its payload line is `đừng đẩy secret lên git`.
- One native 9:16 clip, 4 s, with speech and no number.
- One music bed file in a side folder, used only by the folder-wins test.
- The default fixture folder has no music file. Its plan names a library id.
- The library fixture is four silent-or-tone files plus a manifest with the metadata in section 3.8. The real CC0 files replace the tones when the library is committed. The test checks the id and the policy, not the melody.

Tests:

1. Inventory marks the 16:9 clip `talking_head` and does not invent a music role when no bed is present.
2. A hand-authored plan for transcript A (comparison card on `40%`) passes `check_visual_plan.py`. A plan that puts the same comparison card on transcript B fails, because B's quote has no datum. A plan that repeats the same layout and motion on adjacent segments fails. A plan that sets `sfx` to `cut` fails. A cut inside a word fails.
3. The plan for A and the plan for B, both valid, do not share a treatment signature on the payload segment. A is a card with `40%`. B is `clean` or a punch-in whose on-screen text is `secret`.
4. Landscape render of A, prompted as landscape: `ffprobe` 1920×1080, duration within 0.1 s of the EDL, caption text present in `master.ass` with the spoken diacritics, alpha card present, mix graph has the library bed named in A's plan and a duck, loudnorm still last. Jump cuts have no whoosh. No prompt for landscape is a failed test of the default, not a landscape render.
5. Landscape render of B from the same picture: the payload frame's card region differs from A's (pixel hash of that rect). The face ellipse is still visible. B's plan names a different library id from A's.
6. Portrait render of A's 16:9 source, which is the default: `ffprobe` 1080×1920. The plan's crop keeps the ellipse fully inside the frame. `reframe.json` records `source: look` and that crop, not a detector. The card's bounding box is entirely below the vertical midpoint and above the caption band. Captions use margin 220.
7. Portrait render of the native 9:16 clip: scale only. `reframe.json` has no crop for that range.
8. A center crop authored on the off-center ellipse fails the "ellipse fully inside" assert. A clip with no ellipse, crop `source: center`, still renders, and the self-eval note is written.
9. The same EDL with a music file in the folder: the mix graph uses that file and not the library id. Removing the file returns the graph to the library bed. A plan that names a library id while the folder file is present fails the checker. A manifest bed with `vocals: true` or an empty `license` fails to load.
10. Sample frames are written for the owner: landscape A on the card, landscape B on the payload line, portrait A on the card (face inside the crop), portrait native 9:16.

`check_visual_plan` and the reframe math are unit tests. The frame sizes are fixture renders through `render.py`, the same path a real folder uses. The two-transcript pair is the proof that content, not a preset, decides the picture.

## 4. Phases

Two phases, both in service of the definition of done. There is no third phase in this plan. The skill is not done at the end of phase 1.

### Phase 1 — What the explainer needs from the core

**Effort:** L

**Goal:** A folder of this skill's asset types can be classified, this skill's guardrails can be validated, and the agent is told to follow `style-explainer`.

**Why first:** The skill text needs a checker and an inventory before a render can be honest. The crop field waits until those exist, so a crop is not demoed on a hard-coded folder.

**Tasks:**

1. `helpers/inventory.py` and `tests/test_inventory.py` for the table in section 2.1. Canned probe results and a canned transcript. No network.
2. `skills/style.schema.json`, `helpers/style.py`, `helpers/check_visual_plan.py`, and `skills/style-explainer/style.json` as in section 3.2. The skill prose can be a stub until phase 2. The music manifest schema (mood, energy, bpm, length, license, vocals) is checked here against a fixture manifest. The audio files themselves land in phase 2.
3. `skills/index.json` listing the core and this skill, and the two links in `install.md`.
4. Rewrite the core `SKILL.md` process: a footage edit follows this skill, hard rules unchanged. Point `compile_script.py` at the non-style tool.
5. Document `edit/style-run.json` and the in-memory frame override.

**Files:** `helpers/inventory.py`, `helpers/style.py`, `helpers/check_visual_plan.py`, `skills/style.schema.json`, `skills/style-explainer/style.json`, `skills/index.json`, `SKILL.md`, `install.md`, `tests/test_inventory.py`, `tests/test_visual_plan.py`.

**New dependencies:** none.

**Acceptance:** items 1 and 2 of section 3.10. `install.md` registers `video-use` and `style-explainer` only.

**Risks:**

- Speech-ratio thresholds will misfile a quiet talking head or a chatty b-roll. `ambiguous` plus one `timeline_view` is the escape. Do not lower the threshold until a real folder shows the miss.
- A checker that still encodes "digit → stat card" would violate the design principle even if the tests pass. Review the checker against section 2.5 before closing the phase.

### Phase 2 — The skill, finished

**Effort:** L

**Goal:** The definition of done. Both orientations, the creative-direction skill text, alpha cards, face reframe, captions, SFX, music, brand, the self-eval loop, fixture renders, and one real-folder run.

**Why second:** It needs inventory, the plan checker, and the run file from phase 1.

**Tasks:**

1. Write `skills/style-explainer/SKILL.md` to the level in section 3, including the worked examples as judgment, not as a table to execute blindly.
2. Alpha-card renderer for the primitives the plan names: text, data types, motions. Placement from section 3.5. Reject a plan that intersects the eyes.
3. Per-range `crop` on the EDL, applied in `extract_segment` before scale and grade. The agent fills it from `timeline_view`, as section 3.4 describes. `edit/reframe.json` records the window and `source: look` or `source: center`. No face-detection dependency. Punch-in is a further scale around that window when the plan asks for it.
4. Portrait lower-third at the top-left. Landscape lower-third unchanged.
5. Caption size and `margin_v` from the run's frame entry.
6. SFX only from the plan, never a cut whoosh. Music: folder file wins; otherwise the library id from the plan. `apply_music_policy` keeps an explicit file or id when the theme lock is closed, and still drops a bed nobody named. Commit the four CC0 (or equivalent commercial-use) beds, their license texts, and the manifest metadata.
7. Self-eval notes in `edit/project.md`, including relevance.
8. Fixtures and the renders in section 3.10. Then the real-folder run: both MP4s, both plans, the project notes.

**Files:** `skills/style-explainer/SKILL.md`, `helpers/visuals/` (card path; `select.py` left uncalled), `helpers/render.py` (per-range crop and in-memory frame), `helpers/audio.py` (explicit bed kept when the theme lock is closed), `helpers/brand.py` (portrait lower-third placement), `brand/music/` (four beds, licenses, manifest), `tests/test_reframe.py`, `tests/test_explainer_layout.py`, `tests/test_music_library.py`, `tests/fixtures/styles/explainer/`.

**New dependencies:** none. No face-detection model and no new audio library. The beds are files.

**Acceptance:** section 3.10, items 1–10, and items 1–9 of the definition of done. Both frame sizes are required. The real-folder run is required. A landscape-only sample does not close the phase.

**Risks:**

- The agent's crop on a real face at the extreme edge of a 16:9 frame can still clip an ear once the window is clamped. `reframe.json` records the clamp so the self-eval can say the crop hit the frame edge. A missed face is a bad look, fixed by looking again, not by adding a detector.
- Alpha overlay through the current yuv420 chain will flatten the card. The card encode has to keep an alpha pix_fmt and the overlay filter has to honor it. A flattened full-frame card fails acceptance even if the timing is right.
- Portrait captions at margin 220 can still collide with a tall card. The layout test measures both rects on 1080×1920 and fails on intersection.
- The real folder may contain a case the fixtures hide (two speakers, a vertical phone clip plus a landscape camera). The run stops and asks, per sections 2.1 and 3.1, rather than inventing a policy during that run.

## 5. Open decisions

Recommendations are the default if the owner says to proceed. None of them block writing this plan. A few of them change phase 2's layout numbers, so they should be answered before implementation starts.

### 5.1 One confirmation before the cut?

The core still has a hard rule that the agent waits for a plain-English strategy. This direction also says the agent should analyze the folder and produce the video.

| Option | Result |
| --- | --- |
| A. Keep one confirm | The agent shows orientation (portrait unless the prompt said landscape), what it will cut, the visual plan (intent, treatment, why), and which bed (folder file or library id and why). Then it renders. |
| B. Render straight through | Faster, and a bad filler cut or a mismatched graphic only shows up in self-eval. |

**Recommendation:** A. One short confirm. The plan is the thing the owner can correct before a long render. Self-eval is a weak time to discover the agent dropped a whole take.

### 5.2 Default orientation — decided

Portrait 1080×1920 is the default. Landscape 1920×1080 happens only when the prompt asks for it. Section 3.3 has the wording that counts ("16:9", "landscape", "horizontal", "YouTube widescreen"). "Shorts", "TikTok", and "Reels" stay portrait and turn on `chrome: shorts`.

### 5.3 Same cut in both orientations?

| Option | Result |
| --- | --- |
| A. Same ranges, two deliveries | Portrait is a reframe plus the layout swap in section 3.3, not a second edit. |
| B. Portrait is a tighter cut | A different EDL, shorter, fewer asides. |

**Recommendation:** A. A tighter vertical cut is a different request, not a hidden mode of this skill.

### 5.4 Face crop — decided

No new detector. The agent looks at `timeline_view` and writes a per-range crop, which is the mechanism `main` already uses, with the crop taken out of the shared `grade` string. Section 3.4 is the whole design. YuNet is not added.

### 5.5 Portrait chrome

| Option | Result |
| --- | --- |
| A. `clean` default, `shorts` when the user says TikTok / Reels / Shorts | Explainer captions sit at margin 220. Platform rails opt in. |
| B. Always the Shorts rail | Every portrait export wastes the right edge and a deep bottom band. |

**Recommendation:** A. The numbers are in sections 3.2 and 3.5.

### 5.6 Lower-third without a logo

| Option | Result |
| --- | --- |
| A. On for this skill | "Dan Tech" and `@dantech0xff` for a few seconds. No logo file required. |
| B. Off until the logo exists | Cleaner frame, no name bug. |

**Recommendation:** A. The handle is already the on-screen id. Watermark and intro stay off.

### 5.7 Separate voice file

| Option | Result |
| --- | --- |
| A. A `voice` file replaces camera audio | Lav mic wins when the owner dropped one in. |
| B. Always camera audio | The voice file is ignored. |

**Recommendation:** A, and stop if the two durations disagree by more than 0.5 s.

## 6. Non-goals

This work does not add another style. It does not build a style plugin system, a generic preset runner, or a registry beyond the core and `style-explainer`. It does not change TTS, `compile_script.py`, or the placeholder palette. It does not turn on the watermark. It does not add a face detector. It does not vertically track a face beyond the punch-in the plan requests. It does not put a whoosh on a jump cut. It does not call `helpers/visuals/select.py`. It does not generate music.

## Appendix — later styles, not in this work

Noted so they are not redesigned by accident. None of them are specified, scheduled, or part of the definition of done.

| Id | One line |
| --- | --- |
| `shorts` | One idea, 20–45 s, 9:16 only, faster than the explainer. |
| `documentary` | Recorded voice as the clock, photos and b-roll as the picture, no face required. |
| `tutorial` | Screen recording plus voice, cuts through dead UI time. |
| `vlog` | Talking head and b-roll, fewer graphics, wider pad. |
