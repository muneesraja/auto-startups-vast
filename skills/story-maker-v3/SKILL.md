---
name: story-maker-v3
version: 1.0.0
description: "Story-to-video skill where Claude Code is the brain (authors all markdown/JSON, runs deterministic validators, does the vision step) and Python is the hands (image gen, crop, upscale, LTX Director render, concat). No ADK, no LiteLLM. Continuity via LTX Director FLF2V chains: each 2×4 storyboard row = one Director session."
triggers:
  - story-maker-v3
  - story-maker v3
---

# Story Maker V3 — Claude-as-brain, Python-as-hands

Turns a high-level story into an animated film. **You (Claude Code) are the brain**:
you follow this runbook, author every markdown/JSON artifact, run the deterministic
validators after each, Read the rendered panel images for the vision step, and
self-correct on validator failure (write → validate → fix loop). **Python is the
hands**: deterministic media execution (image gen, crop, upscale, LTX Director
render, concat) invoked via Bash. **Python makes zero LLM calls.** There is no ADK
and no LiteLLM here — the model authoring every artifact is you.

The root cause this fixes vs the old `story-maker` (v2.3): a vision "assistant
director" was given freedom to choose I2V-vs-FLF2V, durations, motion_class, and
beats from one glance at a sheet — that freedom is where hallucination entered. V3
removes the freedom: motion is driven by **Agent 3's numeric depth plan** (depth 1-5
→ depth-delta → camera motion), and I2V-vs-FLF2V is a **code rule**, not a choice.

## Architecture (brain / hands split)

| Layer | Owner | What it does |
|-------|-------|--------------|
| Authoring (Agents 1-5) + validation loop | **Claude Code** (this runbook) | Writes `developed_story.md`, `scenes.md`, `storyboard_*.md`, image prompts, `motion_*.json`; Reads panel images for the vision step; runs `scripts/validate.py` after each and fixes on failure |
| Image media (char sheets, location locks, storyboard sheets, crop, upscale) | **Python via Bash** | `scripts/build_images.py` → `replicate`/`fal_client` + PIL crop |
| LTX video render + concat | **Python background batch** | `scripts/render_all.py` → LTX Director per row, FLF2V chains, concat. Hours — fire-and-forget |

Locked grid: **1 scene = 1 storyboard sheet = 4 rows × 2 cols = 8 panels = 2 LTX
sessions** (~60-80s; 5min → ~5 scenes). Each LTX session is a 2×2 sub-block inside
the 4×2 sheet. Clip 9-15s default 10 (20 max for a genuine `beats[]` arc). Adjacent
panels in a session share a boundary frame; a new session block is a cut.

## Prerequisites

- Credentials in the repo-root `.env`: `FAL_KEY` and/or `REPLICATE_API_TOKEN`,
  `COMFYUI_URL` (and `COMFYUI_AUTH` if your ComfyUI is gated).
- A running ComfyUI with the LTX 2.3 Director Hotfix models installed (repo-root
  `workflows/setup/ltx-23-director-hotfix.sh`). The Hotfix workflow JSON lives at
  repo root `workflows/comfyui/LTX_Director_2_Workflow_Hotfix.json` — it is
  referenced, not copied.
- `ffmpeg` for final concat.
- Python deps: `pip install -r skills/story-maker-v3/requirements.txt`
  (replicate, fal-client, httpx, Pillow, numpy, python-dotenv; **no** google-adk,
  **no** litellm).

Provider defaults (override in `.env`): storyboard sheets + character sheets +
location locks all use **replicate** (`PROVIDER=replicate`,
`STORYBOARD_IMAGE_PROVIDER=replicate`, `CHARACTER_SHEET_IMAGE_PROVIDER=replicate`).
Storyboard sheets are 2160×3840 portrait, character sheets are 2048×1152, location
locks are 3840×2160.

## Durable artifacts + resume waterfall

Output layout: `outputs/story-maker-v3/<story>/epi-N/`; per-story shared assets at
`<story>/assets/` (`characters/{cid}.png`, `locations/{lid}.png` — never wiped).
Before each step,
**check which artifacts already exist and continue from the first missing one.** Do
not re-author or re-generate anything that is already on disk and passes its
validator.

```
1. developed_story.md            (Claude)        — Agent 1
2. scenes.md                     (Claude)        — Agent 2  → validate --schema scenes
3. storyboard_<scene>.md         (Claude, per scene) — Agent 3  → validate --schema storyboard
4. image_prompts/...             (Claude, per scene) — Agent 4  → validate --schema prompts
5. assets/characters/*.png          (Python T2I, once)          — build_images.py --assets-only
   assets/locations/*.png           (Python T2I, once)
6. storyboard_sheet_<scene>.png   (Python, per scene)         — build_images.py --scene <id>
7. panels/<scene>/panel_<r><c>.png   (Python crop)
   panels/<scene>/upscale_<r><c>.png (Python upscale)
8. motion_<scene>.json           (Claude vision, per scene) — Agent 5  → validate --schema motion
9. clips/<scene>/row<r>_clip<k>.mp4  (Python LTX)            — render_all.py
10. scene_<scene>.mp4             (Python concat)
11. final_film.mp4                (Python concat)
```

Each validator writes `<artifact>.validation.json` (`{ok, errors, warnings}`) and
exits nonzero on failure. A failed validator **blocks the paid downstream step** —
fix the artifact and re-run until `ok:true`.

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
[`prompts/storyboard_planner.md`](prompts/storyboard_planner.md): exactly 2 rows ×
4 cols = 8 cells, all 13 fields, numeric `depth_per_char` 1-5, `position_xy` in
[0,1], `duration_seconds` in [9,15] (16-20 only for a flagged beats arc), both
delta tables, and the scene-end handoff block. The 8 cell durations **must sum to
the scene's `target_seconds`**. Then:

```bash
python3 scripts/validate.py "$RUN/storyboard_sN.md" --schema storyboard \
  --scenes-path "$RUN/scenes.md"
```

Fix until `ok:true` for every scene. This is the load-bearing plan — Agent 5 derives
all camera motion from the depth deltas here.

### A4. Author image prompts (Agent 4)

For each scene, author prompt text files per [`prompts/image_prompter.md`](prompts/image_prompter.md)
into `$RUN/image_prompts/`:

- `characters/<cid>.txt` for each `cid` in the scene's `cast` (skip if it exists —
  character sheets are shared across scenes),
- `locations/<lid>.txt` for each distinct `location_id` (skip if it exists),
- `<scene>/storyboard_sheet.txt` (the 2×4 album sheet prompt, per
  [`prompts/storyboard_sheet_template.md`](prompts/storyboard_sheet_template.md)),
- `<scene>/panel_<r><c>.txt` for r,c in {1,2}×{1,2,3,4} (8 panel upscale prompts).

Cast-lock: only reference `char_NN` ids that are in the panel's
`characters_present`. Then:

```bash
python3 scripts/validate.py "$RUN/image_prompts/sN/storyboard_sheet.txt" \
  --schema prompts --run-dir "$RUN" --scene sN
```

Fix until `ok:true` (it checks all char/location/sheet/panel prompt files exist and
that no panel prompt names a `char_NN` outside the scene cast).

**Stage A checkpoint:** every artifact + `.validation.json` present and passing; no
image dollars spent yet. This is the `--plan-only` equivalent.

## Stage B — Image media (Python via Bash)

### B1. Build shared assets (once)

```bash
python3 scripts/build_images.py --output-dir "$RUN" --assets-only
```

Generates `assets/characters/<cid>.png` + `assets/locations/<lid>.png` for every
character/location referenced across all scenes. Existing files are skipped (resume-
safe). Visually confirm character identity plates look right before continuing —
they retexture every panel.

### B2. Build each scene's sheet + panels

For each scene `sN`:

```bash
python3 scripts/build_images.py --output-dir "$RUN" --scene sN
```

This generates `storyboard_sheet_sN.png` (4×2, 2160×3840, Replicate edit with
location→prev sheet→char refs), crops it into 8 `panels/sN/panel_<r><c>.png`, and
upscales each to `panels/sN/upscale_<r><c>.png` (edit: crop as Image 1 + char refs).
Existing sheets/crops/upscales are skipped. **Visually confirm character consistency
across the 8 panels** before Stage C — if a panel drifted, re-author its prompt and
re-run `--scene sN` (delete the bad crop/upscale first so it regenerates).

**Stage B checkpoint:** `assets/characters/` + `assets/locations/` populated; per
scene one 2×4 sheet, 8 crops, 8 upscales; character identity consistent across
panels. This is the `--stop-before-generation` equivalent.

## Stage C — Vision motion (Claude authors; validate + fix each)

### C1. Author each scene's motion timeline (Agent 5)

For each scene `sN`: **Read** the 8 upscaled panels
(`$RUN/panels/sN/upscale_panel_<r><c>.png`) to see what was actually drawn, plus
`storyboard_sN.md` and [`assets/ltx-2.3-director-bible.md`](assets/ltx-2.3-director-bible.md).
Author `$RUN/motion_sN.json` per [`prompts/motion_prompter.md`](prompts/motion_prompter.md):
one `render_unit` per panel (`unit_id` `sN_rR_cC`), `motion_class` + `guidance` enums
only, `guide_frames` with shared boundary panels within each row (FLF2V chain),
`motion_segments` ratio-timed, and `motion_prompt` flat fallback. **Never set
`workflow`** — I2V-vs-FLF2V is a code rule. Unit durations must sum to the scene's
`target_seconds`. Then:

```bash
python3 scripts/validate.py "$RUN/motion_sN.json" --schema motion
```

Fix until `ok:true` (it checks enums, guide_frames, motion_segments ratios, the
within-row FLF2V chain, no `workflow` key, and the duration sum).

## Stage D — Render (background Python, hours; fire-and-forget)

### D1. Render all scenes + concat

```bash
# one scene first (smoke), then all:
python3 scripts/render_all.py --output-dir "$RUN" --only-scenes sN
# then the full film:
python3 scripts/render_all.py --output-dir "$RUN"
```

This renders every `render_unit` via the LTX Director Hotfix workflow (one start
guide → I2V; start+end guides → FLF2V with last-frame strength ≥ 0.85), concatenates
row clips → `scene_<scene>.mp4`, and scenes → `final_film.mp4`. Existing clip files
are skipped (resume-safe). Launch in the background; the user returns later. Override
resolution with `--width/--height` (must be divisible by 32; Director default
`1280x704`) and `--seed`.

**Verify:** `scene_sN.mp4` plays and continuity at the shared boundary frames is
seamless. `final_film.mp4` ≈ `TARGET` (±15%); scene handoffs are clean cuts.

## Resume rules

- Before any step, check which artifacts exist on disk and continue from the first
  missing one. The build/render scripts already skip existing files; for authoring
  steps, do not overwrite a passing artifact.
- To force a regen, delete the target file (and its `.validation.json`) and re-run
  the step.
- Resume test: delete one `clips/.../row1_clip2.mp4`, re-run `render_all.py` — only
  that clip + `scene_*.mp4` + `final_film.mp4` re-execute.

## Pitfalls

1. **Never print credentials.** Do not echo `COMFYUI_AUTH`, `FAL_KEY`,
   `REPLICATE_API_TOKEN`, or slices of them. Probe ComfyUI reachability without
   printing the auth value.
2. **Storyboard sheets must use fal.** The 32:9 (`2560x720`) sheet has no Replicate
   gpt-image-2 enum. Keep `STORYBOARD_IMAGE_PROVIDER=fal` (the default).
3. **Do not set `workflow` in motion JSON.** The validator rejects it; the renderer
   derives I2V-vs-FLF2V from the guide-frame count.
4. **Within-row boundary panels must chain.** `end(K).panel_id == start(K+1).panel_id`
   within a row; a row break is a deliberate cut (not an error).
5. **Cell durations must sum to the scene target.** 8 cells × min 9s = 72s floor per
   scene; pick per-scene `target_seconds` ≥ 72 (the validator enforces the sum).
6. **Cast-lock every prompt.** Only name a `char_NN` visible in the panel's
   `characters_present`; naming an absent character is how LTX invents extras.
7. **Static camera for dialogue.** `motion_class: talking` → locked-off camera,
   animate faces/gestures; never move the camera on a dialogue shot.
8. **No "Smooth cinematic motion".** It causes Ken-Burns freeze; use the pace-aware
   closing line from the bible.
9. **ComfyUI must be running** for Stage D. If `curl $COMFYUI_URL/system_stats` is
   unreachable, Stage D is an operator step — surface it, do not hang.
10. **BrokenPipeError on ComfyUI:** never `pkill` ComfyUI while a job is executing;
    check `/queue` is empty before restarting, and redirect stdout/stderr to a log.

## Reference docs (read while authoring each artifact)

- [`prompts/story_developer.md`](prompts/story_developer.md) — Agent 1
- [`prompts/scene_writer.md`](prompts/scene_writer.md) — Agent 2
- [`prompts/storyboard_planner.md`](prompts/storyboard_planner.md) — Agent 3 (the constrained 2×4 schema)
- [`prompts/image_prompter.md`](prompts/image_prompter.md) — Agent 4
- [`prompts/motion_prompter.md`](prompts/motion_prompter.md) — Agent 5 (Director timeline, depth→camera)
- [`prompts/storyboard_sheet_template.md`](prompts/storyboard_sheet_template.md) — 2×4 sheet spec
- [`prompts/character_sheet_template.md`](prompts/character_sheet_template.md),
  [`prompts/location_sheet_template.md`](prompts/location_sheet_template.md)
- [`assets/ltx-2.3-director-bible.md`](assets/ltx-2.3-director-bible.md) — the LTX contract Agent 5 implements