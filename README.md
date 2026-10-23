<p align="center">
  <img src="static/video-use-banner.png" alt="video-use" width="100%">
</p>

# video-use

Introducing **video-use** — edit videos with Claude Code. 100% open source.

Drop raw footage in a folder, chat with Claude Code, get `final.mp4` back. Works for any content — talking heads, montages, tutorials, travel, interviews — without presets or menus.

Cloud-hosted video-use is coming. [Join the waitlist at video-use.com](https://video-use.com?utm_source=github).

## Quick start (macOS / Linux)

From the footage folder:

```bash
curl -fsSL https://raw.githubusercontent.com/dan-tech-academy/video-use/main/scripts/init.sh | bash
```

That clones [dan-tech-academy/video-use](https://github.com/dan-tech-academy/video-use) to `~/Developer/video-use` (`VIDEO_USE_HOME` overrides the path) and links `video-use` and `style-explainer` into `.claude/skills/` and `.agents/skills/` in the current folder. Run `~/Developer/video-use/scripts/init.sh` again any time. `--install-cmd` also links it to `~/.local/bin/video-use-init`.

If the script says the ElevenLabs key is missing, add it. This appends. It does not replace an existing `.env`:

```bash
printf 'ELEVENLABS_API_KEY=%s\n' 'YOUR_KEY' >> ~/Developer/video-use/.env && chmod 600 ~/Developer/video-use/.env
```

Then open the agent in that same folder:

```bash
claude
```

> Dùng style-explainer dựng video này

Portrait 1080×1920. Say "landscape 16:9" in the same prompt when you want 1920×1080.

| Flag | Effect |
| --- | --- |
| `--global` | Link `~/.claude/skills` and `~/.agents/skills` instead of the current folder. Also `${CODEX_HOME:-~/.codex}/skills` when that directory already exists. |
| `--remove` | Unlink the skills from the current folder. `--global --remove` unlinks the home copies. |
| `--install-cmd` | Symlink the script to `~/.local/bin/video-use-init`, and say so if that directory is not on `PATH`. |
| `--help` | Usage. |

Update with `git -C ~/Developer/video-use pull --ff-only`, or run the script again. Uninstall the folder links with `bash ~/Developer/video-use/scripts/init.sh --remove`. If the footage folder is a git repo, the script prints `.gitignore` lines and does not edit the file.

## What it does

- **Cuts out filler words** (`umm`, `uh`, false starts) and dead space between takes
- **Auto color grades** every segment (warm cinematic, neutral punch, or any custom ffmpeg chain)
- **30ms audio fades** at every cut so you never hear a pop
- **Burns subtitles** in your style — 2-word UPPERCASE chunks by default, fully customizable
- **Generates animation overlays** via [HyperFrames](https://github.com/heygen-com/hyperframes), [Remotion](https://www.remotion.dev/), [Manim](https://www.manim.community/), or PIL — spawned in parallel sub-agents, one per animation
- **Self-evaluates the rendered output** at every cut boundary before showing you anything
- **Persists session memory** in `project.md` so next week's session picks up where you left off

## Setup prompt

Paste into Claude Code, Codex, Hermes, Openclaw, or any agent with shell access:

```text
Set up https://github.com/dan-tech-academy/video-use for me.

Read install.md first to install this repo, wire up ffmpeg, register the skill with whichever agent you're running under, and set up the ElevenLabs API key — ask me to paste it when you need it. Then read SKILL.md for daily usage, and always read helpers/ because that's where the editing scripts live. After install, don't transcribe anything on your own — just tell me it's ready and wait for me to drop footage into a folder.
```

The agent handles the clone, dependencies, skill registration, and prompts you once for your ElevenLabs API key (grab one at [elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys)).

Then point your agent at a folder of raw takes:

```bash
cd /path/to/your/videos
claude    # or codex, hermes, etc.
```

## Generate from a script

Footage still uses the inventory path above. A folder with `script.json` and no camera files is a different entry point:

```bash
python helpers/compile_script.py /path/to/videos/script.json --edit-dir /path/to/videos/edit --plan
python helpers/compile_script.py /path/to/videos/script.json --edit-dir /path/to/videos/edit --provider fake
```

`--plan` prints the voice, the template for each beat, the SFX kinds, and the music id. It does not call ffmpeg or a speech API. The catalog (stat, list, comparison, code, section, question, kinetic, quote) is the default picture. `visual: "custom"` is the slot for HyperFrames, Remotion, or Manim. Confirm language, voice, templates, bed, and runtime before a new synthesis. A cache hit may render without asking again.

For always-on editing from your own VPS or Telegram, run the agent through [Browser Use Box](https://browser-use.com/bux). [Watch the 15-second demo](https://www.tiktok.com/@browser_use/video/7639824093721758989).

And in the session:

> edit these into a launch video

It inventories the sources, proposes a strategy, waits for your OK, then produces `edit/final.mp4` next to your sources. All outputs live in `<videos_dir>/edit/` — the skill directory stays clean.

## Manual install

If you'd rather do it by hand:

```bash
# 1. Clone and symlink into your agent's skills directory
git clone https://github.com/dan-tech-academy/video-use ~/Developer/video-use
ln -sfn ~/Developer/video-use ~/.claude/skills/video-use        # Claude Code
# ln -sfn ~/Developer/video-use ~/.codex/skills/video-use       # Codex

# 2. Install deps
cd ~/Developer/video-use
uv sync                         # or: pip install -e .
brew install ffmpeg             # required
brew install yt-dlp             # optional, for downloading online sources

# 3. Add your ElevenLabs API key
cp .env.example .env
$EDITOR .env                    # ELEVENLABS_API_KEY=...
```

## How it works

The LLM never watches the video. It **reads** it — through two layers that together give it everything it needs to cut with word-boundary precision.

<p align="center">
  <img src="static/timeline-view.svg" alt="timeline_view composite — filmstrip + speaker track + waveform + word labels + silence-gap cut candidates" width="100%">
</p>

**Layer 1 — Audio transcript (always loaded).** One ElevenLabs Scribe call per source gives word-level timestamps, speaker diarization, and audio events (`(laughter)`, `(applause)`, `(sigh)`). All takes pack into a single ~12KB `takes_packed.md` — the LLM's primary reading view.

```
## C0103  (duration: 43.0s, 8 phrases)
  [002.52-005.36] S0 Ninety percent of what a web agent does is completely wasted.
  [006.08-006.74] S0 We fixed this.
```

**Layer 2 — Visual composite (on demand).** `timeline_view` produces a filmstrip + waveform + word labels PNG for any time range. Called only at decision points — ambiguous pauses, retake comparisons, cut-point sanity checks.

> Naive approach: 30,000 frames × 1,500 tokens = **45M tokens of noise**.
> Video Use: **12KB text + a handful of PNGs**.

Same idea as browser-use giving an LLM a structured DOM instead of a screenshot — but for video.

## Pipeline

```
Transcribe ──> Pack ──> LLM Reasons ──> EDL ──> Render ──> Self-Eval
                                                              │
                                                              └─ issue? fix + re-render (max 3)
```

The self-eval loop runs `timeline_view` on the _rendered output_ at every cut boundary — catches visual jumps, audio pops, hidden subtitles. You see the preview only after it passes.

## Design principles

1. **Text + on-demand visuals.** No frame-dumping. The transcript is the surface.
2. **Audio is primary, visuals follow.** Cuts come from speech boundaries and silence gaps.
3. **Ask → confirm → execute → self-eval → persist.** Never touch the cut without strategy approval.
4. **Zero assumptions about content type.** Look, ask, then edit.
5. **12 hard rules, artistic freedom elsewhere.** Production-correctness is non-negotiable. Taste isn't.

See [`SKILL.md`](./SKILL.md) for the full production rules and editing craft.
