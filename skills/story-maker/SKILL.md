---
name: story-maker
version: 2.3.0
description: "ADK multi-agent story-to-video: vision-grounded LTX motion prompts, Grok refs, LTX 2.3 I2V."
triggers:
  - story-maker
  - story-maker-v2
---

# Story Maker V2 — ADK Multi-Agent Pipeline

Turns a high-level story into an animated film using a Google ADK `Workflow` graph with LTX 2.3-aware planning and generation.

## Durable artifacts

| File | Role |
|------|------|
| `developed_story.md` | I2V-aware story rewrite sized to target duration (default LLM; skippable) |
| `scene_paper.md` | Visual production paper from developed story (LLM) |
| `plan.json` | Production pack: shots, light audio, assets, video_shots (1 LLM + code normalize) |
| `generation_specs.json` | Runtime paths/URLs/status (mostly code-built) |

Legacy split files (`narrative_outline.json`, `story_plan.json`, `audio_plan.json`, etc.) are no longer written. Existing output dirs still resume via an on-the-fly adapter that synthesizes `plan.json`.

## Pipeline

0. **Story Developer** — raw story → `developed_story.md` (expands thin sources; I2V co-presence rules). Skip with `--skip-story-developer`.
0.5. **Scene Paper Author** — developed story → `scene_paper.md` (visual coverage, not new plot)
0.6. **Sheet map (code)** — *`reel_v2` only* — deterministic 5×2 panel chunking from scene paper (in-memory; not a resume artifact)
1. **Production Plan Author** — scene paper (+ sheet map) → `plan.json` (shots + nested audio/assets + video_shots for storyboard)
2. **Timeline Enricher + Duration Budget Validator** — offsets, continuity, scene budget reconcile
3. **Build generation specs** — code for `reel_v2`; per-shot profiles still fan out char/shot LLM prompters into specs
4. **Generation** — backgrounds (if any) → char sheets → shot images / storyboard sheets → **vision motion prompter** → LTX I2V → `final_film.mp4`

Motion prompts are authored **after** shot PNGs exist: vision sees each starting frame plus scene/shot/audio context and writes the LTX `motion_prompt`.

See [`assets/ltx-2.3-director-bible.md`](assets/ltx-2.3-director-bible.md) for LTX constraints.

## Requirements

- `OPENROUTER_API_KEY` (or `GEMINI_API_KEY` / `MINIMAX_API_KEY`)
- Still images (split backends for `reel_v2`):
  - **`PROVIDER=replicate`** (default) → `REPLICATE_API_TOKEN` for character/location sheets and panel regen primary
  - **`STORYBOARD_IMAGE_PROVIDER=fal`** (default) → `FAL_KEY` for storyboard album sheets (GPT Image 2 edit + refs; no T2I fallback)
  - Model: `openai/gpt-image-2` (Replicate and fal)
  - Character sheets: quality `medium`, size `1152x2048`
  - Storyboard sheets: quality `medium`, size `1152x2048` (9:16 album)
  - Panel regen / shot stills: quality `low`, size `2048x1152`
  - Panel regen ladder: Replicate edit → Replicate crop-only → **fal edit fallback** (`PANEL_IMAGE_FALLBACK_PROVIDER=fal`) → soft crop-copy last
  - Legacy global `PROVIDER=fal` (Grok Imagine) is optional only — not used for new runs
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
  --plan-only
```

### Flags

| Flag | Description |
|------|-------------|
| `--style` | Story style profile: `cinematic`, `reels`, or `reel_v2` |
| `--target-duration` | Target runtime: `300`, `5m`, `5min` (default depends on `--style`) |
| `--duration-tolerance` | Allowed deviation percent (default 15) |
| `--fresh` | Wipe artifacts and replan from scratch |
| `--skip-story-developer` | Copy raw story into `developed_story.md` (no LLM rewrite) |
| `--plan-only` | Run planning + write `cost_estimate.json`; skip paid generation |
| `--stop-before-generation` | Run through Grok images + vision motion prompts; skip LTX video |
| `--only-scenes` | Generate only listed scene ids (e.g. `scene_01`) |
| `--story-file` | Read story from file |
| `--planning-model` | OpenRouter model for planning agents (e.g. `z-ai/glm-5.2`) |
| `--story-plan-model` | Model for `plan.json` author |
| `--image-provider` | Image backend: `replicate` (default) or legacy `fal` (sets `PROVIDER`) |
| `--sequential-shots` | Sequentially author shot still prompts within each scene using the previous generated frame as continuity context |

### Style profiles

| Style | Purpose | Default target (if omitted) | Shot duration range |
|------|---------|------------------------------|---------------------|
| `cinematic` | Scene-first films with fewer longer clips | `120s` | Primary `{6,8,10}` (optional 3–15) |
| `reels` | Fast short-form with LTX-native clip lengths | `30s` | Primary `{6,8,10}` (optional 3–15) |
| `reel_v2` | Storyboard-sheet pipeline: panels → crop → regen; LTX via `video_shots` | `30s` | Panels editorial 1–4; video shots `{6,8,10}` |

Selection precedence: `--style` CLI flag > `STORY_STYLE` in `.env` > `cinematic`.

### Continuity modes

| Mode | Behavior | Tradeoff |
|------|----------|----------|
| Default | Batch prompt all shot stills, then generate in parallel | Fastest |
| `--sequential-shots` | Within each scene, shot N prompt is authored after shot N-1 exists | Better visual continuity, slower and more vision calls |

### Model tiers (swappable via `.env`)

| Tier | Agents | Env var | Default |
|------|--------|---------|---------|
| **Planning** | scene paper author, production plan author | `PLANNING_MODEL` / `STORY_PLAN_MODEL` | `openai/gpt-5.4-mini` |
| **Secondary** | char sheets + shot images (per-shot profiles) | `SECONDARY_MODEL` (alias: `LIGHT_MODEL`) | `openai/gpt-5.4-mini` |
| **Vision** | vision motion prompter (multimodal) | `VISION_MODEL` | `openai/gpt-5-mini` |
| **Crop analysis** | storyboard panel bbox JSON (`reel_v2`) | `CROP_ANALYSIS_MODEL` | `openai/gpt-5.4-mini` |

| Env var | Description | Default |
|---------|-------------|---------|
| `PLANNING_MODEL_TIMEOUT` | Planning agent timeout (seconds) | `600` |
| `PLANNING_REASONING_EFFORT` | Reasoning effort for planning models (`low`, `medium`, `high`) | `low` |
| `SECONDARY_REASONING_EFFORT` | Reasoning effort for secondary models | `low` |
| `SECONDARY_MODEL_TIMEOUT` | Secondary agent timeout (seconds) | `600` |
| `PROVIDER` | Default still-image backend for chars/locs/panel primary (`replicate` or legacy `fal`) | `replicate` |
| `STORYBOARD_IMAGE_PROVIDER` | Storyboard album sheets only (`fal` or `replicate`) | `fal` |
| `PANEL_IMAGE_PROVIDER` | Panel regen primary override (defaults to `PROVIDER`) | (inherits) |
| `PANEL_IMAGE_FALLBACK_PROVIDER` | Panel regen fallback after primary fails (`fal` / `none`) | `fal` when primary is replicate + `FAL_KEY` set |
| `FAL_KEY` | Required for fal storyboard sheets and panel fal fallback | — |
| `REPLICATE_API_TOKEN` | Required when `PROVIDER=replicate` | — |
| `GROK_REPLICATE_MODEL` | Replicate model slug | `openai/gpt-image-2` |
| `GROK_FAL_MODEL` | Optional fal model override (defaults to GPT Image 2) | (inherits) |
| `REPLICATE_SHEET_QUALITY` | Quality for character + storyboard sheets | `medium` |
| `REPLICATE_PANEL_QUALITY` | Quality for panel regen / shot stills | `low` |
| `REPLICATE_IMAGE_QUALITY` | Fallback quality when a call omits quality | `low` |
| `CHARACTER_SHEET_SIZE` | Char sheet Replicate `aspect_ratio` (pixel enum) | `1152x2048` |
| `STORYBOARD_SHEET_SIZE` | Storyboard sheet size (portrait album) | `1152x2048` |
| `PANEL_IMAGE_SIZE` | Panel regen / shot still size | `2048x1152` |
| `BACKGROUND_IMAGE_SIZE` | Background plate size (when used) | `2048x1152` |
| `STORY_STYLE` | Style profile fallback when `--style` is omitted | `cinematic` |
| `SEQUENTIAL_SHOT_PROMPTS` | Opt into sequential within-scene shot prompting | `off` |
| `CROP_ANALYSIS_MODEL` | Storyboard panel bbox vision model (`reel_v2`) | `openai/gpt-5.4-mini` |
| `IMAGE_REF_LIMIT` | Override max reference images per shot edit (optional) | provider default |

Reference image caps per edit (when `IMAGE_REF_LIMIT` unset): Replicate GPT Image 2 **13**; Seedream 4 **10**; legacy fal Grok Edit **3**. Probe script: `scripts/ref_limit_probe.py`.

```bash
# .env — recommended cost-optimized mix
PLANNING_MODEL=openai/gpt-5.4-mini
PLANNING_REASONING_EFFORT=low
SECONDARY_MODEL=openai/gpt-5.4-mini
SECONDARY_REASONING_EFFORT=low
VISION_MODEL=openai/gpt-5-mini
PROVIDER=replicate
STORYBOARD_IMAGE_PROVIDER=fal
# PANEL_IMAGE_FALLBACK_PROVIDER=fal
GROK_REPLICATE_MODEL=openai/gpt-image-2
CHARACTER_SHEET_SIZE=1152x2048
STORYBOARD_SHEET_SIZE=1152x2048
PANEL_IMAGE_SIZE=2048x1152
BACKGROUND_IMAGE_SIZE=2048x1152

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

Each shot in `plan.json` includes `frame_strategy`:

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

**Authoritative:** `assets/ltx-2.3-director-bible.md`. Primary **`{6, 8, 10}`** (default **8**); optional **3–15**.

| Complexity | Duration | Use for |
|------------|----------|---------|
| simple | 6–8s | insert, reaction, single gesture |
| moderate | 8s | standard action beat |
| complex | split into multiple 6–10s | one continuous idea only; prefer split over long clips |

`reel_v2` keeps dense storyboard **panels** for coverage; LTX clip duration lives on **`video_shots`**. Groups must be **cast-coherent** to the anchor still (`characters_present` ⊆ anchor cast; empty establishing panels are solo/env-only). Motion prompts must be dense timed physical arcs (anti-freeze) even at 6s — vision must not invent cast absent from the start frame.

Repair an existing run's `video_shots` without `--fresh`:

```bash
cd skills/story-maker
.venv/bin/python scripts/repair_video_shots_cast.py ../../outputs/story-maker/<name>
```

### Storyboard assistant director (I2V + FLF2V)

After panel stills exist, vision acts as assistant director: reads the **full storyboard sheet** + the scene block from `scene_paper.md` (editorial agenda) + **5×2 grid row/col map**, and returns hard-cut **segments** of clips:

- `start == end` → standalone **I2V**
- continuous adjacent panels with shared endpoints (`02→03`, then `03→04`) → **FLF2V**
- same-row pairs preferred for FLF; motivated **camera pans/turns** may bridge to a newly revealed subject (e.g. point → what she points at)
- cast/subject jumps without a camera bridge → new segment (editorial cut)

The assistant director **chooses** each clip duration and the scene total (prefer LTX **6–10s**; **3s** only for super-short beats; max **10s**). Scene-paper duration lines are not used as a hard budget.

Plans persist under `generation_specs.storyboard_video_scenes` (legacy mirror: `flf2v_scenes`).

```bash
cd skills/story-maker
# Opt into the director path in the main pipeline
export STORYBOARD_VIDEO_MODE=director

# Manual scene runner — plan only
VISION_MODEL=openai/gpt-5-mini .venv/bin/python scripts/run_flf_scene.py \
  --output-dir ../../outputs/story-maker/<name> \
  --scene scene_01 --plan-only

# Plan + generate all clips
VISION_MODEL=openai/gpt-5-mini .venv/bin/python scripts/run_flf_scene.py \
  --output-dir ../../outputs/story-maker/<name> \
  --scene scene_01

# Generate from a saved plan
.venv/bin/python scripts/run_flf_scene.py \
  --output-dir ../../outputs/story-maker/<name> \
  --scene scene_01 --generate-only
```

Default `STORYBOARD_VIDEO_MODE=fallback` keeps the existing `video_shots` → vision motion → I2V path.

`scripts/smoke_flf2v_storyboard.py` redirects to the same runner.


### reel_v2 image pipeline

`reel_v2` skips per-shot parallel still generation and background plates. Instead:

1. Character sheets (GPT-image-2 `medium`, portrait `1024x1536`) are built from `Research/story-board/Character-sheet.md` via `prompts/reel_v2/character_sheet_template.md` — full profile, turnaround, expressions, scale, poses, and close-ups.
2. Per-scene storyboard sheets (strict 10 panels, 5×2 album on 9:16; each panel 16:9) are built from `Research/story-board/Compiled-storyboard-sheet-prompt.md` via `prompts/reel_v2/storyboard_sheet_template.md`, with character consistency and environment canon from `Character-consistency.md`.
3. Python detects thin white gutters on the 5×2 album sheet and crops each panel to `panel_crops/` (`STORYBOARD_CROP_MODE=python`, default). Uniform grid is the fallback; set `vision` to use `CROP_ANALYSIS_MODEL` instead.
4. GPT-image-2 (`low` quality, `2048x1152`) regenerates each crop into `images/` using crop + character refs.

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
├── plan.json
├── generation_specs.json
├── cost_estimate.json   # with --plan-only
├── backgrounds/
├── characters/
├── locations/           # reel_v2 location locks
├── storyboard_sheets/   # reel_v2 (sequential; prev sheet as continuity ref)
├── panel_crops/         # reel_v2 only
├── images/
├── videos/
└── final_film.mp4
```

`reel_v2` uses `locations/{location_id}.png` establishing locks and generates storyboard sheets via fal GPT Image 2 edit in story order (location + previous sheet + character refs; no T2I fallback). Panel regen uses crop + character refs only (Replicate primary, fal fallback; no location plate). Cinematic `backgrounds/` plates are not used in reel_v2.

Override base dir with `STORY_MAKER_OUTPUT_DIR` in `.env`.

## ComfyUI

Uses `assets/workflow-templates/ltx-i2v.json`. Install models:

```bash
bash workflows/setup/ltx-23-i2v-official.sh
```
