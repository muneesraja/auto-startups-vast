---
name: story-maker-v5
version: 5.0.0
description: "Production-ready story-to-video skill combining v3's canonical Ref2VA token-binding continuity and v4's animation screenplay format. Features dynamic shot pacing (1-shot master takes to 8-shot montages per 15s generation), strict 3x2 (min) to 3x3 (max) storyboard grids, boundary-aware tail-video conditioning, optional audio references, and approval-locked resumable rendering for seamless multi-minute films."
triggers:
  - story-maker-v5
  - story-maker v5
---

# Story Maker V5 — H3-directed scene production

Turns a high-level story into an animated film. **You (Claude Code) are the brain**:
you follow this runbook, author every markdown/text artifact, run the deterministic
validators after each, Read the rendered storyboard sheets for the vision step, and
self-correct on validator failure (write → validate → fix loop). **Python is the
hands**: deterministic media execution (image gen, Minimax H3 render, concat)
invoked via Bash. **Python makes zero LLM calls.** There is no ADK and no LiteLLM
here — the model authoring every artifact is you.

**V5 restores the proven Ref2VA token-binding continuity protocol from V3** while
incorporating V4's industry-standard animation screenplay intake and multi-tiered critique.
Each 5–15s generation uses a 6-to-9 panel storyboard sheet, structured Ref2VA prompt
with strict `<Subject N>`, `<Picture 1>`, `<Video 1>`, and `<Audio 1>` token
bindings, native stereo audio, and dynamic shot pacing (1 to 8 shots per
generation — oner master takes included).

## Architecture (brain / hands split)

| Layer | Owner | What it does |
|-------|-------|--------------|
| Authoring (Agents 1-5) + validation loop | **Claude Code** (this runbook) | Writes `developed_story.md`, `scenes.md`, `storyboard_*.md`, image prompts, `video_prompts/*.txt`; Reads sheet images for the vision step; runs `scripts/validate.py` after each and fixes on failure |
| Image media (char sheets, location locks, storyboard sheets) | **Python via Bash** | `scripts/build_images.py` → `replicate`/`fal_client` |
| Minimax H3 video render + concat | **Python background batch** | `scripts/render_all.py` → sequential render: each generation is conditioned on the previous generation's rendered tail (3s) via `ref_videos`, then concat. Hours — fire-and-forget |

Locked chunking: **1 scene = N generations; 1 generation = 1 storyboard sheet =
1 Minimax H3 render, 5-15s**. Each sheet is a clean panel grid (`panel_grid`,
6-9 panels, column-major numbering, NO text/timecodes on the image). Minimum / default
grid is `3x2` (6 panels), maximum grid is `3x3` (9 panels). Dynamic shot count:
**1 to 8 shots per generation** — a 1-shot master take (oner) is legal and
mandatory for unbroken beats; 1–2 shot generations carry the mandatory
super-high-detail requirement (see [`assets/production-rules.md`](assets/production-rules.md) §1).
A shot never straddles a generation boundary. Continuity between adjacent generations is
handled at render time by conditioning each generation on the previous generation's
rendered tail (3s) as a `ref_video` — **unless the boundary is a `hard_cut`**,
in which case the next generation opens fresh with no tail (see Boundary
policy below). No bridge generations are used.

## Episode intake (explicit entry point)

Production starts from an explicit `EpisodeSpec`, not from an implicit folder
convention. Stories live in a user-managed `stories/<series>/` directory —
read by path, never treated as production state.

**Scaffold a story** (idempotent — never overwrites):

```bash
python3 scripts/init_story.py lord-shiva-furious-moments
# or use the story-intake CLI (episode create, asset/audio import with
# naming conventions applied, check/status, prepare):
python3 ../story-intake/cli.py status lord-shiva-furious-moments
```

The canonical input folder (see `tools/story_input.py`):

```text
stories/<series>/
├── config.json         # series defaults — all fields optional
├── series.md           # story bible (world, canon, characters) for Agent 1
├── episodes/
│   └── episode-1/          # one folder per episode
│       ├── episode-1.md        # script / concept — user fills or agent drafts
│       ├── meta.json           # optional per-episode overrides
│       ├── audio/              # this episode's audio refs (shadow series audio/)
│       └── references/         # this episode's video refs
├── audio/              # series-wide: voice_S1.mp3 · music.wav · s1__ambience.flac
├── characters/         # user ref images: char_01.png → char_01 (+ .md notes)
├── locations/          # loc_01.png → loc_01
├── objects/            # obj_01.png → obj_01
├── style/              # moodboard / style frames → <run>/style/
└── references/         # series-wide video clips → <run>/references/
```

`config.json` fields: `title`, `style` (`3d_animation` default | `realistic` |
`pixar` | `comic` | `watercolor` | `bw_cartoon`), `style_notes`, `intake_mode`,
`duration_mode`, `default_duration_minutes`, `language`, `tone`, `rating`,
`aspect`, `cast` (`[{id, name, speaker, ref}]` — binds character → image →
`voice_<SN>` audio → `(SN)` speaker ID), `constraints`, `never_show`,
`defaults`. Episode meta overrides config per field.

```bash
python3 scripts/prepare_episode.py --stories-root stories --series shiva --episode 6
python3 scripts/prepare_episode.py --story-file stories/shiva/episodes/episode-6.md
```

Discovery looks for `episodes/episode-<N>/episode-<N>.md` first (the
canonical folder form), then flat `episodes/episode-<N>.md`, then flat-root
`episode-<N>.md` (legacy), `Episode*.md`, then `Story.md`. The sidecar
`episodes/episode-<N>/meta.json` declares title, `intake_mode`,
`duration_mode`, `target_seconds`, `handoff_from`, and audio refs
(`audio.voice_refs {S1: path}`, `audio.music_track`, `audio.dialogue_master`,
`audio.ambience`).

Audio materializes into `<run>/audio/` with precedence **meta-declared >
`episodes/episode-N/audio/` > `audio/`** — bare-role names (`voice_S1.mp3`,
`music.wav`) act as episode-wide references; scoped names
(`s1__ambience.wav`, `s1_g2__voice_S1.mp3`) keep their scope (see
`tools/audio_refs.py`).

User-supplied images are **pre-approved**: `characters/`, `locations/`, and
`objects/` files are copied into the shared assets dir and registered as
`origin: user` + `status: approved` — they win over generated sheets at GATE 1.
A `cast[].ref` entry maps an image to a canonical id explicitly; otherwise the
filename stem is the id (non-`char_NN`/`loc_NN`/`obj_NN` stems warn).
`series.md` is copied to `<run>/series_bible.md`.

`prepare_episode.py` writes `<run>/episode_spec.json`, a provenance copy of
the source (`story_source.md`), materialized audio + user assets,
`status.json` (`planned`), and updates the series index
`outputs/<series>/episodes.json`.

## Episode status tracking

Two orthogonal stages per episode:

- **Writing** (`episodes.json` index): `draft → planned → ready`
- **Production** (`<run>/status.json` + index): `planned → assets_approved →
  render_approved → rendering → qc_pending → complete`

Transitions are advanced automatically: `prepare_episode` (planned),
`assetctl approve-all` (assets_approved, GATE 1), `build_manifest --approve`
(render_approved, GATE 2), `render_all` (rendering → qc_pending),
`review_run --accept` (complete). A rejected clip (`review_run --reject`)
returns the run to `qc_pending` for re-render.

```bash
python3 scripts/episode_status.py --story-dir outputs/story-maker-v5/shiva   # board
python3 scripts/episode_status.py --run-dir <run>                            # one run
python3 scripts/episode_status.py --run-dir <run> --set qc_pending           # manual
```

## Episode context (mandatory)

**Always load the current episode's context before authoring anything.** That
means: the user's story file, `developed_story.md`, `scenes.md`, every already-
authored `storyboard_*.md` of this episode, and — for episode 2+ — the previous
episode's final scene storyboard/handoff. Minimax prompts open with lines like
"Continue directly from the previous scene", so you must know exactly what state
(cast on screen, positions, mood, lighting) each generation continues from.
Never author a storyboard or video prompt from the scene beat alone.

## Canonical worked example

All prompt files in `prompts/` use one shared worked example —
**"Ollie's Dive"** in [`assets/example-ollie.md`](assets/example-ollie.md)
(adapted from the *Swapped* opening analyzed in `Research/ollie/`). Entity
IDs `char_01`–`char_03`, `loc_01`–`loc_02`, `obj_01`–`obj_03`, scene `s1`,
and generation `s1/g2` mean the same thing in every prompt. When editing
prompt examples, keep them on this story — do not introduce new example
casts. The long-form end-to-end version is
[`EXAMPLE_GENERATION.md`](EXAMPLE_GENERATION.md).

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
- Python deps: `pip install -r skills/story-maker-v5/requirements.txt`
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

## Boundary policy (load-bearing — `tools/boundary.py`)

Every generation boundary is either a **continuation** or a **fresh cut**:

- Within a scene: generation `gK+1`'s shot-1 `transition` decides.
- Across scenes: the previous scene's `handoff.transition` decides.
- `hard_cut` → **fresh cut**: the renderer attaches no tail video, the video
  prompt must NOT declare `<Video 1>`, and the summary prefix is
  `[reference generation]`.
- Any other value (`continuous`, `cut_on_action`, `reaction_cut`,
  `match_cut`, `whip_pan`, `audio_led`, `camera_move`) → **continuation**:
  the previous rendered tail (3s) is attached as `ref_videos`, the video
  prompt must declare `<Video 1>`, and `[Shot 1]` opens with the seamless-
  continuation sentence.

The handoff transition and the next scene's g1 shot-1 transition must agree:
`hard_cut` handoff + `continuous` shot 1 is a validator error. The
validator's `<Video 1>` check and the renderer both read this one policy.

## Audio references (optional — `tools/audio_refs.py`)

Drop audio files into `$RUN/audio/` with role-tagged names to attach them as
MiniMax `<Audio 1>` references:

- `audio/<scene>_<gen>__<role>.<ext>` — scoped to one generation
  (e.g. `s1_g1__voice_S1.mp3` — an ElevenLabs-generated voice sample).
- `audio/<scene>__<role>.<ext>` — scoped to every generation of a scene.
- Roles: `voice_S<N>` (speaker timbre/delivery guide for speaker ID S<N>),
  `dialogue` (approved dialogue master), `music` (music reference),
  `sfx`/`ambience`/`timing` (guides).
- Attached refs are discovered by `tools/audio_refs.py` and hashed into
  `render_manifest.json` — rebuild the manifest after adding files.

When a generation has an audio ref, its video prompt MUST declare `<Audio 1>`
in `subject_definitions:` with its role, give it a `retention_analysis:` line,
and bind each speaker ID used in dialogue (`(S1) is <Subject 1>'s voice.`).
An audio ref guides the render — it is not automatically the delivered
soundtrack; mixing the approved master into delivery is a post-render choice.

## Durable artifacts + resume waterfall

Output layout: `outputs/story-maker-v5/<story>/epi-N/`; per-story shared assets at
`<story>/assets/` (`characters/{cid}.png`, `locations/{lid}.png`,
`objects/{oid}.png` — never wiped). The shared asset registry lives at
`<story>/assets/asset_registry.json` — the h3 GlobalAssetRegistry schema:
versioned, content-addressed assets with `draft → approved` status, hosted
URLs, and per-episode sheet keys (`<episode>.s1_g1`). A new episode reads the
existing registry and only creates new characters/locations/objects; existing
assets are skipped. `ref_images:` names resolve only `approved` assets for
cross-episode reuse — promoted at GATE 1 via:

```bash
python3 scripts/assetctl.py --run-dir <run> approve-all   # GATE 1 promotion
python3 scripts/assetctl.py --run-dir <run> list [--status draft]
python3 scripts/assetctl.py --run-dir <run> doctor
```

A V1 flat registry is migrated on first open (backup:
`asset_registry.v1.bak.json`); migrated entries land as `draft` and require
GATE 1 approval before reuse.
Before each step,
**check which artifacts already exist and continue from the first missing one.** Do
not re-author or re-generate anything.
1. developed_story.md + story.json     (Claude)             — Agent 1 / Intake Normalizer
   (screenplay format per assets/screenplay-format.md; validate --schema screenplay)
   (supports intake_mode: preserve_script | develop_from_concept; canonical constraints)
1b. beat_board.md                      (Claude)             — Agent 1b → validate --schema beat_board
   (8-15 dramatic beats is advisory; 3 minimum enforced; emotion + estimated timing)
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
   (REQUIRED for render; immutable content-addressed lock: sha256 of scenes.md,
   every storyboard, every sheet, every video prompt, every audio ref + duration;
   any post-approval edit to a hashed input invalidates the manifest and render
   refuses to run)
   ═══ GATE 2: user confirms render_manifest.json before paid GPU render ═══
7c. render_state.json                  (Python, mutable)    — written/read by render_all.py
   (per-generation status, clip path, ComfyUI prompt_id, attempts, input
   fingerprint, timestamps — resume data lives here, NOT in the manifest)
8. clips/<scene>/<gen>.mp4             (Python Minimax H3)  — render_all.py --manifest render_manifest.json
   (manifest must exist and be approved; input fingerprints checked before
   skipping; interrupted runs re-poll persisted prompt_ids instead of requeuing)
9. scene_<scene>.mp4                   (Python concat, audio preserved)
10. final_film.mp4                     (Python concat)
10b. qc.md                             (Python)             — render_all.py writes a review report
   (per-clip status, durations, seam notes, ffprobe verification results)

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

All commands run from `skills/story-maker-v5/`. Let `RUN=outputs/story-maker-v5/<name>`
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
**Dynamic Shot Depth & Duration Plan** per the canonical taxonomy in
[`assets/production-rules.md`](assets/production-rules.md) §1 (1-shot oner →
asymmetric 2-shot → 3-shot action arc → 4+ rapid montage; mechanical equal
slicing is prohibited and 1–2 shot generations require mandatory high detail).
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
Every shot must enforce the canonical policies in
[`assets/production-rules.md`](assets/production-rules.md): **multi-character prop
ergonomics** (§2), **dialogue progression** (§3), and **10-second commercial
button structuring** (§4) where applicable.
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
sizing `detailed_description` to the shot count (≥120 words for a oner,
≥250 for 2-shot, ~350+ for busier generations) without tag stuffing,
framing key acting/vocal beats in MCU/CU to preserve facial fidelity,
applying 3D camera motion syntax (`[Motion Type] with [amplitude] at [speed]`),
using `[Shot N] At MM:SS.mmm` timestamps in **generation-local seconds**,
the 8-value transition grammar (see the bible's transition table — vary transitions;
a cut must add new information), `<d>[English] ...</d>` dialogue with stable speaker
IDs bound to subjects (`(S1) is <Subject 1>'s voice.`),
identity/count locks as inline prose, seamless continuation phrasing at
continuation boundaries (never at `hard_cut` boundaries — see Boundary policy),
`<Audio 1>` declared when `audio/_manifest.json` attaches a ref to the generation,
and two separate audio sections. Then:

```bash
python3 scripts/validate.py "$RUN/video_prompts/sN_gK.txt" \
  --schema video_prompt --run-dir "$RUN" --scene sN
```

Fix until `ok:true` (it checks all six sections present and ordered, shot
count + timestamps against the storyboard, label definitions, dialogue tags,
warns on tag stuffing or shallow description, and rejects `char_NN` tokens).
Use `--legacy` to validate pre-Ref2VA prompts from existing runs.

### C2. Build the approved render manifest

```bash
python3 scripts/build_manifest.py "$RUN" --approve
```

Writes `$RUN/render_manifest.json`: every generation with the sha256 of its
storyboard sheet, video prompt, and attached audio ref, plus hashes of
`scenes.md` and every `storyboard_*.md`. The manifest is **immutable once
approved** — editing any hashed input afterwards makes the manifest stale
and `render_all.py` refuses to run until you rebuild and re-approve.

**═══ GATE 2 ═══**

STOP after the manifest is built and approved. Present the video prompts and
the manifest to the user for review before spending GPU hours. Do NOT render
until the user explicitly says go.

## Stage D — Render (background Python, hours; fire-and-forget)

### D1. Render all scenes + concat (sequential with tail refs)

```bash
# one scene first (smoke), then all:
python3 scripts/render_all.py --output-dir "$RUN" --only-scenes sN
# then the full film:
python3 scripts/render_all.py --output-dir "$RUN"
```

Sequential single-pass render (requires an approved `render_manifest.json` —
run `build_manifest.py --approve` first; render aborts without it):
- **Preflight**: verifies the manifest is approved and every hashed input
  (scenes.md, storyboards, sheets, video prompts, audio refs) still matches
  its recorded sha256. A stale input aborts before any GPU spend.
- **Render**: renders all generations (`g1, g2, ...`) in `scenes.md` order
  (not filename order) via the Minimax H3 R2V workflow (sheet = reference
  image, video prompt = timeline, duration from the storyboard snapped to
  Minimax's frame grid). The ComfyUI `prompt_id` is persisted to
  `render_state.json` immediately after queueing — an interrupted run
  re-polls the existing job instead of submitting a duplicate.
- **Tail extraction**: after rendering `gK`, extracts its last 3s via ffmpeg.
- **Conditioning (boundary-aware)**: at a continuation boundary the tail of
  `gK` is passed as a `ref_video` so the model sees the actual rendered
  ending. At a `hard_cut` boundary (gK+1 shot-1 `hard_cut`, or the previous
  scene's `handoff.transition: hard_cut`) **no tail is attached** — the
  generation opens fresh.
- **Audio refs**: files in `audio/` matching the generation's naming scope
  (see Audio references above) are uploaded and attached as the generation's
  audio reference; the approved manifest pins their hashes.
- **Concat**: per scene in storyboard `gens` order, then scenes →
  `final_film.mp4`, preserving Minimax's native stereo audio.
- **Verify**: every downloaded clip is written via `*.part` then verified
  with ffprobe (codec + duration) before being promoted. At the end,
  `qc.md` is written summarizing per-clip status for review.

Resume is **fingerprint-aware**, not just file-exists: `render_state.json`
records each clip's input fingerprint (sheet + prompt + audio hashes, plus
the predecessor clip's hash when a tail was attached). A changed input —
including a regenerated predecessor — marks the clip and its dependents
stale and re-renders them. Launch in the background; the user returns later.
Override size with `--megapixels/--aspect` (default 0.6MP 16:9 → 1056×608)
and `--seed`.

Flags:
- `--tail-ref-seconds` (default 3.0): seconds of tail to extract as ref video
  for the next generation.
- `--only-scenes sN [sM ...]`: render a subset — clips only, writes
  `scene_sN.mp4` but never `final_film.mp4` (a partial preview is not the film).

**Verify:** `scene_sN.mp4` plays with audio and generation handoffs read as
smooth transitions (not jarring jumps). `final_film.mp4` ≈ `TARGET` (±15%).
Use `python3 -m tools.seam_report "$RUN"` to quantify seam jumps, and read
`qc.md` for the machine-generated render report.

## Resume rules

- Before any step, check which artifacts exist on disk and continue from the first
  missing one. The build/render scripts already skip existing files; for authoring
  steps, do not overwrite a passing artifact.
- To force a regen, delete the target file (and its `.validation.json`) and re-run
  the step. `render_all.py` automatically detects a stale input fingerprint and
  re-renders the clip plus every generation downstream that consumed its tail.
- Resume test: delete one `clips/sN/g2.mp4`, re-run `render_all.py` — only that
  clip + its dependents + `scene_sN.mp4` + `final_film.mp4` re-execute.

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
10. **Generations render sequentially.** Each generation after the first
    (at a continuation boundary) is conditioned on the *rendered* tail (3s)
    of the previous generation, so they cannot render in parallel.
    `render_state.json` tracks the dependency fingerprint — a regenerated
    clip automatically marks the next generation stale; you no longer need
    to delete dependent clips by hand.
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
