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
| **Provider** (`fal` or `replicate`) | Controls still-image backend |
| **Only scenes** (`scene_02`) | Lets the agent rerun a subset |

You do **not** need to remember every CLI flag. Plain English is enough.

---

## What the agent does (behind the scenes)

1. Expands your story into a narrative outline with scene budgets
2. Directs a `story_plan.json` with shot timing, pacing, and staging
3. Plans audio and scene background assets
4. Generates character sheets and shot still prompts
5. Creates still images for each shot
6. Uses a vision model to write motion prompts from the actual starting frames
7. Renders LTX image-to-video clips
8. Concatenates them into `final_film.mp4`

If sequential shots are enabled, the agent also re-authors each shot still prompt after seeing the previous generated frame within the same scene.

---

## Style profiles

| Style | Best for | Default target | Shot rhythm |
|------|----------|----------------|-------------|
| `cinematic` | Short films, scene-first storytelling, slower breathing shots | `120s` | Fewer longer shots |
| `reels` | Short-form content, rapid hooks, energetic pacing | `30s` | Many 1–4s shots |
| `reel_v2` | Storyboard-sheet consistency: multi-panel sheets → crop → regen | `30s` | Many 1–4s shots |

`reel_v2` does **not** use background plates or per-shot parallel still prompting. It generates per-scene 10-panel storyboard sheets, uses vision to detect panel boxes, crops them, then regenerates each panel at full resolution with character references.

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
FAL_KEY=...
COMFYUI_URL=http://localhost:8188

STORY_STYLE=cinematic
# STORY_STYLE=reels
# STORY_STYLE=reel_v2

PLANNING_MODEL=openai/gpt-5.4-mini
PLANNING_REASONING_EFFORT=low
SECONDARY_MODEL=z-ai/glm-5.2
VISION_MODEL=openai/gpt-5-mini
# CROP_ANALYSIS_MODEL=openai/gpt-5.4-mini

PROVIDER=fal
# PROVIDER=replicate
# REPLICATE_API_TOKEN=...

BACKGROUND_IMAGE_SIZE=2048x1024
# SEQUENTIAL_SHOT_PROMPTS=1
```

Important env vars:

| Env var | Meaning |
|---------|---------|
| `STORY_STYLE` | Default style profile (`cinematic` / `reels` / `reel_v2`) |
| `CROP_ANALYSIS_MODEL` | Vision model for storyboard panel bbox JSON (`reel_v2`) |
| `SEQUENTIAL_SHOT_PROMPTS` | Opt into sequential within-scene shot prompting |
| `PLANNING_MODEL` | Narrative expander + shot director model |
| `SECONDARY_MODEL` | Audio / scene assets / char sheets / shot image planning |
| `VISION_MODEL` | Vision motion prompting model |
| `PROVIDER` | Grok image backend: `fal` or `replicate` |
| `REPLICATE_API_TOKEN` | Required when `PROVIDER=replicate` |
| `BACKGROUND_IMAGE_SIZE` | Panoramic scene background size |
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

Recommended for `reel_v2`: `PROVIDER=replicate`, `GROK_REPLICATE_MODEL=openai/gpt-image-2`, `REPLICATE_IMAGE_QUALITY=low`.

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
├── narrative_outline.json
├── story_plan.json
├── audio_plan.json
├── scene_assets.json
├── generation_specs.json
├── backgrounds/
├── characters/
├── storyboard_sheets/   # reel_v2
├── panel_crops/         # reel_v2
├── images/
├── videos/
└── final_film.mp4
```

Useful files:

- `story_plan.json` — shot plan, pacing, staging, blocking
- `generation_specs.json` — still prompt specs + motion status
- `images/` — generated starting frames
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
- **Replicate can handle more refs** than fal, which helps multi-character shots.
- **Read `story_plan.json` and `generation_specs.json`** when diagnosing odd framing or continuity.

---

## If something goes wrong

If shots feel visually repetitive:

> Re-run story-maker with `--style reels` or enable `--sequential-shots` for stronger shot-to-shot continuity.

If dialogue reverses feel spatially wrong:

> Inspect `story_plan.json` for `staging`, `blocking`, `subject_position`, `facing_direction`, and `background_region`.

If still generation is too slow or too expensive:

> Turn off sequential shots and use the default parallel mode.

If image refs fail or expire:

> Resume the same run name — the pipeline already repairs references on resume.
