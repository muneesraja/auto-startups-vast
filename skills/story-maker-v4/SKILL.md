---
name: story-maker-v4
version: 4.2.0
description: "Production-ready story-to-video skill where Claude Code authors and validates artifacts while Python runs deterministic media tasks. Video backend: MiniMax H3 R2V via ComfyUI — each 5–15s generation uses a storyboard sheet, structured Ref2VA prompt, native stereo audio, and bounded optional references. No panel crops or upscales."
triggers:
  - story-maker-v4
  - story-maker v4
---

# Story Maker V4 — H3-directed scene production

Turns a high-level story into an animated film. **You (Claude Code) are the brain**:
you follow this runbook, author every markdown/text artifact, run the deterministic
validators after each, Read the rendered storyboard sheets for the vision step, and
self-correct on validator failure (write → validate → fix loop). **Python is the
hands**: deterministic media execution (image gen, Minimax H3 render, concat)
invoked via Bash. **Python makes zero LLM calls.** There is no ADK and no LiteLLM
here — the model authoring every artifact is you.

**V4 targets MiniMax H3 reference generation.** It preserves the V3 pipeline,
adds a self-contained Ref2VA contract, H3 reference budgets, and an H3 pacing
profile. H3 renders directly from a storyboard sheet; a generation is limited to
**5–15 seconds**, so a shot that cannot finish inside the current generation
moves — panels and all — to the next generation's storyboard.

## Architecture (brain / hands split)

| Layer | Owner | What it does |
|-------|-------|--------------|
| Authoring (Agents 1-5) + validation loop | **Claude Code** (this runbook) | Writes `developed_story.md`, `scenes.md`, `storyboard_*.md`, image prompts, `video_prompts/*.txt`; Reads sheet images for the vision step; runs `scripts/validate.py` after each and fixes on failure |
| Image media (char sheets, location locks, storyboard sheets) | **Python via Bash** | `scripts/build_images.py` → `replicate`/`fal_client` |
| Minimax H3 video render + concat | **Python background batch** | `scripts/render_all.py` → sequential render: each generation is conditioned on the previous generation's rendered tail (3s) via `ref_videos`, then concat. Hours — fire-and-forget |

Locked chunking: **1 scene = N generations; 1 generation = 1 storyboard sheet =
1 Minimax H3 render, 5-15s**. Each sheet is a clean panel grid (`panel_grid`,
6-12 panels, column-major numbering, NO text/timecodes on the image). Default
grid is `3x2` (3 rows × 2 columns). A shot never straddles a
generation boundary. A ~70s scene ≈ 5 generations. Continuity between adjacent
generations is handled at render time by conditioning each generation on the
previous generation's rendered tail (3s) as a `ref_video`. No bridge
generations are used.

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
  repo root `workflows/comfyui/minimax/Minimax H3 R2V - Final.json` — it is referenced,
  not copied (override with `MINIMAX_H3_WORKFLOW`).
- **Illustration styles (optional):** for 2D storybook, folk / flat-geometric,
  vintage editorial, or semi-realistic painterly concept-art looks, install the
  H3-native style LoRAs with
  `bash workflows/setup/minimax-h3-r2v-style-lora.sh` and point
  `MINIMAX_H3_WORKFLOW` at
  `workflows/comfyui/minimax/minimax-h3-r2v-style-lora.json`. Presets, trigger words and
  strengths: [`assets/style-lora-presets.md`](assets/style-lora-presets.md).
  Only H3 adapters load into H3 — Flux/SDXL/Qwen-Image LoRAs will not work.
- `ffmpeg` for concat.
- Python deps: `pip install -r skills/story-maker-v4/requirements.txt`
  (replicate, fal-client, httpx, Pillow, numpy, python-dotenv; **no** google-adk,
  **no** litellm).

Provider defaults (override in `.env`): storyboard sheets + character sheets +
location locks + object sheets all use **replicate** (`PROVIDER=replicate`,
`STORYBOARD_IMAGE_PROVIDER=replicate`, `CHARACTER_SHEET_IMAGE_PROVIDER=replicate`).
Storyboard sheets, character sheets, location locks, and object sheets are all
**3840×2160 (4K)** at `quality=medium`. Location locks use a wide-angle 360°
view prompt. All Replicate outputs use `output_format=webp` +
`output_compression=90` (override with `REPLICATE_OUTPUT_FORMAT` /
`REPLICATE_OUTPUT_COMPRESSION`) to keep 4K files small (~1-3MB vs 5-15MB for
PNG). Minimax renders at `MINIMAX_MEGAPIXELS=0.6`, `MINIMAX_ASPECT=16:9`
(→ 1056×608) by default.

**Dynamic reference images:** any prompt file (character, location, object, or
storyboard sheet) may begin with a `ref_images: name1, name2, ...` line naming
up to 10 existing assets to attach as reference images. The backend resolves
names via the shared registry (objects → locations → characters → sheets) and
passes them to the image generation call. Use this to carry visual continuity
across episodes — e.g. attach the existing "kitchen" location when generating a
new "hall" location.

## Durable artifacts + resume waterfall

Output layout: `outputs/story-maker-v4/<story>/epi-N/`; per-story shared assets at
`<story>/assets/` (`characters/{cid}.png`, `locations/{lid}.png`,
`objects/{oid}.png` — never wiped). The shared asset registry lives at
`<story>/assets/asset_registry.json` — it tracks hosted URLs for all assets
across all episodes. A new episode reads the existing registry and only creates
new characters/locations/objects; existing assets are skipped.
Before each step,
**check which artifacts already exist and continue from the first missing one.** Do
not re-author or re-generate anything```
1. developed_story.md + story.json     (Claude)             — Agent 1 / Intake Normalizer
   (screenplay format per assets/screenplay-format.md; validate --schema screenplay)
   (supports intake_mode: preserve_script | develop_from_concept; canonical constraints)
1b. beat_board.md                      (Claude)             — Agent 1b → validate --schema beat_board
   (8-15 dramatic beats with emotion + estimated timing)
2. scenes.md                           (Claude)             — Agent 2  → validate --schema scenes
   (each scene has objects: [oid, ...] and beats: [n, ...] referencing the beat board)
   (optional: validate --schema constraints --scenes-path scenes.md)
3. spatial_plan_<scene>.md             (Claude, per scene)  — Agent 3a → validate --schema spatial_plan
   (2.5D coordinate contract: landmarks, zones, per-generation/per-shot spatial state)
3b. storyboard_<scene>.md              (Claude, per scene)  — Agent 3  → validate --schema storyboard
4. image_prompts/characters/ + locations/ + objects/ + <scene>/storyboard_sheet_<gen>.txt
                                       (Claude, per scene)  — Agent 4  → validate --schema prompts
   (reference priority, spatial continuity, action contract: visible pose, plain prose reading order)
4b. critique_report.md                 (Claude)             — Agent 6  → validate --schema critique
   (directing questions evaluated with severity tiers: BLOCKER, MAJOR, MINOR, NOT_APPLICABLE)
   ═══ GATE 0: critique must pass with zero BLOCKERs and all MAJORs disposed before image generation ═══
5. assets/characters/*.png             (Python T2I, once, 4K) — build_images.py --assets-only
   assets/locations/*.png              (Python T2I, once, 4K wide-angle 360°)
   assets/objects/*.png                (Python T2I, once, 4K)
6. storyboard_sheet_<scene>_<gen>.png  (Python, per generation) — build_images.py --scene <id>
   ═══ GATE 1: user visually confirms all sheets + spatial_qa_report.md before continuing ═══
6b. spatial_qa_report.md               (Claude, per scene)  — Agent 7  → validate --schema spatial_qa
   (PASS/WARN/BLOCKER escalation policy + sha256 tracking; BLOCKER halts GATE 1)
7. video_prompts/<scene>_<gen>.txt     (Claude vision, per generation) — Agent 5 → validate --schema video_prompt
   (discrepancy authority policy; 4-layer audio: dialogue, foley, ambience, music)
7b. render_manifest.json               (Python)             — build_manifest.py --approve
   (immutable content-addressed lock: sheet_sha256, prompt_sha256, duration; staleness protection)
   ═══ GATE 2: user confirms render_manifest.json before paid GPU render ═══
8. clips/<scene>/<gen>.mp4             (Python Minimax H3)  — render_all.py --manifest render_manifest.json
   (each generation conditioned on previous generation's rendered tail via ref_videos; staleness checked)
9. scene_<scene>.mp4                   (Python concat, audio preserved)
10. final_film.mp4                     (Python concat)

Each validator writes `<artifact>.validation.json` (`{ok, errors, warnings}`) and
exits nonzero on failure. A failed validator **blocks the paid downstream step** —
fix the artifact and re-run until `ok:true`.

## Episode run order + human gates

When a user requests an episode generation from a story, follow this order with
**three human approval gates**. These are runbook rules — there is no code
enforcement. You (Claude) must stop and ask the user before proceeding.

```
Stage A: Author all storyboards for all scenes (A1-A4 per scene) + story.json
Stage A-QA: Critique agent evaluates the full plan against directing questions (with Severity Tiers)
  ═══ GATE 0 ═══
  STOP. The critique report must have zero BLOCKERs and all MAJORs disposed before any image generation.
  Fix flagged artifacts or confirm director disposition until all questions pass.
Stage B: Generate assets + storyboard sheets (Python T2I, once per story + per scene)
Stage B-QA: Spatial QA inspects sheets against spatial plans (Agent 7, PASS/WARN/BLOCKER)
  ═══ GATE 1 ═══
  STOP. User visually confirms all sheets + spatial_qa_report.md before continuing.
  BLOCKER entries halt GATE 1. WARN is non-blocking.
Stage C: Video prompter authors video prompts from sheets (Agent 5)
Stage C-Lock: Build approved render_manifest.json (build_manifest.py --approve)
  ═══ GATE 2 ═══
  STOP. User confirms render_manifest.json (sheet + prompt hashes locked) before paid GPU render.
Stage D: Render all clips sequentially with tail conditioning (Python, background)
```

At each gate, present the user with the file paths to review and wait for explicit
approval. If the user requests changes, fix and re-generate before proceeding.

## Stage A — Planning (Claude authors; validate + fix each; no image spend)

All commands run from `skills/story-maker-v4/`. Let `RUN=outputs/story-maker-v4/<name>`
(absolute path preferred) and `TARGET` be the target duration in seconds
(e.g. `300` for 5 min).

### A1. Develop the story (Agent 1)

Read the user's raw story file + `TARGET` and
[`assets/directors-guide.md`](assets/directors-guide.md) Section 1,
[`assets/anime-studio-playbook.md`](assets/anime-studio-playbook.md),
[`assets/unbound-storytelling-guide.md`](assets/unbound-storytelling-guide.md), and
[`assets/screenplay-format.md`](assets/screenplay-format.md). Author
`$RUN/developed_story.md` per [`prompts/story_developer.md`](prompts/story_developer.md):
produce a **full animation screenplay** (not a prose summary) with sluglines,
1–3 line action paragraphs, ALL-CAPS sound effects, formatted dialogue with
parenteticals, and montage sequences,
ending with `## Characters` (id/name/species/age/appearance, stable `char_NN` ids)
and `## Locations` (id/name/description/establishing_prompt). Then validate:

```bash
python3 scripts/validate.py "$RUN/developed_story.md" --schema screenplay
```

Read `$RUN/developed_story.md.validation.json`. If `ok:false`, fix every listed
error and re-run. **Do not proceed to Agent 1b until the screenplay passes.**

### A1b. Extract the beat board (Agent 1b)

After the developed story, author `$RUN/beat_board.md` per
[`prompts/beat_board.md`](prompts/beat_board.md): extract 8–15 dramatic beats
from the story, each with a visible `description:`, an `emotion:` register, and
an `estimated_seconds:` guide. Then:

```bash
python3 scripts/validate.py "$RUN/beat_board.md" --schema beat_board --target-seconds "$TARGET"
```

Read `$RUN/beat_board.md.validation.json`. If `ok:false`, fix every listed error
and re-run. **Do not proceed to Agent 2 until the beat board passes.**

### A2. Break into scenes (Agent 2)

Read `$RUN/beat_board.md` (Agent 1b). Compute `scene_count = ceil(TARGET / 70)`.
Author `$RUN/scenes.md` per [`prompts/scene_writer.md`](prompts/scene_writer.md) —
group beats into scenes, one `## Scene sN — <title>` block per scene with
`scene_id`, `target_seconds`, `cast`, `characters_present`, `location_id`,
`objects`, `beats`, `beat`, plus V4's anime-studio production metadata:
`style_target`, `acting_beat`, `layout_strategy`, `visual_motif`, `sound_world`.
Per-scene targets must sum within 15% of `TARGET`. Then:

```bash
python3 scripts/validate.py "$RUN/scenes.md" --schema scenes --target-seconds "$TARGET" --run-dir "$RUN"
```

Read `$RUN/scenes.md.validation.json`. If `ok:false`, fix every listed error and
re-run. **Do not proceed until it passes.**

### A3-Pre. Scene & Shot Depth Analysis (Director's Prerequisite)

Before authoring spatial geography or storyboard boundaries, analyze the scene's
dramatic beats, physical choreography, and dialogue tempo to establish the
**Dynamic Shot Depth & Duration Plan**:
- **Story-First Pacing Rule (MANDATORY)**:
  * **1-Shot Master Take / Oner (10.0s–15.0s)**: When the narrative beat is a continuous physical sequence (continuous slide down a cavern, sovereign entrance, unbroken falling action, high-stakes continuous tracking, or sustained emotional dialogue), **DO NOT CUT**. Author it as an unbroken single-shot Master Take (10.0–15.0s) filling the generation.
  * **Asymmetric 2-Shot Dynamic (2 shots per 15s)**: Unequal dramatic division based on action/reaction or statement/rebuttal (e.g. 11.5s setup + 3.5s reaction; 9.0s statement + 6.0s rebuttal; 5.0s confrontation + 10.0s lethal whisper and freeze).
  * **Dynamic Action Arc (3 shots per 15s)**: High-stakes physical sequences with varying tempo (e.g. 6.0s drift/approach + 2.5s shock impact + 6.5s smoke/standoff).
  * **Rapid Montage (4+ shots per 15s)**: Strictly reserved for high-tempo preparation, chaotic impacts, or rapid flashbacks.
  * **STRICT PROHIBITION**: Never mechanically split generations into identical shot counts (e.g. defaulting to 2 shots per generation or 4 shots per scene) or arbitrary uniform slices (e.g. 2 × 7.5s or 4 × 3.75s). Mechanical slicing will trigger validator warnings.
- **Dynamic Cinematography Rule (MANDATORY)**:
  * Every shot must have an intentional camera angle (`low_angle`, `high_angle`, `worm_eye`, `bird_eye`, `side_profile`, `three_quarter`, `over_the_shoulder`, `dutch_angle`, `pov`, `reverse_shot`).
  * **Static eye-level framing repeated across cuts triggers an anti-monotony warning in the validator.**
  * Pair contrasting, motivated camera angles shot-to-shot (e.g. pair a wide high-angle establishing shot with a low-angle hero close-up, a dynamic side-profile tracking shot, or a worm's-eye ground perspective followed by a canted dutch-angle tumble).
  * Every shot must feature motivated camera movement (`Tracking Shot`, `Push In`, `Pull Out`, `Crane Up/Down`, `Arc Shot`, `Tilt Up/Down`, `Whip Pan`). Monotonous static camera shots across cuts trigger a validator warning.

### A3a. Plan scene spatial geography (Agent 3a)

For each scene `sN`, author `$RUN/spatial_plan_sN.md` per
[`prompts/spatial_planner.md`](prompts/spatial_planner.md) guided by the Director's
Dynamic Shot Depth Plan: a 2.5D coordinate contract with landmarks, zones, per-generation
spatial state (location reference, anchor, positions, movement constraints), and per-shot
camera/subject state. Then:

```bash
python3 scripts/validate.py "$RUN/spatial_plan_sN.md" --schema spatial_plan \
  --run-dir "$RUN" --scene sN
```

Fix until `ok:true`. If a scene has no spatial plan, the pipeline falls back
to legacy behaviour (warning, not error).

### A3. Storyboard each scene (Agent 3)

For each scene `sN`, author `$RUN/storyboard_sN.md` per
[`prompts/storyboard_planner.md`](prompts/storyboard_planner.md) and
[`assets/directors-guide.md`](assets/directors-guide.md): the scene split
into `## Generation gK — a-b s` blocks (each 5-15s, contiguous, summing to the
scene's `target_seconds`), each with `panel_grid` and `### Shot` blocks
(contiguous, panels in reading order, Minimax camera vocabulary, audio +
dialogue, `shot_size` + `composition` fields, 8-value transition grammar).
**The 15s rule is load-bearing: a shot that does not fit in the
current generation moves whole to the next one.**

Shot durations must reflect the **Dynamic Shot Depth Plan** established in A3-Pre:
shots range dynamically from 1.5s shock cuts to full 15.0s master takes, varying
rhythm naturally (fast-slow-fast, building tension, or sustained emotional hold).
Every shot must enforce **multi-character prop ergonomics** (individual bowls/props in separate screen zones; never shared-bowl eating), **dialogue progression** (anti-repetition; authority arrival pivot), and **10-second commercial button structuring** where applicable.
Then:

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
  The storyboard-sheet prompt is a hierarchical document:
  **CANVAS → SCENE BIBLE → CHARACTER BIBLE → PROP CONTINUITY → CONTINUITY RULES
  → SEQUENCE PROGRESSION → PANEL DIRECTIONS → RENDERING STYLE → HARD EXCLUSIONS**.
  When a spatial plan exists, `build_images.py` deterministically materializes a
  **SPATIAL CONTINUITY BIBLE** at the **top** of each normal sheet prompt before
  the paid image call. No separate anchor prompt is authored.

Cast-lock: only reference `char_NN` ids that are in the scene's cast. Then:

```bash
python3 scripts/validate.py "$RUN/image_prompts/sN/storyboard_sheet_g1.txt" \
  --schema prompts --run-dir "$RUN" --scene sN
```

Fix until `ok:true` (it checks char/location prompt files and one sheet prompt
per generation exist and are non-empty).

**Stage A checkpoint:** every artifact + `.validation.json` present and passing; no
image dollars spent yet. This is the `--plan-only` equivalent.

## Stage A-QA — Critique (Claude evaluates; GATE 0; no image spend)

### AQ. Evaluate the full plan against 210+ directing questions (Agent 6)

After all Stage A artifacts pass structural validation, run the critique agent.
Read all artifacts (`developed_story.md`, `beat_board.md`, `scenes.md`, all
`storyboard_sN.md`) + [`assets/directing-questions.md`](assets/directing-questions.md)
and author `$RUN/critique_report.md` per
[`prompts/critique_agent.md`](prompts/critique_agent.md): evaluate every question
(200+ across 9 sections — Story, Shot Design, Camera, Composition, Editing,
Animation, Sound, Spatial, and H3/anime production), mark each PASS/FAIL/ADVISORY
with specific feedback. Then:

```bash
python3 scripts/validate.py "$RUN/critique_report.md" --schema critique \
  --question-bank assets/directing-questions.md
```

Read `$RUN/critique_report.md.validation.json`. If any FAIL remains:
- The director agent (1, 2, or 3) fixes the flagged artifacts
- Re-run the structural validators on the fixed artifacts
- Re-evaluate the affected questions and update `critique_report.md`
- Re-run the critique validator
- Repeat until zero FAILs

**═══ GATE 0 ═══**

STOP. The critique report must pass with zero FAILs before any image generation.
This catches directing problems while they're still cheap to fix (markdown edits),
before they become expensive (regenerated 4K sheets or re-rendered clips).
Do NOT proceed to Stage B until the critique passes.

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

This generates `storyboard_sheet_sN_gK.webp` for every generation (3840×2160).
When a spatial plan exists, `build_images.py` first deterministically
materializes a **SPATIAL CONTINUITY BIBLE** at the **top** of each normal sheet
prompt, then generates the sheet using the reference ordering:
previous sheet → conditional location → char refs → extras.
For `g1` (no previous sheet): location → char refs → extras.
The location panorama is attached for `g1` and for later generations whose
spatial plan sets `location_reference: attach`; otherwise omitted. Existing
sheets are skipped (resume-safe). Bridges do not get spatial blocks.

### B2a. Spatial visual QA (Agent 7, per scene)

After sheets are generated, if a `spatial_plan_sN.md` exists, Agent 7 inspects
each sheet against the spatial plan and writes `$RUN/spatial_qa_report.md` per
[`prompts/spatial_qa_agent.md`](prompts/spatial_qa_agent.md). Then:

```bash
python3 scripts/validate.py "$RUN/spatial_qa_report.md" --schema spatial_qa \
  --run-dir "$RUN" --scene sN
```

WARN entries are non-blocking. The report is shown at GATE 1 alongside the
sheets.

**═══ GATE 1 ═══**

STOP after all sheets + the spatial QA report are generated. Ask the user to
visually confirm every storyboard sheet — clean equal panels, zero text,
consistent characters, readable motion progression, and spatial geography
matching the spatial plan. Agent 4 should write camera geometry, not
shot-size jargon; keep HARD EXCLUSIONS short and surgical; never use brand
references like "Pixar". Do NOT proceed until the user explicitly says go.
If a sheet is wrong, delete it and re-run `--scene sN`. Spatial QA WARN entries
do not block GATE 1 but should be reviewed.

## Stage C — Vision + video prompts (Claude authors; validate + fix each)

### C1. Author each generation's Ref2VA prompt (Agent 5)

For each scene `sN` and generation `gK`: **Read** the sheet
(`$RUN/storyboard_sheet_sN_gK.webp`) to see what was actually drawn, plus
`storyboard_sN.md`, the episode context,
[`assets/minimax-h3-prompt-bible.md`](assets/minimax-h3-prompt-bible.md),
[`assets/minimax-h3-modes-guide.md`](assets/minimax-h3-modes-guide.md),
[`assets/cinematography-bible.md`](assets/cinematography-bible.md), and
[`assets/unbound-storytelling-guide.md`](assets/unbound-storytelling-guide.md).
Author `$RUN/video_prompts/sN_gK.txt` per [`prompts/video_prompter.md`](prompts/video_prompter.md):
a 6-section Ref2VA prompt (`subject_definitions` / `summary` /
`retention_analysis` / `detailed_description` / `overall_soundscape` /
`non_diegetic_music`), adhering to the "One Job" rule across reference assets,
aiming for 350–500 words in `detailed_description` without tag stuffing,
framing key acting/vocal beats in MCU/CU to preserve facial fidelity,
applying 3D camera motion syntax (`[Motion Type] with [amplitude] at [speed]`),
using `[Shot N] At MM:SS.mmm` timestamps in **generation-local seconds**,
the 8-value transition grammar (see the bible's transition table — vary transitions;
a cut must add new information), `<d>[English] ...</d>` dialogue with stable speaker IDs,
identity/count locks as inline prose, standardized seamless continuation phrasing for g2+,
and two separate audio sections. Then:

```bash
python3 scripts/validate.py "$RUN/video_prompts/sN_gK.txt" \
  --schema video_prompt --run-dir "$RUN" --scene sN
```

Fix until `ok:true` (it checks all six sections present and ordered, shot
count + timestamps against the storyboard, label definitions, dialogue tags,
warns on tag stuffing or shallow description, and rejects `char_NN` tokens).
Use `--legacy` to validate pre-Ref2VA prompts from existing runs.

**═══ GATE 2 ═══**

STOP after all video prompts pass. Present them to the user for review before
spending GPU hours. Do NOT render until the user explicitly says go.

## Stage D — Render (background Python, hours; fire-and-forget)

### D1. Render all scenes + concat (sequential with tail refs)

```bash
# one scene first (smoke), then all:
python3 scripts/render_all.py --output-dir "$RUN" --only-scenes sN
# then the full film:
python3 scripts/render_all.py --output-dir "$RUN"
```

Sequential single-pass render:
- **Render**: renders all generations (`g1, g2, ...`) sequentially via the
  Minimax H3 R2V workflow (sheet = reference image, video prompt = timeline,
  duration from the storyboard snapped to Minimax's frame grid).
- **Tail extraction**: after rendering `gK`, extracts its last 3s via ffmpeg.
- **Conditioning**: when rendering `g(K+1)`, the tail of `gK` is passed as a
  `ref_video` (dynamically wired into the Minimax H3 node, exactly like
  `ref_images`) so the model sees the actual rendered ending of the previous
  clip. `g1` has no tail ref (first generation of the run).
- **Cross-scene**: the tail of the last generation in scene N is passed to
  `g1` of scene N+1.
- **Concat**: per scene in storyboard `gens` order, then scenes →
  `final_film.mp4`, preserving Minimax's native stereo audio.

Existing clip files are skipped (resume-safe). Launch in the background; the
user returns later. Override size with `--megapixels/--aspect` (default 0.6MP
16:9 → 1056×608) and `--seed`.

Flags:
- `--tail-ref-seconds` (default 3.0): seconds of tail to extract as ref video
  for the next generation.

**Verify:** `scene_sN.mp4` plays with audio and generation handoffs read as
smooth transitions (not jarring jumps). `final_film.mp4` ≈ `TARGET` (±15%).
Use `python3 -m tools.seam_report "$RUN"` to quantify seam jumps.

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
10. **Generations render sequentially.** Each generation after g1 is
    conditioned on the *rendered* tail (3s) of the previous generation, so
    they cannot render in parallel. Deleting a clip invalidates its tail ref
    for the next generation — delete the next clip too and re-run.
    `TARGET_story = TARGET_delivery` (no additive bridge seconds).
11. **Tail ref videos are soft references, not frame pinning.** The tail
    video gives the model the actual ending state to continue from, but the
    model still interprets it freely. Describe the opening of each
    generation as continuing from the previous generation's ending.
12. **A cut must add new information.** If two adjacent shots share the same
    characters and only framing/angle changes, use `camera_move` instead of
    `hard_cut`. The validator errors on same-characters + same-shot_size +
    hard_cut, and warns on 3+ consecutive identical transitions. Vary
    transitions: `cut_on_action`, `reaction_cut`, `match_cut`, `whip_pan`,
    `audio_led` are all available — not every boundary needs to be a
    `hard_cut`.
13. **Shot size and composition serve the story.** Don't pick them for variety
    alone — see [`assets/directors-guide.md`](assets/directors-guide.md)
    Sections 2 & 4 for the "why" behind each. `closeup` → emotion;
    `extreme_wide` → isolation/scale; `low_angle` → power; `high_angle` →
    vulnerability. The `shot_size` field enables the definitive new-information
    check: without it, the validator can only warn.
