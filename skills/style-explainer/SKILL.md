---
name: style-explainer
description: Talking-head tech explainer for Dan Tech. Delivery is portrait 9:16 unless the user asks for 16:9. Visuals are chosen per segment from the words. A 16:9 camera is cropped from the timeline_view filmstrip. Read the core video-use SKILL.md and style.json before editing.
---

# Talking-head explainer

Read `../../SKILL.md` (the core hard rules) and `style.json` in this directory before anything else. This skill is the footage edit. It does not synthesize a voice and it does not call `helpers/visuals/select.py`.

A person talks to camera about a technical idea, in Vietnamese or mixed Vietnamese and English. The face stays the A-roll. Fillers and dead air go. Each kept sentence is directed from what it means. A figure may become a card. A warning may become a punch-in. A story may stay a clean face. The next sentence does not reuse that treatment. Captions are sentence-length in Be Vietnam Pro. Jump cuts stay dry. A music file in the folder is the bed. Otherwise pick one instrumental from `brand/music/`. The default delivery is 1080×1920. Landscape 1920×1080 is rendered only when the prompt asks for it.

Helpers live next to the core skill. From this directory that is `../../helpers/`. Run them with `python` from the video-use repo root as `python helpers/<name>.py`.

## Stop before a cut

Required: at least one `talking_head` video whose transcript has speech. The camera may be 16:9, 9:16, or another frame. Phone rotation metadata counts.

| Gap | What to do |
| --- | --- |
| No `talking_head` | Stop. Name the missing role. Do not synthesize speech. Photos plus a voice file are not a substitute. |
| No b-roll and no photos | Normal. Use the face, type, and cards. |
| No music in the folder | Pick one bed from `brand/music/manifest.json`. Do not generate a bed. Do not leave the mix silent. |
| No SFX files | Use the CC0 set, only kinds this plan names. |
| Ambiguous file | One question, then update `edit/inventory.json`. |
| Voice file and camera audio differ by more than 0.5 s | Stop and ask which timeline is the cut. Do not stretch one to the other. |

A `voice` file replaces camera audio as the stem. The camera picture stays.

## Run

Write every session file under `<videos_dir>/edit/`. Do not write inside the video-use repo.

1. **Inventory.** `python helpers/inventory.py <folder> --edit-dir <edit>`. It does not call Scribe. A file printed as `needs_transcript` has no role yet. Transcribe with the core helpers (`transcribe_batch.py`, cache per source), then re-run inventory with `--transcripts`, a JSON map of relative path to `{"words": [...]}`. Folder names win: `voice/`, `music/`, `sfx/`, `broll/`, `photos/`, `screen/` (screen is b-roll). A mid speech ratio stays `ambiguous` until you look at one `timeline_view` and set that file's `role` to `talking_head` or `broll` and `source` to `look` in `edit/inventory.json` (`apply_look` in `helpers/inventory.py` does the same write). Do not guess a role for a file that has no transcript.

2. **Read.** `pack_transcripts.py` writes `takes_packed.md`. That is the reading view. Note slips in a short list.

3. **Orientation.** Do not ask. Write `edit/style-run.json` before the visual plan.

   Portrait `clean` is the default. Landscape only when the prompt contains one of: `16:9`, `16x9`, `1920x1080`, `landscape`, `horizontal`, `youtube widescreen`. `shorts`, `tiktok`, or `reels` stays portrait and sets `chrome` to `shorts`. A 16:9 camera still delivers portrait unless the prompt asked for landscape. `python -c` is unnecessary. The phrases above are the rule. `helpers/orientation.py` `resolve_orientation` implements the same phrases if you want to check a prompt.

   ```json
   {"style": "explainer", "orientation": "portrait", "chrome": "clean"}
   ```

   One editorial cut serves both orientations. The same ranges, quotes, and times. When you change orientation, rewrite layout only: a landscape `side-card` becomes a portrait `lower-card`. Intent, quote, and why stay. A shorter vertical cut is a separate request.

4. **Cut.** Snap every edge to a word. Pad 80–140 ms (inside the core 30–200 ms window). The checker rejects an edge inside a word.

   Remove, as their own words: `ừ`, `ừm`, `à`, `ờ`, `ơ`, `um`, `uh`. `thì` and `kiểu` go only when they are a stall with a pause of at least 0.15 s on both sides. They are also real grammar. Drop a false start when the same three-word opening happens twice, and keep the later complete one. Cut silence of 0.4 s or more inside a take. Keep breaths under 0.15 s. Between sentences leave 120–200 ms. Drop a cold open that is only a slate, a clap, or "ok so" / "ờ thì" before the claim. The first words of the output are the claim or the question, and they land inside 8 s.

   Keep laughs, audio events, and the payoff word. A hold may run up to 20 s when one sentence is one argument. Do not cut on a timer and do not speed the voice.

   B-roll or a photo, when the words need a picture the face does not show, covers 2–5 s and returns to the face on the payoff word. A graphic tied to a spoken datum stays on the face. Same setup may jump-cut. No dip to black and no crossfade on the face. The only transition is `cut`.

5. **Crop, when the run is portrait and the source is wider than 9:16.** There is no face detector. Look, then write the window.

   Run `timeline_view.py` on the in-point, the middle, and the out-point. One filmstrip is enough when the face does not move. Write a crop in source pixels on the EDL range, not inside `grade`. Full source height, width = height × 9/16, x so the face sits in the window. A 1920×1080 camera is a 608×1080 window, clamped inside the source.

   ```json
   {"crop": {"x": 120, "y": 0, "w": 608, "h": 1080, "source": "look",
             "why": "Face is left of center on the filmstrip at 1.2s."}}
   ```

   `extract_segment` applies that crop before the scale and before the grade. The scaled frame is 1080×1920. `edit/reframe.json` copies the crop and the why.

   If the three looks disagree by more than about a fifth of the frame, write `keyframes`: one x per second, moving by at most 40% of the crop width per second. The next shot has its own crop. A jump cut may change the window instantly.

   If you cannot see a face, center the window, set `source` to `center`, and say so in `why`. Render writes that fact into `edit/project.md`. Self-eval repeats it.

   A source that is already 9:16 is scaled, not cropped. `reframe.json` has no crop for that range. Already-9:16 into a landscape run is letterboxed. Do not crop the head off to fill 16:9.

   | Source | Landscape run | Portrait run |
   | --- | --- | --- |
   | Already 16:9 | Scale to 1920×1080. No face crop. | Crop with the window you wrote, then scale to 1080×1920. |
   | Already 9:16 | Letterbox to 1920×1080. | Scale to 1080×1920. No crop. |
   | Other portrait | Letterbox to 1920×1080. | Scale to fit 1080×1920 and pad the rest. No side crop. |
   | Wider than 16:9 | Scale to fit 1920×1080 and pad. | Crop with your window to 9:16, then scale. |

6. **Direct each segment.** After the cut, before overlays. `style.json` is taste and limits. It is not an order of templates. Do not map a digit onto a card because it is a digit.

   Split kept speech on sentence or beat boundaries. Read each segment with the one before it and the one after it. Assign one intent: `claim`, `number`, `comparison`, `steps`, `warning`, `joke`, `question`, `story`, `code`, `emphasis`.

   Compose a treatment from the primitives in `style.json`, or mark the segment clean, or mark it bespoke when no composition can carry the line. Write why in one or two sentences that quote or paraphrase the line. A clean stretch is one segment. Two adjacent segments whose signature is `clean` fail the checker. A signature is `layout` + `motion` + `data.type`. A clean segment's signature is `clean`.

   Variety is part of composing. Do not repeat the same treatment on the next segment. Leave at least `min_clean_s` (1 s) of clean face between graphics. At most `max_graphics_per_10s` (2) graphics in any 10 s. A graphic holds at least `min_graphic_s` (2 s) and at least until its quote ends. It may start up to 0.45 s before the last word of the quote. Spend a stronger motion on the hook and on the final claim, then drop the energy.

   These lines are judgment, not a lookup table. A different transcript on the same picture gets a different treatment.

   | The line, in context | A treatment that can fit | Why this one |
   | --- | --- | --- |
   | "nhanh hơn 40%" after a setup line | `side-card` or `lower-card`, motion `count-up`, data `comparison`, text `40%`, sfx `reveal` | The payload is the contrast and the figure. |
   | "đừng đẩy secret lên git" | Punch-in on the face, text `secret`, or `clean` if the face already sells the warning | A comparison card would invent a number. |
   | Three short steps in one sentence | Data `steps`, motion `draw-on`, then the next segment `clean` | The list is the payload. The following line needs air. |
   | A joke or a story with no figure | `clean` | The face is the joke. |
   | A hook that is the claim | Stronger motion than the next segment, landing inside 8 s | Escalation belongs on the claim, then the energy drops. |
   | A shell token or a backtick | Data `code`, text the token, motion `hold` | The term is the payload. |

   On-screen text and data labels must occur in that segment's quote. A shortening is allowed only when `why` names it and the numerals still occur in the quote. Do not put a number on screen that this segment did not say.

   `edit/visual_plan.json`:

   ```json
   {
     "style": "explainer",
     "orientation": "portrait",
     "music": {"source": "library", "id": "measured", "why": "Calm explanation. No folder bed."},
     "segments": [
       {
         "id": "s3",
         "start": 4.2,
         "end": 7.0,
         "quote": "nhanh hơn 40%",
         "intent": "comparison",
         "why": "The line contrasts speed and states a percent. The previous line was only setup.",
         "face_center_x": 480,
         "treatment": {
           "layout": "lower-card",
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

   A clean segment is `{"treatment": {"layout": "clean"}}` and still has `intent` and `why`. A punch-in sets `"motion": "punch-in"`. Render adds a zoom of at least 1.15 around the crop you wrote, or around the full source when the run has no crop. You may set `crop.zoom` yourself. A bespoke segment is `{"layout": "bespoke", "engine": "pillow", "path": "edit/visuals/s3.mov"}` and the why names the primitive that cannot carry the line.

   `start` and `end` are times on the output timeline. The card is drawn for that window. Layout `side-card` is for landscape. Layout `lower-card` is for portrait. Portrait plus `side-card` fails the checker. Pass `face_center_x` in delivery-frame pixels when you know which half the face is in. Landscape puts the card on the other side. Unknown face center uses the right side.

   Safe zones, so a card does not cover the eyes or the captions:

   - Landscape 1920×1080, margin 90. Side inset 80. Top inset at least 116. Caption band is 72 px tall above the margin. Captions are `sentence`, Be Vietnam Pro, size 22, bottom-center, spoken case. Lower-third is bottom-left for the first 4 s: "Dan Tech" and `@dantech0xff`. A `side-card` is at most 640×520, vertically centered in the safe rect, opposite the face. If it would cover the face expanded by 24 px, it shrinks to 480 px wide once. If it still would, change the layout or mark the segment clean. Record that revision. Do not let render drop the card in silence.
   - Portrait 1080×1920, chrome `clean`, margin 220. Top 120. Side 64. Caption size 28, two lines maximum, band above the 220 px margin. A third line waits for the next cue. Lower-third is top-left for 3 s. A `lower-card` is the safe column, at most 38% of the frame tall, entirely below the vertical midpoint and above the caption band. The face keeps the upper frame.
   - `chrome: shorts` adds `bottom_extra` 120 to the margin (220 + 120 = 340) and `right_extra` 96 to the right inset. Top becomes 160. The right rail stays empty.

   Cards use the colors and fonts in `brand/theme.json`. Those colors are placeholders. Do not recolor the card per video. Watermark, intro, and outro stay off.

7. **Music.** One bed for the whole piece.

   1. A file whose inventory role is `music` wins. The plan records `"source": "folder"` and the path. Do not also name a library id. The checker rejects that.
   2. Otherwise read the kept transcript and pick one id. The pick follows the piece, not a rotation.

   | Id | Use it when |
   | --- | --- |
   | `measured` | A calm explanation. The ordinary Dan Tech explainer. |
   | `curious` | The piece opens on a question and stays there. |
   | `tense` | A warning. "Don't do this." |
   | `light` | The payload is a story or a joke, not a figure. |

   Record the id, the mood it matched, and why. Two different transcripts should not get the same id when their moods differ. The beds are original instrumentals, CC0, no vocals. They loop. Duck is −13 dB, attack 80 ms, release 400 ms. The bed fades over the last 0.5 s. `brand/theme.json` keeps `music.enabled` false so a run that names no bed stays silent. Naming a file or an id keeps the bed. If the manifest is missing, stop and say the library is missing. Do not generate a bed.

8. **SFX.** `style.json` sets `cuts` false. Jump cuts get the 30 ms voice fades and no whoosh. A segment may name `reveal`, `tick`, or `impact` at its payoff, or name none. Do not name `cut`. A folder file whose name matches a kind replaces that kind's CC0 clip.

9. **Confirm once.** Show orientation, what you will cut, the visual plan (intent, treatment, why per segment), and which bed (folder path or library id, and why). Wait for that confirm. Then render. This is the one strategy confirm. Self-eval is the wrong time to discover a dropped take.

10. **Check, then render.**

    ```bash
    python helpers/check_visual_plan.py \
      --plan edit/visual_plan.json \
      --run edit/style-run.json \
      --inventory edit/inventory.json \
      --edl edit/edl.json \
      --words edit/words.json \
      --manifest brand/music/manifest.json
    python helpers/render.py edit/edl.json -o edit/final.mp4 --build-subtitles
    ```

    `edit/words.json` is an object of source id to the Scribe word list (`type`, `start`, `end`, `text`). Exit 1 prints `field: message`. Revise the plan. The checker does not pick a substitute graphic. It fails a missing intent, why, or treatment; on-screen text the quote did not say; data when the quote has no number, percent, currency, or contrast (`vs`, `versus`, `so với`, `hơn`); an identical signature on the next segment; a graphic shorter than 2 s; a gap under 1 s; more than 2 graphics in 10 s; a portrait `side-card` or a landscape `lower-card`; a card on the eyes; sfx `cut` or an unknown kind; a library id while the folder has music, an unknown id, vocals, or an empty license; a frame size that disagrees with the run; a cut inside a word.

    The EDL ranges are the cut. Set `frame.width` and `frame.height` to the run (1080×1920 or 1920×1080). Put each crop on its range. `render.py` reads `edit/style-run.json` and `edit/visual_plan.json`, draws alpha cards and the lower-third, and copies music and SFX from the plan onto the EDL when you have not set them yourself. Subtitles are still the last filter. Loudnorm (−14 LUFS / −1 dBTP / LRA 11) stays last in the audio chain.

11. **Self-eval.** Run the core checklist on the rendered file: `timeline_view` at every cut, captions readable inside the safe band, diacritics drawn, `ffprobe` duration within 0.1 s of `total_duration_s`, `ebur128` on the mix. You cannot hear the mix. Report the numbers.

    Also check, and write each one into `edit/passes.json` as a list of `{"failures": ["..."], "loudness": "..."}`:

    - Every on-screen string is in that segment's quote.
    - A data graphic is absent when the quote has no datum.
    - Eyes are not under a card. A face the plan left visible is still visible.
    - Portrait `edit/reframe.json` matches the crop you wrote (`source` `look` or `center`), and the frame shows that window.
    - Jump cuts have no whoosh. Any SFX kind is one the plan named.
    - The bed is the folder file, or the library id in the plan, and it is ducked.

    A failed relevance check rewrites the visual plan. It does not swap in a keyword card from `select.py`.

    ```bash
    python helpers/self_eval.py --passes edit/passes.json --max-passes 3 --project edit/project.md
    ```

    The printed word is the decision. `stop_pass`: checks passed, show the preview. `stop_no_progress`: this pass left the same failures as the one before it, show the preview with the issues. `stop_cap`: `self_eval.max_passes` (default 3) is the backstop, a cost stop, not a quota. Show the preview and the remaining issues. `rerender`: fix, render again, append the next pass. Do not hide the file because a check is still open.

## What this skill does not do

It does not add another style. It does not change TTS or `compile_script.py`. It does not turn the watermark on. It does not add a face detector. It does not generate music. It does not put a whoosh on a jump cut.
