# Story Maker — Agent Guide

Use this skill to turn a written story into an AI-animated film or reel. You talk to the agent in plain language, and it plans the narrative, directs shots, generates still frames, writes motion prompts, renders video clips, and concatenates the final film.

**Output root:** `outputs/story-maker/<name>/`

---

## How to invoke the skill

Mention any of these in your prompt so the agent loads `story-maker`:

- `@story-maker`
- "use the story-maker skill"
- "make a film from this story"
- "generate a reel from this story"
- "turn this story into a video"

On Hermes/VPS or locally, the agent runs from the repo and uses `skills/story-maker/`. Credentials live in the repo `.env` or your shared environment.

---

## Prompting examples

### Make a cinematic short film

> Use the story-maker skill to make a 2 minute cinematic film from `stories/story-naila/Story.md`.

> Generate a story-maker film from `stories/baby-star/Story.md` with a calm cinematic style.

> Run `story-maker` on `stories/story-naila/Story.md` and target 90 seconds.

### Make a fast reel

> Use the story-maker skill to turn `stories/story-naila/Story.md` into a 30 second reel.

> Generate a fast-paced reels version of `stories/baby-star/Story.md`.

> Make a short-form vertical-style reel rhythm from this story using the `reels` style profile.

> Use story-maker `reel_v2` for storyboard-sheet consistency on `stories/story-naila/Story.md`.

### Better continuity

> Run story-maker in reels mode with sequential shots for stronger continuity.

> Generate this film with higher-fidelity shot-to-shot continuity using the previous frame for each next shot.

> Use the story-maker skill with sequential shots enabled.

### Planning only / stop before videos

> Use story-maker to plan and generate images only for `stories/story-naila/Story.md` — stop before video generation.

> Run story-maker through stills and motion prompts, but do not render final videos yet.

### Partial reruns / resume

> Resume the `baby-star` story-maker run.

> Re-run only `scene_02` and `scene_03` for the `baby-star` output.

> Continue the failed story-maker run named `story-naila-v1`.

### Model / provider overrides

> Run story-maker in reels mode using Replicate for images.

> Generate this story with `gpt-5.4-mini` for planning and keep GLM as the secondary model.

> Use the story-maker skill with `--style reels`, Replicate image generation, and a 30 second target.

---

## What to put in your prompt

The agent can infer a lot, but including these makes runs more reliable:

| You say | Why it helps |
|---------|--------------|
| **Story path** (`stories/story-naila/Story.md`) | Tells the agent what source story to use |
| **Output name** (`naila-reel-v1`) | Makes reruns/resume predictable |
| **Style** (`cinematic`, `reels`, or `reel_v2`) | Picks the right directing and image pipeline |
| **Target duration** (`30s`, `90s`, `5m`) | Controls pacing and shot count |
| **Sequential shots** | Opts into higher-fidelity continuity |
| **Stop before generation** | Useful for reviewing plans/stills first |
| **Provider** (`replicate`, default) | Chars/locs/panel primary; storyboard sheets use fal by default |
| **Only scenes** (`scene_02`) | Lets the agent rerun a subset |

You do **not** need to remember every CLI flag. Plain English is enough.

---

## What the agent does (behind the scenes)

1. Rewrites the source into `developed_story.md` (I2V-aware; expands thin stories to the target duration)
2. Writes `scene_paper.md` (visual production coverage of the developed story)
3. Authors a single `plan.json` (shots, light audio, assets, and for `reel_v2` video_shots)
4. Builds `generation_specs.json` (runtime paths / status)
5. Generates character / location sheets (Replicate) and storyboard albums (fal GPT Image 2 by default), then panel stills (Replicate primary, fal fallback)
6. Creates still images for each shot / storyboard panels
7. Uses a vision model to write motion prompts from the actual starting frames
8. Renders LTX image-to-video clips
9. Concatenates them into `final_film.mp4`

If sequential shots are enabled, the agent also re-authors each shot still prompt after seeing the previous generated frame within the same scene.

---

## Style profiles

| Style | Best for | Default target | Shot rhythm |
|------|----------|----------------|-------------|
| `cinematic` | Short films, scene-first storytelling, slower breathing shots | `120s` | Fewer longer shots |
| `reels` | Short-form content; LTX-native clip lengths | `30s` | Primary `{6,8,10}` (optional 3–15) |
| `reel_v2` | Storyboard-sheet consistency: multi-panel sheets → crop → regen | `30s` | Panels editorial; LTX via `video_shots` `{6,8,10}` |

`reel_v2` does **not** use cinematic `backgrounds/` plates or per-shot parallel still prompting. It generates **location lock** plates (`locations/`), then per-scene 8-panel 4×2 photo-album sheets (**8:9** page / `1024x1152` so packed cells are ~**16:9**) **in story order** (each sheet after the first gets the previous sheet PNG as a continuity ref, plus location + character refs). Each album **row** is a preferred FLF start→end pair (left=start, right=end). It uses Python white-gutter detection to crop panels (`STORYBOARD_CROP_MODE=python`; optional `vision`), then regenerates each panel at full resolution with character references only. LTX duration is planned on **`video_shots`** (primary `{6,8,10}`, default 8; optional 3–15) by grouping consecutive panels that stay **cast-coherent** to the anchor still — panels are editorial coverage, not 1s Pro clips. Empty establishing panels do not share a clip with character entrances.

**FLF2V / assistant-director alt path:** set `STORYBOARD_VIDEO_MODE=director` to plan I2V standalones + FLF2V continuous chains from the storyboard sheet, `scene_paper.md` agenda, and 4×2 grid row/col map after panel regen. Prefer same-row FLF; motivated camera pans may reveal new subjects. The assistant director chooses per-clip durations (prefer LTX 6–10s; 3s only for super-short beats) plus `motion_class` / `guidance` enums (mapped to image-lock strength and CFG). Default LTX resolution is **1920×1088**. Manual runner: `scripts/run_flf_scene.py`. Default remains the existing `video_shots` I2V path (`STORYBOARD_VIDEO_MODE=fallback`). See `SKILL.md` and `plans/ad-ltx-strength-cfg-resolution.md`.




Selection precedence:

1. `--style`
2. `STORY_STYLE` in `.env`
3. default `cinematic`

---

## Continuity modes

| Mode | What it does | Tradeoff |
|------|---------------|----------|
| Default | All shot still prompts are authored first, then stills are generated in parallel | Fastest |
| Sequential shots | Inside each scene, the next shot prompt is authored after seeing the previous frame | Better visual continuity, slower and more vision calls |

Use sequential mode for:

- shot-reverse-shot dialogue
- tight reels where continuity errors are obvious
- scenes where geography / eyeline consistency matters

Leave it off for:

- quick experiments
- cheap drafts
- long-form iterations where speed matters more than pixel-perfect continuity

---

## Environment variables

Minimum setup for most runs:

```bash
OPENROUTER_API_KEY=...
REPLICATE_API_TOKEN=...
COMFYUI_URL=http://localhost:8188

STORY_STYLE=cinematic
# STORY_STYLE=reels
# STORY_STYLE=reel_v2

PLANNING_MODEL=openai/gpt-5.4-mini
PLANNING_REASONING_EFFORT=low
SECONDARY_MODEL=openai/gpt-5.4-mini
VISION_MODEL=openai/gpt-5-mini
# CROP_ANALYSIS_MODEL=openai/gpt-5.4-mini  # only if STORYBOARD_CROP_MODE=vision
# STORYBOARD_CROP_MODE=python

PROVIDER=replicate
STORYBOARD_IMAGE_PROVIDER=fal
# CHARACTER_SHEET_IMAGE_PROVIDER=fal
# PANEL_IMAGE_PROVIDER=replicate
# PANEL_IMAGE_FALLBACK_PROVIDER=none
GROK_REPLICATE_MODEL=openai/gpt-image-2
# Sheets: medium @ 2K; panel regen: low @ 2K
# REPLICATE_SHEET_QUALITY=medium
# CHARACTER_SHEET_SIZE=1152x2048
# STORYBOARD_SHEET_SIZE=1024x1152
# REPLICATE_PANEL_QUALITY=low
# PANEL_IMAGE_SIZE=2048x1152
# BACKGROUND_IMAGE_SIZE=2048x1152
# SEQUENTIAL_SHOT_PROMPTS=1
```

Important env vars:

| Env var | Meaning |
|---------|---------|
| `STORY_STYLE` | Default style profile (`cinematic` / `reels` / `reel_v2`) |
| `PLANNING_MODEL` | Default for story developer, scene paper, and `plan.json` authors |
| `STORY_DEVELOPER_MODEL` | Optional override for story developer only |
| `STORY_PLAN_MODEL` | Optional override for `plan.json` author only |
| `SECONDARY_MODEL` | Char-sheet / shot-image prompt authors |
| `VISION_MODEL` | Vision motion prompting model |
| `CROP_ANALYSIS_MODEL` | Optional storyboard panel bbox JSON when `STORYBOARD_CROP_MODE=vision` |
| `STORYBOARD_CROP_MODE` | `python` (default: white-gutter → grid) \| `vision` \| `auto` |
| `SEQUENTIAL_SHOT_PROMPTS` | Opt into sequential within-scene shot prompting |
| `PROVIDER` | Default still-image backend for locs/panel primary (`replicate`; legacy `fal` optional) |
| `STORYBOARD_IMAGE_PROVIDER` | Storyboard album sheets (`fal` default; `replicate` optional) |
| `CHARACTER_SHEET_IMAGE_PROVIDER` | Character sheets (`fal` when `FAL_KEY` set) |
| `PANEL_IMAGE_PROVIDER` | Panel regen primary override (defaults to `PROVIDER`) |
| `PANEL_IMAGE_FALLBACK_PROVIDER` | After primary panel fail: off by default; set `fal` to opt in |
| `FAL_KEY` | Required for fal storyboard + character sheets |
| `REPLICATE_API_TOKEN` | Required for `PROVIDER=replicate` |
| `GROK_REPLICATE_MODEL` | Replicate image model (`openai/gpt-image-2`) |
| `GROK_FAL_MODEL` | Optional fal model override (GPT Image 2) |
| `REPLICATE_SHEET_QUALITY` | Quality for character + storyboard sheets (`medium`) |
| `REPLICATE_PANEL_QUALITY` | Quality for panel regen / shot stills (`low`) |
| `CHARACTER_SHEET_SIZE` | Char sheet `aspect_ratio` pixel enum (`1152x2048`) |
| `STORYBOARD_SHEET_SIZE` | Storyboard sheet size 8:9 album (`1024x1152`) |
| `PANEL_IMAGE_SIZE` | Panel regen / shot still size (`2048x1152`) |
| `BACKGROUND_IMAGE_SIZE` | Background plate size when used (`2048x1152`) |
| `IMAGE_REF_LIMIT` | Optional override for reference image cap |
| `COMFYUI_URL` | LTX I2V render endpoint |

---

## Common commands

### Cinematic short

```bash
cd skills/story-maker

python3 main.py \
  --story-file ../../stories/story-naila/Story.md \
  --name story-naila-film \
  --style cinematic \
  --target-duration 90s \
  --fresh
```

### Fast reel

```bash
cd skills/story-maker

python3 main.py \
  --story-file ../../stories/story-naila/Story.md \
  --name story-naila-reel \
  --style reels \
  --target-duration 30s \
  --fresh
```

### reel_v2 storyboard pipeline

1. Generate character sheets, then **location lock** plates under `locations/` (empty-stage establishing images from `plan.locations`).
2. Plan storyboard sheets in story order; each sheet after the first sets `continuity_from_sheet_id` to the previous sheet.
3. Generate sheets **sequentially** via **fal GPT Image 2 edit** (default `STORYBOARD_IMAGE_PROVIDER=fal`) with refs: location lock → previous sheet → character sheets. **No T2I fallback** — failed sheets are marked `failed` and the run continues.
4. Python gutter crop (or vision) → panel regen at full resolution with **crop + character refs only** (no location plate on regen). Primary: **Replicate only** by default (same `2048x1152` / `low`). Fal panel fallback is opt-in via `PANEL_IMAGE_FALLBACK_PROVIDER=fal`.
5. Motion / I2V as usual.

`reel_v2` still does **not** write cinematic `backgrounds/` plates (`assets.generate_background: false`).

```bash
cd skills/story-maker

python3 main.py \
  --story-file ../../stories/story-naila/Story.md \
  --name story-naila-reel-v2 \
  --style reel_v2 \
  --target-duration 30s \
  --image-provider replicate \
  --stop-before-generation \
  --fresh
```

Recommended for `reel_v2`: `PROVIDER=replicate`, `STORYBOARD_IMAGE_PROVIDER=fal`, character sheets on fal (`FAL_KEY` set), `GROK_REPLICATE_MODEL=openai/gpt-image-2`, sheet quality `medium` @ storyboard `1024x1152` (8:9 album → ~16:9 panels) / character `1152x2048`, panel regen quality `low` @ `2048x1152` on Replicate (no fal panel fallback).

### Fast reel with stronger continuity

```bash
cd skills/story-maker

python3 main.py \
  --story-file ../../stories/story-naila/Story.md \
  --name story-naila-reel-seq \
  --style reels \
  --target-duration 30s \
  --sequential-shots \
  --fresh
```

### Images + motion prompts only

```bash
cd skills/story-maker

python3 main.py \
  --story-file ../../stories/story-naila/Story.md \
  --name story-naila-preview \
  --style reels \
  --target-duration 30s \
  --stop-before-generation \
  --fresh
```

### Resume an existing run

```bash
cd skills/story-maker

python3 main.py \
  --story-file ../../stories/story-naila/Story.md \
  --name story-naila-reel
```

### Re-run only specific scenes

```bash
cd skills/story-maker

python3 main.py \
  --story-file ../../stories/story-naila/Story.md \
  --name story-naila-reel \
  --only-scenes scene_02,scene_03
```

---

## Output layout

```text
outputs/story-maker/<name>/
├── developed_story.md
├── scene_paper.md
├── plan.json
├── generation_specs.json
├── cost_estimate.json   # with --plan-only
├── backgrounds/         # cinematic / reels (not reel_v2)
├── characters/
├── locations/           # reel_v2 location locks
├── storyboard_sheets/   # reel_v2 (sequential continuity)
├── panel_crops/         # reel_v2
├── images/
├── videos/
└── final_film.mp4
```

Useful files:

- `developed_story.md` — I2V-aware expanded/rewritten story (skip with `--skip-story-developer`)
- `scene_paper.md` — visual production paper
- `plan.json` — production pack (shots, audio, assets, `locations[]`, video_shots)
- `generation_specs.json` — runtime still/motion status
- `locations/` — empty-stage establishing locks keyed by `location_id` (reel_v2)
- `storyboard_sheets/` — multi-panel boards; sheet N+1 refs sheet N for continuity
- `images/` — generated starting frames / regen panels
- `videos/` — per-shot LTX clips
- `final_film.mp4` — final concatenated output

---

## Spatial continuity model

Latest `story-maker` runs can use these story-plan fields for better shot geography:

- `staging` — scene geography described left-to-right
- `blocking` — where each named character stands/faces
- `subject_position`
- `facing_direction`
- `eyeline`
- `background_region`

These are what keep:

- shot-reverse-shot dialogue coherent
- solo reaction shots feeling like the partner is still just off-camera
- reverse angles from reusing the identical backdrop

---

## Tips

- **Start with `reels` for short-form** — it is purpose-built for fast pacing and denser shot counts.
- **Use sequential shots selectively** — best for final-quality continuity, not every draft.
- **Use `--stop-before-generation` first** when testing a new story or prompt style.
- **Give stable output names** — easier resume and comparison.
- **Rerun only broken scenes** instead of restarting whole stories.
- **Keep storyboard on fal + panel primary on Replicate** — fal fallback recovers E005/policy misses without bare T2I.
- **Read `plan.json` and `generation_specs.json`** when diagnosing odd framing or continuity (check `fallback_mode` / `image_provider` on shots).

---

## If something goes wrong

If shots feel visually repetitive:

> Re-run story-maker with `--style reels` or enable `--sequential-shots` for stronger shot-to-shot continuity.

If dialogue reverses feel spatially wrong:

> Inspect `plan.json` for `staging`, `blocking`, `subject_position`, `facing_direction`, and `background_region`.

If still generation is too slow or too expensive:

> Turn off sequential shots and use the default parallel mode.

If image refs fail or expire:

> Resume the same run name — the pipeline already repairs references on resume.
