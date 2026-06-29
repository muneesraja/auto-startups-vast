---
name: story-maker
version: 2.0.0
description: "ADK multi-agent story-to-video: narrative planning, dynamic Grok reference strategy, LTX 2.3 I2V with native audio."
triggers:
  - story-maker
  - story-maker-v2
---

# Story Maker V2 — ADK Multi-Agent Pipeline

Turns a raw story into a short animated film using a Google ADK `Workflow` graph with specialized LLM agents and deterministic generation nodes.

## Pipeline

1. **Story Planner** — bible, characters, scenes, shot briefs → `story_plan.json`
2. **Timeline Enricher** — computes `scene_time_offset_seconds` and `continuity_from_previous` per shot
3. **Audio Planner** — per-shot audio, transitions → `audio_plan.json`
4. **Scene Asset Planner** — background plate decisions (`style_anchor` vs `full_plate`) → `scene_assets.json`
5. **Parallel prompters** (fan-out):
   - Character Sheet Prompter
   - Shot Reference Strategist (char sheets only for `style_anchor` scenes; per-shot `environment_state`)
   - Motion Prompter (timeline-aware LTX 2.3 I2V + native audio)
6. **Merge + validate** → `generation_specs.json`
7. **Generation** — backgrounds → char sheets → shot images → videos → `final_film.mp4`

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
  --story "A curious monkey finds a glowing gem..." \
  --name "monkey_adventure"
```

### Flags

| Flag | Description |
|------|-------------|
| `--fresh` | Wipe artifacts and replan from scratch |
| `--stop-before-generation` | Run planning + specs only; skip fal/ComfyUI |
| `--only-scenes` | Generate only listed scene ids (e.g. `scene_01`) |
| `--story-file` | Read story from file |

Resume is automatic: re-run the same `--name` and the `resume_router_node` picks up from the earliest missing artifact.

## Background reference modes

| Mode | Use case | Grok Edit reference |
|------|----------|---------------------|
| `style_anchor` | Dynamic exteriors (water, wind, clouds) | Character sheets only; plate is art-direction doc |
| `full_plate` | Static interiors | Character sheets + background plate |

## Scene timeline

Shots within a scene are time-ordered. The timeline enricher sets `scene_time_offset_seconds` from prior shot durations. Story planner authors `environment_state` and `pace` per shot; motion prompter uses both for environment animation and beat density.

## Output layout

```
outputs/story-maker/<name>/
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
