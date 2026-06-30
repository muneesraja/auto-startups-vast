---
name: story-maker
version: 2.1.0
description: "ADK multi-agent story-to-video: LTX-aware director, dynamic Grok refs, LTX 2.3 I2V with native audio."
triggers:
  - story-maker
  - story-maker-v2
---

# Story Maker V2 — ADK Multi-Agent Pipeline

Turns a high-level story into an animated film using a Google ADK `Workflow` graph with LTX 2.3-aware planning and generation.

## Pipeline

1. **Narrative Expander** — sparse story + target duration → `narrative_outline.json` (acts, scene beats, budgets)
2. **LTX Shot Director** — outline → `story_plan.json` (4–15s shots with `motion_intent`, `camera_intent`, `audio_intent`)
3. **Timeline Enricher** — `scene_time_offset_seconds`, continuity flags, meta totals
4. **Duration Budget Validator** — checks summed shot duration vs target ± tolerance
5. **Audio Planner** → `audio_plan.json`
6. **Scene Asset Planner** → `scene_assets.json`
7. **Parallel prompters** → `generation_specs.json`
8. **Generation** — backgrounds → char sheets → shot images → LTX I2V → `final_film.mp4`

See [`assets/ltx-2.3-director-bible.md`](assets/ltx-2.3-director-bible.md) for LTX constraints fed to directors and motion prompter.

## Requirements

- `OPENROUTER_API_KEY` (or `GEMINI_API_KEY` / `MINIMAX_API_KEY`)
- `FAL_KEY` for Grok Imagine
- `COMFYUI_URL` for LTX 2.3 I2V
- `ffmpeg` for final concat

## Usage

```bash
cd skills/story-maker
pip install -r requirements.txt

python3 main.py \
  --story-file ../../stories/baby-dolphin/Story.md \
  --name baby-dolphin \
  --target-duration 5m \
  --stop-before-generation
```

### Flags

| Flag | Description |
|------|-------------|
| `--target-duration` | Target runtime: `300`, `5m`, `5min` (default 120s if omitted) |
| `--duration-tolerance` | Allowed deviation percent (default 15) |
| `--fresh` | Wipe artifacts and replan from scratch |
| `--stop-before-generation` | Run planning + specs only; skip fal/ComfyUI |
| `--only-scenes` | Generate only listed scene ids (e.g. `scene_01`) |
| `--story-file` | Read story from file |

Resume is automatic: re-run the same `--name` and the `resume_router_node` picks up from the earliest missing artifact.

## LTX shot sizing

| Complexity | Duration | Use for |
|------------|----------|---------|
| simple | 4–6s | insert, reaction, single gesture |
| moderate | 7–10s | standard action beat |
| complex | 11–15s | one camera beat, max 2–3 micro-beats |

Motion prompts are I2V-native: animate from the still — no appearance re-description.

## Background reference modes

| Mode | Use case | Grok Edit reference |
|------|----------|---------------------|
| `style_anchor` | Dynamic exteriors | Character sheets only |
| `full_plate` | Static interiors | Char sheets + `scene_id` background plate |

## Output layout

```
outputs/story-maker/<name>/
├── narrative_outline.json
├── story_plan.json
├── audio_plan.json
├── scene_assets.json
├── generation_specs.json
├── backgrounds/
├── characters/
├── images/
├── videos/
└── final_film.mp4
```

Override base dir with `STORY_MAKER_OUTPUT_DIR` in `.env`.

## ComfyUI

Uses `assets/workflow-templates/ltx-i2v.json`. Install models:

```bash
bash workflows/setup/ltx-23-i2v-official.sh
```
