---
name: story-to-video-cloud
version: 1.0.0
description: "Turn stories into highly consistent cinematic videos using a cloud-based image generation backend (Grok Imagine via fal.ai) and self-hosted LTX-2.3 FLF2V video generation."
triggers:
  - cloud-video
  - story-to-video-cloud
  - grok-imagine
---

# v1.0.0 — Cloud Story-to-Video Pipeline (Grok Imagine & LTX-2.3)

This skill implements a cloud-integrated story-to-video pipeline. It uses Google ADK for structured orchestration, Grok Imagine via fal.ai for premium, reference-guided character sheets and shot generation, and LTX-2.3 (via ComfyUI) for First-to-Last Frame video generation.

## Orchestration Flow
1. **Director Script** — Narrative planning only
1.5 **FFLF Visual Planner** — Shot framing, entry, camera & visual delta planning (Step 1.5)
2a. **Blueprint Structure** — Structured schema validation
2b. **Blueprint Visuals** — Enriching blueprint with FFLF plan details
3. **Character Sheet Prompter** — Grok T2I Character Reference Sheets
4. **Char Spatial Mapper** — Prioritizing characters by prominence
4.5 **FF Shot Prompter** — Grok Edit with character reference images
4.6 **Reference Integrity Node** — Ensuring strict 3-ref limits and coverage (Step 4.6)
5. **LF Delta Planner** — Planning transition between frames
5.5 **LF Shot Prompter** — Grok Edit using FF + character sheets
6. **Motion Prompter** — Generating LTX prompt & settings
7. **Validate Prompts** — Structural validation of prompt payloads
8. **Wave Organizer** — Optimizing image/video batches
9. **Wave Executor** — Run Grok Imagine via fal.ai & LTX-2.3 FLF2V on ComfyUI

## Usage
```bash
python3 main.py --story "Your story content here" --name "story_output_dir_name"
```

