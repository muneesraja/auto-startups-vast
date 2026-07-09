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

0. **Scene Paper Author** — raw story + target duration → `scene_paper.md` (scene-by-scene rewrite; source of truth for all planning)
0.5. **Storyboard Sheet Scene Splitter** — *storyboard-mode profiles only (`reel_v2`)* — `scene_paper.md` → `story_sheet_scene.md`, a mechanical sheet map that chunks each scene paper scene into 2×5/10-panel storyboard sheets. It never rewrites content, only pins the exact sheet count/boundaries so the narrative expander and shot director can't silently invent extra sheets or duplicate a scene across sheets. Per-shot profiles (`cinematic`, `reels`) skip this step entirely.
1. **Narrative Expander** — `scene_paper.md` (+ `story_sheet_scene.md` when present) + target duration → `narrative_outline.json` (acts, scene beats, budgets)
2. **LTX Shot Director** — outline → `story_plan.json` (4–16s shots, scene-first, fewer longer clips)
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
- Grok still images via **`PROVIDER`**:
  - `PROVIDER=fal` → `FAL_KEY` (default)
  - `PROVIDER=replicate` → `REPLICATE_API_TOKEN` (default: `openai/gpt-image-2`, quality `low`)
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
| `--style` | Story style profile: `cinematic`, `reels`, or `reel_v2` |
| `--target-duration` | Target runtime: `300`, `5m`, `5min` (default depends on `--style`) |
| `--duration-tolerance` | Allowed deviation percent (default 15) |
| `--fresh` | Wipe artifacts and replan from scratch |
| `--stop-before-generation` | Run through Grok images + vision motion prompts; skip LTX video |
| `--only-scenes` | Generate only listed scene ids (e.g. `scene_01`) |
| `--story-file` | Read story from file |
| `--planning-model` | OpenRouter model for both planning agents (e.g. `z-ai/glm-5.2`) |
| `--narrative-expander-model` | Model for `narrative_outline.json` only |
| `--story-plan-model` | Model for `story_plan.json` only |
| `--image-provider` | Grok image backend: `fal` or `replicate` (sets `PROVIDER`) |
| `--sequential-shots` | Sequentially author shot still prompts within each scene using the previous generated frame as continuity context |

### Style profiles

| Style | Purpose | Default target (if omitted) | Shot duration range |
|------|---------|------------------------------|---------------------|
| `cinematic` | Scene-first films with fewer longer clips | `120s` | `4-16s` |
| `reels` | Fast short-form with rapid visual rhythm | `30s` | `1-4s` |
| `reel_v2` | Storyboard-sheet pipeline: multi-panel sheets → vision crop → panel regen | `30s` | `1-4s` |

Selection precedence: `--style` CLI flag > `STORY_STYLE` in `.env` > `cinematic`.

### Continuity modes

| Mode | Behavior | Tradeoff |
|------|----------|----------|
| Default | Batch prompt all shot stills, then generate in parallel | Fastest |
| `--sequential-shots` | Within each scene, shot N prompt is authored after shot N-1 exists | Better visual continuity, slower and more vision calls |

### Model tiers (swappable via `.env`)

Three LLM tiers — all use OpenRouter slugs unless noted:

| Tier | Agents | Env var | Default |
|------|--------|---------|---------|
| **Planning** | scene paper author, storyboard sheet scene splitter, narrative expander, LTX shot director | `PLANNING_MODEL` / `NARRATIVE_EXPANDER_MODEL` / `STORY_PLAN_MODEL` | `openai/gpt-5.4-mini` |
| **Secondary** | audio, scene assets, char sheets, shot images | `SECONDARY_MODEL` (alias: `LIGHT_MODEL`) | `openai/gpt-5.4-mini` |
| **Vision** | vision motion prompter (multimodal) | `VISION_MODEL` | `openai/gpt-5-mini` |
| **Crop analysis** | storyboard panel bbox JSON (`reel_v2`) | `CROP_ANALYSIS_MODEL` | `openai/gpt-5.4-mini` |

| Env var | Description | Default |
|---------|-------------|---------|
| `PLANNING_MODEL_TIMEOUT` | Planning agent timeout (seconds) | `600` |
| `PLANNING_REASONING_EFFORT` | Reasoning effort for planning models (`low`, `medium`, `high`) | `low` |
| `SECONDARY_REASONING_EFFORT` | Reasoning effort for secondary models | `low` |
| `SECONDARY_MODEL_TIMEOUT` | Secondary agent timeout (seconds) | `600` |
| `GROK_IMAGE_RESOLUTION` | Grok T2I/Edit resolution (`1k`, etc.) | `1k` |
| `BACKGROUND_IMAGE_SIZE` | Panoramic background plate size (GPT Image 2 WxH) | `2048x1024` |
| `STORYBOARD_SHEET_SIZE` | Storyboard sheet render size (GPT Image 2 WxH, 16:9) | `2048x1152` |
| `PROVIDER` | Grok image backend: `fal` or `replicate` | `fal` |
| `STORY_STYLE` | Style profile fallback when `--style` is omitted | `cinematic` |
| `SEQUENTIAL_SHOT_PROMPTS` | Opt into sequential within-scene shot prompting | `off` |
| `REPLICATE_API_TOKEN` | Required when `PROVIDER=replicate` | — |
| `GROK_REPLICATE_MODEL` | Replicate model slug | `openai/gpt-image-2` |
| `REPLICATE_IMAGE_QUALITY` | GPT Image quality on Replicate (`low`, `medium`, `high`) | `low` |
| `CROP_ANALYSIS_MODEL` | Storyboard panel bbox vision model (`reel_v2`) | `openai/gpt-5.4-mini` |
| `IMAGE_REF_LIMIT` | Override max reference images per shot edit (optional) | provider default |

Reference image caps per edit (when `IMAGE_REF_LIMIT` unset): fal Grok Edit **3**; Replicate GPT Image 2 **13**; Seedream 4 **10**; legacy Replicate Grok **1**. Probe script: `scripts/ref_limit_probe.py`.

```bash
# .env — recommended cost-optimized mix
PLANNING_MODEL=openai/gpt-5.4-mini
PLANNING_REASONING_EFFORT=low
SECONDARY_MODEL=openai/gpt-5.4-mini
SECONDARY_REASONING_EFFORT=low
VISION_MODEL=openai/gpt-5-mini
BACKGROUND_IMAGE_SIZE=2048x1024
STORYBOARD_SHEET_SIZE=2048x1152

# CLI (applied before agents load)
python3 main.py --story-file ../../stories/baby-star/Story.md \
  --name baby-star-claude --planning-model anthropic/claude-sonnet-4.6 --fresh

# Reels profile (defaults to 30s if --target-duration omitted)
python3 main.py --story-file ../../stories/baby-star/Story.md \
  --name baby-star-reel --style reels --fresh

# Higher-fidelity continuity inside each scene
python3 main.py --story-file ../../stories/baby-star/Story.md \
  --name baby-star-seq --style cinematic --sequential-shots --fresh

# reel_v2: storyboard sheets + vision crop + panel regen (no background plates)
python3 main.py --story-file ../../stories/story-naila/Story.md \
  --name story-naila-reel-v2 --style reel_v2 --target-duration 30s --fresh
```

**Resume glider-and-rara (scenes 02+) when fal is locked** — set `PROVIDER=replicate` and `REPLICATE_API_TOKEN`, then:

```bash
cd skills/story-maker
PROVIDER=replicate python3 main.py \
  --story-file ../../stories/glider-and-rara/Story.md \
  --name glider-and-rara --target-duration 5m
```

Or pass `--image-provider replicate` instead of setting `PROVIDER` in `.env`.

Saved artifacts include `_meta` with `narrative_model`, `story_plan_model`, `secondary_model`, and `vision_model` for A/B comparison.

### Director: starting frame first

Each shot in `story_plan.json` includes `frame_strategy`:

| Value | Starting still | Motion |
|-------|----------------|--------|
| `empty_then_enter` | Empty/quiet plate | Subject enters frame |
| `at_rest_then_react` | Subject at rest | Trigger → reaction |
| `in_action_continuous` | Mid-activity hold | Motion continues |

For spatial continuity, scenes may also include `staging` + `blocking`, and shots may include `subject_position`, `facing_direction`, `eyeline`, and `background_region`. These keep shot-reverse-shot dialogue and solo reaction angles spatially coherent against the same room geography.

### Grok image quality

- All Grok prompts append a no-text clause (no subtitles, labels, watermarks).
- Images are 16:9 landscape (better LTX I2V motion than portrait).
- Motion prompts open with `A cinematic scene of ...` and end with quality tags.

Resume is automatic: re-run the same `--name` and the `resume_router_node` picks up from the earliest missing artifact.

## LTX shot sizing

| Complexity | Duration | Use for |
|------------|----------|---------|
| simple | 5–8s | insert, reaction, single gesture |
| moderate | 8–12s | standard action beat |
| complex | 12–16s | one camera beat, max 2–3 micro-beats |

For `--style reels` or `reel_v2`, durations are constrained to `1-4s` to support short-form pacing.

### reel_v2 image pipeline

`reel_v2` skips per-shot parallel still generation and background plates. Instead:

1. Character sheets (GPT-image-2 `medium`, portrait `1024x1536`) are built from `Research/story-board/Character-sheet.md` via `prompts/reel_v2/character_sheet_template.md` — full profile, turnaround, expressions, scale, poses, and close-ups.
2. Per-scene storyboard sheets (strict 10 panels, 2×5) are built from `Research/story-board/Compiled-storyboard-sheet-prompt.md` via `prompts/reel_v2/storyboard_sheet_template.md`, with character consistency and environment canon from `Character-consistency.md`.
3. `CROP_ANALYSIS_MODEL` vision returns panel bounding boxes as JSON.
4. Python crops each panel to `panel_crops/`.
5. GPT-image-2 (low) regenerates each crop at full 16:9 into `images/` using crop + character refs.

Motion/video stages are unchanged.

Motion prompts are I2V-native: written from the actual starting frame — role + position referents, no appearance re-description.

## Background reference modes

| Mode | Use case | Grok Edit reference |
|------|----------|---------------------|
| `style_anchor` | Dynamic exteriors | Character sheets only |
| `full_plate` | Static interiors | Char sheets + `scene_id` background plate |

## Output layout

```
outputs/story-maker/<name>/
├── scene_paper.md
├── story_sheet_scene.md  # reel_v2 (storyboard mode) only
├── narrative_outline.json
├── story_plan.json
├── audio_plan.json
├── scene_assets.json
├── generation_specs.json
├── backgrounds/
├── characters/
├── storyboard_sheets/   # reel_v2 only
├── panel_crops/         # reel_v2 only
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
