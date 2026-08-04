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
Storyboard sheets are **2160×3840 (4K portrait)** at `quality=medium`,
character sheets are 2048×1152, location locks are 3840×2160.

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
4. image_prompts/characters/ + locations/ + <scene>/storyboard_sheet.txt  (Claude, per scene) — Agent 4  → validate --schema prompts
5. assets/characters/*.png          (Python T2I, once)          — build_images.py --assets-only
   assets/locations/*.png           (Python T2I, once)
6. storyboard_sheet_<scene>.png   (Python, per scene)         — build_images.py --sheet-only --scene <id>
   ═══ GATE 1: user visually confirms all sheets before continuing ═══
7. panels/<scene>/panel_<r><c>.png   (Python crop)            — build_images.py --crop-only --scene <id>
   image_prompts/<scene>/panel_<r><c>.txt  (Claude post-crop, per scene) — Agent 4  → validate --schema panel_prompts
8. panels/<scene>/upscale_<r><c>.png (Python outpaint)         — build_images.py --upscale-only --scene <id>
   ═══ GATE 2: user visually confirms all upscales before continuing ═══
9. director_sets_<scene>.json    (Claude, per scene) — Agent 3b → validate --schema director_sets
10. motion_<scene>.json           (Claude vision, per scene) — Agent 5  → validate --schema motion
11. clips/<scene>/row<r>_clip<k>.mp4  (Python LTX)            — render_all.py
12. scene_<scene>.mp4             (Python concat)
13. final_film.mp4                (Python concat)
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
Stage B1: Generate all storyboard sheets for all scenes (--sheet-only)
  ═══ GATE 1 ═══
  STOP. Ask the user to visually confirm all storyboard sheets.
  Do NOT proceed to crops until the user says go.
Stage B2: Crop all panels for all scenes (--crop-only)
  Author panel outpaint prompts (post-crop, edge-continuation only)
  Validate panel prompts (--schema panel_prompts)
Stage B3: Outpaint all panels for all scenes (--upscale-only)
  ═══ GATE 2 ═══
  STOP. Ask the user to visually confirm all upscaled panels.
  Do NOT proceed to motion/video until the user says go.
Stage C0: Author director_sets for all scenes
Stage C1: Author motion timelines for all scenes
Stage D: Render video
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

### A4. Author pre-generation image prompts (Agent 4)

For each scene, author prompt text files per [`prompts/image_prompter.md`](prompts/image_prompter.md)
into `$RUN/image_prompts/`:

- `characters/<cid>.txt` for each `cid` in the scene's `cast` (skip if it exists —
  character sheets are shared across scenes),
- `locations/<lid>.txt` for each distinct `location_id` (skip if it exists),
- `<scene>/storyboard_sheet.txt` (the 2×4 album sheet prompt, per
  [`prompts/storyboard_sheet_template.md`](prompts/storyboard_sheet_template.md)).

**Panel outpaint prompts are authored post-crop** (after GATE 1) — see Stage B2.

Cast-lock: only reference `char_NN` ids that are in the scene's cast. Then:

```bash
python3 scripts/validate.py "$RUN/image_prompts/sN/storyboard_sheet.txt" \
  --schema prompts --run-dir "$RUN" --scene sN
```

Fix until `ok:true` (it checks char/location/sheet prompt files exist and are
non-empty).

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
they retexture every panel.

### B2. Generate storyboard sheets (per scene)

For each scene `sN`:

```bash
python3 scripts/build_images.py --output-dir "$RUN" --sheet-only --scene sN
```

This generates `storyboard_sheet_sN.png` (4×2, 2160×3840, Replicate edit with
location→prev sheet→char refs). Existing sheets are skipped.

**═══ GATE 1 ═══**

STOP after all sheets are generated. Ask the user to visually confirm every
storyboard sheet. Do NOT proceed to crops until the user explicitly says go.
If a sheet is wrong, delete it and re-run `--sheet-only`.

### B3. Crop panels + author panel prompts + outpaint (per scene)

**Crop** (free PIL, no API cost):

```bash
python3 scripts/build_images.py --output-dir "$RUN" --crop-only --scene sN
```

This crops the sheet into 8 `panels/sN/panel_<r><c>.png`.

**Author panel outpaint prompts** (Agent 4, post-crop): Read each crop PNG to see
what was actually drawn, then author `$RUN/image_prompts/sN/panel_<r><c>.txt` per
[`prompts/image_prompter.md`](prompts/image_prompter.md) — edge-continuation only,
no `char_NN` tokens, no negative-cast phrasing. Then:

```bash
python3 scripts/validate.py "$RUN/image_prompts/sN/panel_11.txt" \
  --schema panel_prompts --run-dir "$RUN" --scene sN
```

Fix until `ok:true`.

**Outpaint** (pre-pad + model repaints side bars only):

```bash
python3 scripts/build_images.py --output-dir "$RUN" --upscale-only --scene sN
```

This pre-pads each crop to 2048×1152 with mirrored/blurred side bars
(`panel_outpaint.py`), then asks the model to repaint only the side bars. A
`center_region_drift` guard compares the locked inner box and rejects outputs that
drift. Existing upscales are skipped.

**═══ GATE 2 ═══**

STOP after all upscales are generated. Ask the user to visually confirm every
upscaled panel — check that characters are preserved and side bars blend
seamlessly. Do NOT proceed to motion/video until the user explicitly says go.
If a panel drifted, delete its `upscale_*.png` and `prepad_*.png`, re-author its
prompt, and re-run `--upscale-only`.

## Stage C — Timing + Vision motion (Claude authors; validate + fix each)

### C0. Author director sets (Agent 3b)

For each scene `sN`, author `$RUN/director_sets_sN.json` per
[`prompts/director_set_planner.md`](prompts/director_set_planner.md): 2 sets of 4
panels each, with a fixed 8-beat sequence (pre_roll → panel_hold → gap → ... →
panel_hold). Beat durations are the **sole authority** for scene timing. Then:

```bash
python3 scripts/validate.py "$RUN/director_sets_sN.json" \
  --schema director_sets --scenes-path "$RUN/scenes.md"
```

Fix until `ok:true` (it checks beat sequence, duration ranges, gap transitions,
set totals ≤ 20s, and sum of set durations = scene target_seconds).

### C1. Author each scene's motion timeline (Agent 5)

For each scene `sN`: **Read** the 8 upscaled panels
(`$RUN/panels/sN/upscale_panel_<r><c>.png`) to see what was actually drawn, plus
`director_sets_sN.json` (the authoritative timing plan), `storyboard_sN.md`, and
[`assets/ltx-2.3-director-bible.md`](assets/ltx-2.3-director-bible.md).
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
2. **Storyboard sheets use Replicate gpt-image-2 at medium quality, 4K portrait.**
   The sheet is `2160x3840` (4K portrait) with `quality=medium`. Keep
   `STORYBOARD_IMAGE_PROVIDER=replicate` (the default) and
   `REPLICATE_SHEET_QUALITY=medium`. Do NOT switch to fal or lower the resolution.
3. **Do not set `workflow` in motion JSON.** The validator rejects it; the renderer
   derives I2V-vs-FLF2V from the guide-frame count.
4. **Within-row boundary panels must chain.** `end(K).panel_id == start(K+1).panel_id`
   within a row; a row break is a deliberate cut (not an error).
5. **Cell durations are estimates only.** The authoritative timing comes from
   `director_sets_sN.json` (Stage C0). The storyboard sum must still match
   `target_seconds` as a sanity check.
6. **Panel outpaint prompts must NOT name characters.** The `panel_prompts` validator
   rejects any `char_NN` token. The crop already has the characters — the outpaint
   model must only extend side bars.
7. **Panel outpaint prompts must NOT use negative-cast phrasing.** "No humans",
   "no dog", etc. cause the model to delete subjects. The validator rejects these.
8. **The pre-padded canvas is the ONLY reference image for outpaint.** Character
   sheets and location locks are deliberately dropped — they were the primary source
   of reimagination pressure that caused character deletion in epi-4.
9. **Gates are mandatory.** GATE 1 (after sheets) and GATE 2 (after upscales) are
   runbook rules. You must stop and ask the user before proceeding. Do NOT skip them.
10. **Static camera for dialogue.** `motion_class: talking` → locked-off camera,
    animate faces/gestures; never move the camera on a dialogue shot.
11. **No "Smooth cinematic motion".** It causes Ken-Burns freeze; use the pace-aware
    closing line from the bible.
12. **ComfyUI must be running** for Stage D. If `curl $COMFYUI_URL/system_stats` is
    unreachable, Stage D is an operator step — surface it, do not hang.
13. **BrokenPipeError on ComfyUI:** never `pkill` ComfyUI while a job is executing;
    check `/queue` is empty before restarting, and redirect stdout/stderr to a log.

## Reference docs (read while authoring each artifact)

- [`prompts/story_developer.md`](prompts/story_developer.md) — Agent 1
- [`prompts/scene_writer.md`](prompts/scene_writer.md) — Agent 2
- [`prompts/storyboard_planner.md`](prompts/storyboard_planner.md) — Agent 3 (the constrained 2×4 schema)
- [`prompts/director_set_planner.md`](prompts/director_set_planner.md) — Agent 3b (set timing plan, beat sequence)
- [`prompts/image_prompter.md`](prompts/image_prompter.md) — Agent 4
- [`prompts/motion_prompter.md`](prompts/motion_prompter.md) — Agent 5 (Director timeline, depth→camera)
- [`prompts/storyboard_sheet_template.md`](prompts/storyboard_sheet_template.md) — 2×4 sheet spec
- [`prompts/character_sheet_template.md`](prompts/character_sheet_template.md),
  [`prompts/location_sheet_template.md`](prompts/location_sheet_template.md)
- [`assets/ltx-2.3-director-bible.md`](assets/ltx-2.3-director-bible.md) — the LTX contract Agent 5 implements