---
name: story-maker-v3
version: 2.0.0
description: "Story-to-video skill where Claude Code is the brain (authors all markdown/text artifacts, runs deterministic validators, does the vision step) and Python is the hands (image gen, Minimax H3 render, concat). No ADK, no LiteLLM. Video backend: Minimax H3 R2V via ComfyUI — each <=15s generation renders directly from one storyboard sheet reference + a timeline prompt, with native stereo audio. No panel crops, no upscales."
triggers:
  - story-maker-v3
  - story-maker v3
---

# Story Maker V3 — Claude-as-brain, Python-as-hands (Minimax H3)

Turns a high-level story into an animated film. **You (Claude Code) are the brain**:
you follow this runbook, author every markdown/text artifact, run the deterministic
validators after each, Read the rendered storyboard sheets for the vision step, and
self-correct on validator failure (write → validate → fix loop). **Python is the
hands**: deterministic media execution (image gen, Minimax H3 render, concat)
invoked via Bash. **Python makes zero LLM calls.** There is no ADK and no LiteLLM
here — the model authoring every artifact is you.

**v2.0 (Minimax H3) replaces the LTX 2.3 Director pipeline.** Minimax H3 has far
stronger prompt adherence and visual consistency, and renders directly from a
storyboard sheet reference — so panel crops, outpaints/upscales, director sets,
and motion JSON are all gone. The one hard limitation: **a generation is at most
15 seconds**. The whole plan is therefore chunked at 15s boundaries: a shot that
cannot finish inside the current generation moves — panels and all — to the next
generation's storyboard.

## Architecture (brain / hands split)

| Layer | Owner | What it does |
|-------|-------|--------------|
| Authoring (Agents 1-5) + validation loop | **Claude Code** (this runbook) | Writes `developed_story.md`, `scenes.md`, `storyboard_*.md`, image prompts, `video_prompts/*.txt`; Reads sheet images for the vision step; runs `scripts/validate.py` after each and fixes on failure |
| Image media (char sheets, location locks, storyboard sheets) | **Python via Bash** | `scripts/build_images.py` → `replicate`/`fal_client` |
| Minimax H3 video render + concat | **Python background batch** | `scripts/render_all.py` → one ComfyUI render per generation (sheet = reference image, timeline prompt, native stereo audio), concat. Hours — fire-and-forget |

Locked chunking: **1 scene = N generations; 1 generation = 1 storyboard sheet =
1 Minimax H3 render, 5-15s**. Each sheet is a clean panel grid (`panel_grid`,
2-12 panels, NO text/timecodes on the image). A shot never straddles a
generation boundary. A ~70s scene ≈ 5 generations.

## Episode context (mandatory)

**Always load the current episode's context before authoring anything.** That
means: the user's story file, `developed_story.md`, `scenes.md`, every already-
authored `storyboard_*.md` of this episode, and — for episode 2+ — the previous
episode's final scene storyboard/handoff. Minimax prompts open with lines like
"Continue directly from the previous scene", so you must know exactly what state
(cast on screen, positions, mood, lighting) each generation continues from.
Never author a storyboard or video prompt from the scene beat alone.

## Prerequisites

- Credentials in the repo-root `.env`: `FAL_KEY` and/or `REPLICATE_API_TOKEN`,
  `COMFYUI_URL` (and `COMFYUI_AUTH` if your ComfyUI is gated).
- A running ComfyUI with the Minimax H3 models installed (Comfy-Org/MiniMax-H3:
  ref2va UNet, video + audio VAEs, qwen3vl CLIP). The workflow JSON lives at
  repo root `workflows/comfyui/Minimax H3 R2V - Final.json` — it is referenced,
  not copied (override with `MINIMAX_H3_WORKFLOW`).
- `ffmpeg` for concat.
- Python deps: `pip install -r skills/story-maker-v3/requirements.txt`
  (replicate, fal-client, httpx, Pillow, numpy, python-dotenv; **no** google-adk,
  **no** litellm).

Provider defaults (override in `.env`): storyboard sheets + character sheets +
location locks all use **replicate** (`PROVIDER=replicate`,
`STORYBOARD_IMAGE_PROVIDER=replicate`, `CHARACTER_SHEET_IMAGE_PROVIDER=replicate`).
Storyboard sheets are **3840×2160 (4K landscape)** at `quality=medium`,
character sheets are 2048×1152, location locks are 3840×2160. Minimax renders at
`MINIMAX_MEGAPIXELS=0.6`, `MINIMAX_ASPECT=16:9` (→ 1056×608) by default.

## Durable artifacts + resume waterfall

Output layout: `outputs/story-maker-v3/<story>/epi-N/`; per-story shared assets at
`<story>/assets/` (`characters/{cid}.png`, `locations/{lid}.png` — never wiped).
Before each step,
**check which artifacts already exist and continue from the first missing one.** Do
not re-author or re-generate anything that is already on disk and passes its
validator.

```
1. developed_story.md              (Claude)             — Agent 1
2. scenes.md                       (Claude)             — Agent 2  → validate --schema scenes
3. storyboard_<scene>.md           (Claude, per scene)  — Agent 3  → validate --schema storyboard
4. image_prompts/characters/ + locations/ + <scene>/storyboard_sheet_<gen>.txt
                                   (Claude, per scene)  — Agent 4  → validate --schema prompts
5. assets/characters/*.png         (Python T2I, once)   — build_images.py --assets-only
   assets/locations/*.png          (Python T2I, once)
6. storyboard_sheet_<scene>_<gen>.png  (Python, per generation) — build_images.py --scene <id>
   ═══ GATE 1: user visually confirms all sheets before continuing ═══
7. video_prompts/<scene>_<gen>.txt (Claude vision, per generation) — Agent 5 → validate --schema video_prompt
   ═══ GATE 2: user confirms the video prompts before paid GPU render ═══
8. clips/<scene>/<gen>.mp4         (Python Minimax H3)  — render_all.py
9. scene_<scene>.mp4               (Python concat, audio preserved)
10. final_film.mp4                 (Python concat)
```

Each validator writes `<artifact>.validation.json` (`{ok, errors, warnings}`) and
exits nonzero on failure. A failed validator **blocks the paid downstream step** —
fix the artifact and re-run until `ok:true`.

## Episode run order + human gates

When a user requests an episode generation from a story, follow this order with
**two mandatory human approval gates**. These are runbook rules — there is no code
enforcement. You (Claude) must stop and ask the user before proceeding.

```
Stage A: Author all storyboards for all scenes (A1-A4 per scene)
Stage B: Generate shared assets + all storyboard sheets (per generation)
  ═══ GATE 1 ═══
  STOP. Ask the user to visually confirm all storyboard sheets.
  Do NOT proceed until the user says go.
Stage C: Author Minimax video prompts for all generations (vision: Read each sheet)
  ═══ GATE 2 ═══
  STOP. Present the video prompts for review before the paid GPU render.
  Do NOT proceed to render until the user says go.
Stage D: Render video (background, hours)
```

At each gate, present the user with the file paths to review and wait for explicit
approval. If the user requests changes, fix and re-generate before proceeding.

## Stage A — Planning (Claude authors; validate + fix each; no image spend)

All commands run from `skills/story-maker-v3/`. Let `RUN=outputs/story-maker-v3/<name>`
(absolute path preferred) and `TARGET` be the target duration in seconds
(e.g. `300` for 5 min).

### A1. Develop the story (Agent 1)

Read the user's raw story file + `TARGET`. Author `$RUN/developed_story.md` per
[`prompts/story_developer.md`](prompts/story_developer.md): expand/shrink to target,
anti-sameness, videography writing, ending with `## Characters` (id/name/species/
age/appearance, stable `char_NN` ids) and `## Locations` (id/name/description/
establishing_prompt). No validator for this file.

### A2. Break into scenes (Agent 2)

Compute `scene_count = ceil(TARGET / 70)`. Author `$RUN/scenes.md` per
[`prompts/scene_writer.md`](prompts/scene_writer.md) — one `## Scene sN — <title>`
block per scene with `scene_id`, `target_seconds`, `cast`, `characters_present`,
`location_id`, `beat`. Per-scene targets must sum within 15% of `TARGET`. Then:

```bash
python3 scripts/validate.py "$RUN/scenes.md" --schema scenes --target-seconds "$TARGET"
```

Read `$RUN/scenes.md.validation.json`. If `ok:false`, fix every listed error and
re-run. **Do not proceed until it passes.**

### A3. Storyboard each scene (Agent 3)

For each scene `sN`, author `$RUN/storyboard_sN.md` per
[`prompts/storyboard_planner.md`](prompts/storyboard_planner.md): the scene split
into `## Generation gK — a-b s` blocks (each 5-15s, contiguous, summing to the
scene's `target_seconds`), each with `panel_grid` and `### Shot` blocks
(contiguous, panels in reading order, Minimax camera vocabulary, audio +
dialogue). **The 15s rule is load-bearing: a shot that does not fit in the
current generation moves whole to the next one.** Then:

```bash
python3 scripts/validate.py "$RUN/storyboard_sN.md" --schema storyboard \
  --scenes-path "$RUN/scenes.md"
```

Fix until `ok:true` for every scene.

### A4. Author pre-generation image prompts (Agent 4)

For each scene, author prompt text files per [`prompts/image_prompter.md`](prompts/image_prompter.md)
into `$RUN/image_prompts/`:

- `characters/<cid>.txt` for each `cid` in the scene's `cast` (skip if it exists —
  character sheets are shared across scenes),
- `locations/<lid>.txt` for each distinct `location_id` (skip if it exists),
- `<scene>/storyboard_sheet_<gen>.txt` — one per generation, per
  [`prompts/storyboard_sheet_template.md`](prompts/storyboard_sheet_template.md).

Cast-lock: only reference `char_NN` ids that are in the scene's cast. Then:

```bash
python3 scripts/validate.py "$RUN/image_prompts/sN/storyboard_sheet_g1.txt" \
  --schema prompts --run-dir "$RUN" --scene sN
```

Fix until `ok:true` (it checks char/location prompt files and one sheet prompt
per generation exist and are non-empty).

**Stage A checkpoint:** every artifact + `.validation.json` present and passing; no
image dollars spent yet. This is the `--plan-only` equivalent.

## Stage B — Image media (Python via Bash; gated)

### B1. Build shared assets (once)

```bash
python3 scripts/build_images.py --output-dir "$RUN" --assets-only
```

Generates `assets/characters/<cid>.png` + `assets/locations/<lid>.png` for every
character/location referenced across all scenes. Existing files are skipped (resume-
safe). Visually confirm character identity plates look right before continuing —
they retexture every sheet.

### B2. Generate storyboard sheets (per scene, one per generation)

For each scene `sN`:

```bash
python3 scripts/build_images.py --output-dir "$RUN" --scene sN
```

This generates `storyboard_sheet_sN_gK.png` for every generation (3840×2160,
Replicate edit with location → previous sheet → char refs; the previous sheet
chains g1→g2→... and across scenes for continuity). Existing sheets are skipped.

**═══ GATE 1 ═══**

STOP after all sheets are generated. Ask the user to visually confirm every
storyboard sheet — clean equal panels, zero text, consistent characters,
readable motion progression. Do NOT proceed until the user explicitly says go.
If a sheet is wrong, delete it and re-run `--scene sN`.

## Stage C — Vision + video prompts (Claude authors; validate + fix each)

### C1. Author each generation's Minimax prompt (Agent 5)

For each scene `sN` and generation `gK`: **Read** the sheet
(`$RUN/storyboard_sheet_sN_gK.png`) to see what was actually drawn, plus
`storyboard_sN.md`, the episode context, and
[`assets/minimax-h3-prompt-bible.md`](assets/minimax-h3-prompt-bible.md).
Author `$RUN/video_prompts/sN_gK.txt` per [`prompts/video_prompter.md`](prompts/video_prompter.md):
Reference block (use the storyboard, appearance locks — describe characters by
appearance, never `char_NN`), style block, `Timeline` with one
`SHOT n — a–b s (Continuous Shot)` block per storyboard shot in
**generation-local seconds**, `Hard cinematic cut.` between shots, dialogue and
sound direction inline, `Final frame:`, and a `Negative Prompt` block. Then:

```bash
python3 scripts/validate.py "$RUN/video_prompts/sN_gK.txt" \
  --schema video_prompt --run-dir "$RUN" --scene sN
```

Fix until `ok:true` (it checks the storyboard reference, Timeline/Negative
Prompt sections, SHOT count + time ranges against the storyboard, the 15s cap,
and rejects `char_NN` tokens).

**═══ GATE 2 ═══**

STOP after all video prompts pass. Present them to the user for review before
spending GPU hours. Do NOT render until the user explicitly says go.

## Stage D — Render (background Python, hours; fire-and-forget)

### D1. Render all scenes + concat

```bash
# one scene first (smoke), then all:
python3 scripts/render_all.py --output-dir "$RUN" --only-scenes sN
# then the full film:
python3 scripts/render_all.py --output-dir "$RUN"
```

This renders every generation via the Minimax H3 R2V workflow (sheet uploaded as
the ONLY reference image, video prompt as the timeline, duration from the
storyboard snapped to Minimax's frame grid), then concatenates generation clips →
`scene_<scene>.mp4` and scenes → `final_film.mp4`, **preserving Minimax's native
stereo audio**. Existing clip files are skipped (resume-safe). Launch in the
background; the user returns later. Override size with `--megapixels/--aspect`
(default 0.6MP 16:9 → 1056×608) and `--seed`.

**Verify:** `scene_sN.mp4` plays with audio and generation handoffs read as
intentional cuts/continuations. `final_film.mp4` ≈ `TARGET` (±15%).

## Resume rules

- Before any step, check which artifacts exist on disk and continue from the first
  missing one. The build/render scripts already skip existing files; for authoring
  steps, do not overwrite a passing artifact.
- To force a regen, delete the target file (and its `.validation.json`) and re-run
  the step.
- Resume test: delete one `clips/sN/g2.mp4`, re-run `render_all.py` — only that
  clip + `scene_sN.mp4` + `final_film.mp4` re-execute.

## Pitfalls

1. **Never print credentials.** Do not echo `COMFYUI_AUTH`, `FAL_KEY`,
   `REPLICATE_API_TOKEN`, or slices of them. Probe ComfyUI reachability without
   printing the auth value.
2. **15 seconds, period.** No generation may exceed 15s and no shot may straddle
   a generation boundary — the storyboard validator enforces both. When a scene's
   pacing fights the boundary, re-cut the shots, don't stretch the generation.
3. **Storyboard sheets must be text-free.** The sheet goes to Minimax verbatim;
   painted timecodes/labels leak into the video. All timing lives in the prompt.
4. **Describe characters by appearance in video prompts.** Minimax has never seen
   your `char_NN` ids; the `video_prompt` validator rejects them. Use the locked
   appearance descriptions from `developed_story.md`.
5. **Generation-local timecodes.** `SHOT` ranges in a video prompt start at 0.0
   for every generation, even though the storyboard uses scene-relative times.
6. **Direct the audio.** Minimax generates voice/SFX/music natively. Silent
   prompts produce invented audio. Every shot should carry sound direction, and
   dialogue must be quoted inline where it happens.
7. **The sheet wins over the plan.** Agent 5 must Read the actual sheet image and
   describe what was drawn; if the sheet deviates from the storyboard, either
   regenerate the sheet (before GATE 1 sign-off) or write the prompt to the sheet.
8. **Continuity across generations is authored, not automatic.** Each generation
   is an independent render: the sheet chain (previous sheet as reference) plus
   "Continue directly from the previous scene" prompt lines are what carry
   continuity. Keep the episode context loaded at all times.
9. **Gates are mandatory.** GATE 1 (after sheets) and GATE 2 (after video
   prompts, before render) are runbook rules. You must stop and ask the user.
