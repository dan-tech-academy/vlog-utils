---
name: style-explainer
description: Talking-head tech explainer for Dan Tech. Delivery is portrait 9:16 unless the user asks for 16:9. Visuals are chosen per segment from the words. A 16:9 camera is cropped from the timeline_view filmstrip. Read the core video-use SKILL.md and style.json before editing.
---

# Talking-head explainer

Read `../../SKILL.md` (the core hard rules) and `style.json` in this directory before anything else. This skill is the footage edit. It does not synthesize a voice.

The render path, the card renderer, and the worked examples land with the rest of the skill. The checker is already `helpers/check_visual_plan.py`. A footage run still follows the core hard rules: subtitles last, no cut inside a word, outputs only under `<videos_dir>/edit/`.
