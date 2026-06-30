---
name: story-maker
version: 2.2.0
description: "ADK multi-agent story-to-video: vision-grounded LTX motion prompts, Grok refs, LTX 2.3 I2V."
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
7. **Parallel prompters** (char sheets + shot images) → `generation_specs.json`
8. **Generation** — backgrounds → char sheets → shot images → **vision motion prompter** → LTX I2V → `final_film.mp4`

Motion prompts are authored **after** shot PNGs exist: GPT-5-mini vision sees each starting frame plus full scene/shot/audio context and writes the LTX `motion_prompt`.

See [`assets/ltx-2.3-director-bible.md`](assets/ltx-2.3-director-bible.md) for LTX constraints.

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
  --story-file ../../stories/baby-star/Story.md \
  --name baby-star \
  --target-duration 5m \
  --stop-before-generation
```

### Flags

| Flag | Description |
|------|-------------|
| `--target-duration` | Target runtime: `300`, `5m`, `5min` (default 120s if omitted) |
| `--duration-tolerance` | Allowed deviation percent (default 15) |
| `--fresh` | Wipe artifacts and replan from scratch |
| `--stop-before-generation` | Run through Grok images + vision motion prompts; skip LTX video |
| `--only-scenes` | Generate only listed scene ids (e.g. `scene_01`) |
| `--story-file` | Read story from file |
| `--planning-model` | OpenRouter model for both planning agents (e.g. `z-ai/glm-5.2`) |
| `--narrative-expander-model` | Model for `narrative_outline.json` only |
| `--story-plan-model` | Model for `story_plan.json` only |

### Model tiers (swappable via `.env`)

Three LLM tiers — all use OpenRouter slugs unless noted:

| Tier | Agents | Env var | Default |
|------|--------|---------|---------|
| **Planning** | narrative expander, LTX shot director | `PLANNING_MODEL` / `NARRATIVE_EXPANDER_MODEL` / `STORY_PLAN_MODEL` | `openai/gpt-5-mini` |
| **Secondary** | audio, scene assets, char sheets, shot images | `SECONDARY_MODEL` (alias: `LIGHT_MODEL`) | `z-ai/glm-5.2` |
| **Vision** | vision motion prompter (multimodal) | `VISION_MODEL` | `openai/gpt-5-mini` |

| Env var | Description | Default |
|---------|-------------|---------|
| `PLANNING_MODEL_TIMEOUT` | Planning agent timeout (seconds) | `600` |
| `SECONDARY_MODEL_TIMEOUT` | Secondary agent timeout (seconds) | `600` |
| `GROK_IMAGE_RESOLUTION` | Grok T2I/Edit resolution (`1k`, etc.) | `1k` |

```bash
# .env — recommended production mix
PLANNING_MODEL=anthropic/claude-sonnet-4.6
SECONDARY_MODEL=z-ai/glm-5.2
VISION_MODEL=openai/gpt-5-mini

# or per planning stage
NARRATIVE_EXPANDER_MODEL=anthropic/claude-sonnet-4.6
STORY_PLAN_MODEL=anthropic/claude-sonnet-4.6

# CLI (applied before agents load)
python3 main.py --story-file ../../stories/baby-star/Story.md \
  --name baby-star-claude --planning-model anthropic/claude-sonnet-4.6 --fresh
```

Saved artifacts include `_meta` with `narrative_model`, `story_plan_model`, `secondary_model`, and `vision_model` for A/B comparison.

### Director: starting frame first

Each shot in `story_plan.json` includes `frame_strategy`:

| Value | Starting still | Motion |
|-------|----------------|--------|
| `empty_then_enter` | Empty/quiet plate | Subject enters frame |
| `at_rest_then_react` | Subject at rest | Trigger → reaction |
| `in_action_continuous` | Mid-activity hold | Motion continues |

### Grok image quality

- All Grok prompts append a no-text clause (no subtitles, labels, watermarks).
- Images are 16:9 landscape (better LTX I2V motion than portrait).
- Motion prompts open with `A cinematic scene of ...` and end with quality tags.

Resume is automatic: re-run the same `--name` and the `resume_router_node` picks up from the earliest missing artifact.

## LTX shot sizing

| Complexity | Duration | Use for |
|------------|----------|---------|
| simple | 4–6s | insert, reaction, single gesture |
| moderate | 7–10s | standard action beat |
| complex | 11–15s | one camera beat, max 2–3 micro-beats |

Motion prompts are I2V-native: written from the actual starting frame — role + position referents, no appearance re-description.

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
