# Story Maker V3 — Deep Architecture

> **One-line summary:** Claude Code is the brain (authors all markdown/text artifacts, runs deterministic validators, does the vision step); Python is the hands (deterministic image generation, Minimax H3 video render, concat). No ADK, no LiteLLM, no LLM calls from Python.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Brain / Hands Split](#2-brain--hands-split)
3. [Agent Roster](#3-agent-roster)
4. [Pipeline Stages + Gates](#4-pipeline-stages--gates)
5. [Artifact Waterfall](#5-artifact-waterfall)
6. [Story Hierarchy](#6-story-hierarchy)
7. [Asset System (Cross-Episode)](#7-asset-system-cross-episode)
8. [Image Generation Subsystem](#8-image-generation-subsystem)
9. [Video Render Subsystem](#9-video-render-subsystem)
10. [Validation Subsystem](#10-validation-subsystem)
11. [Critique Subsystem (GATE 0)](#11-critique-subsystem-gate-0)
12. [Configuration](#12-configuration)
13. [File Map](#13-file-map)
14. [Data Flow Diagrams](#14-data-flow-diagrams)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STORY MAKER V3                                  │
│                                                                         │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐     │
│   │  CLAUDE CODE │    │   PYTHON     │    │   EXTERNAL BACKENDS  │     │
│   │  (the brain) │    │  (the hands) │    │                      │     │
│   │              │    │              │    │  • Replicate (GPT     │     │
│   │  Agents 1-6  │───▶│  scripts/    │───▶│    Image 2, 4K)      │     │
│   │  Authors     │    │  tools/      │    │  • fal (GPT Image 2) │     │
│   │  markdown +  │    │  config.py   │    │  • ComfyUI (Minimax  │     │
│   │  prompt files│    │  Deterministic│   │    H3 R2V render)    │     │
│   │              │◀───│  execution   │◀───│  • ffmpeg (concat)   │     │
│   │  Runs        │    │              │    │                      │     │
│   │  validators  │    │  Zero LLM    │    │                      │     │
│   │  Reads sheets│    │  calls       │    │                      │     │
│   │  (vision)    │    │              │    │                      │     │
│   └──────────────┘    └──────────────┘    └──────────────────────┘     │
│                                                                         │
│   Gates: GATE 0 (critique) → GATE 1 (sheets) → GATE 2 (video prompts)  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key constraints:**
- Each Minimax H3 generation is at most **15 seconds** (load-bearing).
- Each generation uses **one clean storyboard sheet** (4K, no text) as the reference image.
- Each generation produces **native stereo audio** (Minimax generates it).
- No panel crops, no upscales, no outpaints — the sheet goes to Minimax verbatim.
- Storyboard sheet prompts are hierarchical: **CANVAS → SCENE/CHARACTER/PROP
  BIBLES → CONTINUITY RULES → SEQUENCE → PANEL DIRECTIONS → RENDERING STYLE →
  HARD EXCLUSIONS**; the materialized spatial contract lives at the top as the
  **SPATIAL CONTINUITY BIBLE**.
- Python makes **zero LLM calls** — all authoring is Claude.

---

## 2. Brain / Hands Split

| Layer | Owner | What it does |
|-------|-------|--------------|
| **Authoring** (Agents 1-6) | Claude Code | Writes `developed_story.md`, `beat_board.md`, `scenes.md`, `storyboard_*.md`, image prompts, video prompts, critique report. Reads sheet images for the vision step. Runs `scripts/validate.py` after each and fixes on failure. |
| **Image media** (sheets, assets) | Python via Bash | `scripts/build_images.py` → `tools/image_pipeline.py` → Replicate/fal. Generates 4K character sheets, location locks, object sheets, storyboard sheets. |
| **Video render** (Minimax H3) | Python background | `scripts/render_all.py` → `tools/minimax_workflow.py` → ComfyUI. Sequential render: each generation conditioned on the previous generation's rendered tail. |
| **Concat** (final film) | Python via Bash | `tools/video_concat.py` → ffmpeg. Per-scene concat, then final film. |
| **Validation** (deterministic) | Python via Bash | `scripts/validate.py` → `tools/validators.py` + `tools/critique_validator.py`. Pure parsing + assertions, no LLM. |

---

## 3. Agent Roster

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AUTHORING AGENTS                             │
│                                                                     │
│  Agent 1  — Story Developer                                         │
│  Agent 1b — Beat Board Extractor                                   │
│  Agent 2  — Scene Writer                                           │
│  Agent 3a — Spatial Planner (2.5D coordinate contract)             │
│  Agent 3  — Storyboard Planner (the Director)                      │
│  Agent 4  — Image Prompter                                         │
│  Agent 5  — Video Prompter (vision: reads sheet images)            │
│  Agent 6  — Critique Agent (self-questioning, 210+ questions)      │
│  Agent 7  — Spatial Visual QA (post-sheet, non-blocking)          │
└─────────────────────────────────────────────────────────────────────┘
```

| Agent | Input | Output | Validator |
|-------|-------|--------|-----------|
| **1** Story Developer | Raw story file + TARGET | `developed_story.md` (narrative + Characters/Locations/Objects) | None (free-form) |
| **1b** Beat Board | `developed_story.md` + TARGET | `beat_board.md` (8-15 beats with emotion + timing) | `--schema beat_board` |
| **2** Scene Writer | `beat_board.md` + `developed_story.md` + TARGET | `scenes.md` (N scenes, each with cast/location/objects/beats) | `--schema scenes` |
| **3a** Spatial Planner | `scenes.md` + location lock prompt | `spatial_plan_sN.md` (2.5D landmarks/zones/per-gen/per-shot state) | `--schema spatial_plan` |
| **3** Storyboard Planner | `spatial_plan_sN.md` + `scenes.md` + `developed_story.md` + episode context | `storyboard_sN.md` (generations → shots, per scene) | `--schema storyboard` |
| **4** Image Prompter | `storyboard_sN.md` + `spatial_plan_sN.md` + `developed_story.md` | `image_prompts/` (character/location/object/sheet/anchor prompts) | `--schema prompts` |
| **6** Critique Agent | All Stage A artifacts + `directing-questions.md` | `critique_report.md` (210+ questions, PASS/FAIL) | `--schema critique` |
| **5** Video Prompter | Sheet images (vision) + `storyboard_sN.md` + `spatial_plan_sN.md` + prompt bible | `video_prompts/sN_gK.txt` (Ref2VA 6-section prompt) | `--schema video_prompt` |
| **7** Spatial QA | Sheet images (vision) + `spatial_plan_sN.md` | `spatial_qa_report.md` (PASS/WARN per sheet) | `--schema spatial_qa` |

---

## 4. Pipeline Stages + Gates

```
STAGE A: Planning (Claude authors; validate + fix each; no image spend)
│
├── A1.   developed_story.md         (Agent 1)
├── A1b.  beat_board.md              (Agent 1b) → validate --schema beat_board
├── A2.   scenes.md                  (Agent 2)  → validate --schema scenes
├── A3a.  spatial_plan_sN.md         (Agent 3a) → validate --schema spatial_plan (per scene)
├── A3.   storyboard_sN.md           (Agent 3)  → validate --schema storyboard  (per scene)
├── A4.   image_prompts/             (Agent 4)  → validate --schema prompts     (per scene)
│         (spatial continuity block is deterministically materialized by build_images.py)
│
STAGE A-QA: Critique (Claude evaluates; GATE 0; no image spend)
│
├── AQ.   critique_report.md         (Agent 6)  → validate --schema critique
│         ═══ GATE 0 ═══  (zero FAILs required before image generation)
│
STAGE B: Image media (Python via Bash; gated)
│
├── B1.   assets/characters/*.webp   (Python T2I, 4K, once)
├── B1.   assets/locations/*.webp    (Python T2I, 4K wide-angle 360°, once)
├── B1.   assets/objects/*.webp      (Python T2I, 4K, once)
├── B2.   storyboard_sheet_sN_gK.webp (Python, per generation, 4K)
├── B2.   storyboard_sheet_sN_gK.webp (Python, per generation, 4K)
├── B2a.  spatial_qa_report.md       (Agent 7)  → validate --schema spatial_qa  (per scene)
│         ═══ GATE 1 ═══  (user visually confirms all sheets + spatial QA report)
│
STAGE C: Vision + video prompts (Claude authors; validate + fix each)
│
├── C1.   video_prompts/sN_gK.txt    (Agent 5, vision: reads sheet images)
├── C1.   video_prompts/sN_gK.txt    (Agent 5, per generation)
│         ═══ GATE 2 ═══  (user confirms video prompts before paid render)
│
STAGE D: Render (background Python, hours; fire-and-forget)
│
├── D1.   clips/sN/gK.mp4            (Minimax H3, sequential — conditioned on previous tail)
├── D1.   scene_sN.mp4               (ffmpeg concat)
├── D1.   final_film.mp4             (ffmpeg concat of all scenes)
```

### Gate summary

| Gate | When | What | Enforcement |
|------|------|------|-------------|
| **GATE 0** | After Stage A-QA | Critique report has zero FAILs | Deterministic (`validate --schema critique`) |
| **GATE 1** | After Stage B (sheets) | User visually confirms all storyboard sheets | Runbook rule (Claude stops and asks) |
| **GATE 2** | After Stage C (video prompts) | User reviews video prompts before paid render | Runbook rule (Claude stops and asks) |

---

## 5. Artifact Waterfall

```
developed_story.md
  │  (free-form narrative + ## Characters + ## Locations + ## Objects)
  │
  ▼
beat_board.md
  │  (8-15 beats: description + emotion + estimated_seconds)
  │
  ▼
scenes.md
  │  (N scenes: scene_id + target_seconds + cast + location_id + objects + beats + beat)
  │
  ▼
storyboard_s1.md    storyboard_s2.md    storyboard_sN.md
  │  (generations gK → shots: panels + characters_present + shot_size +
  │   composition + action + camera + audio + dialogue + transition)
  │  (generations only — no bridge generations)
  │
  ▼
image_prompts/
  ├── characters/char_01.txt    (character sheet prompt, 4K)
  ├── locations/loc_01.txt      (location lock prompt, 4K 360°)
  ├── objects/obj_01.txt        (object sheet prompt, 4K)
  └── s1/storyboard_sheet_g1.txt (storyboard sheet prompt, 4K)
      s1/storyboard_sheet_g1.txt (sheet prompt)
  │  (any prompt may begin with ref_images: name1, name2, ... for dynamic refs)
  │
  ▼
critique_report.md
  │  (200+ questions evaluated: PASS/FAIL/ADVISORY per question)
  │  ═══ GATE 0 ═══
  │
  ▼
assets/characters/char_01.webp   (4K, shared across episodes)
assets/locations/loc_01.webp     (4K wide-angle 360°, shared)
assets/objects/obj_01.webp       (4K, shared)
storyboard_sheet_s1_g1.webp      (4K, per generation)
storyboard_sheet_s1_g1.webp      (4K, per generation)
  │  ═══ GATE 1 ═══
  │
  ▼
video_prompts/s1_g1.txt          (Ref2VA 6-section prompt)
video_prompts/s1_g1.txt          (Ref2VA prompt)
  │  ═══ GATE 2 ═══
  │
  ▼
clips/s1/g1.mp4                  (Minimax H3 render, ≤15s, native stereo audio)
clips/s1/g1.mp4                  (render, conditioned on previous tail)
scene_s1.mp4                     (ffmpeg concat: g1, b1, g2, b2, g3, ...)
final_film.mp4                   (ffmpeg concat of all scenes)
```

---

## 6. Story Hierarchy

```
EPISODE (epi-N folder)
│
├── STORY (developed_story.md)
│   └── BEATS (beat_board.md: 8-15 beats with emotion + timing)
│       │
│       ▼
│   SEQUENCES (not yet implemented — future phase)
│       │
│       ▼
│   SCENES (scenes.md: N scenes, each grouping 1+ beats)
│       │
│       ▼
│   GENERATIONS (storyboard_sN.md: gK blocks, each ≤15s)
│       │
│       ▼
│   SHOTS (within each generation: ### Shot N blocks)
│       │  Each shot has:
│       │  • panels: [1, 2, ...]     (panel indices on the sheet)
│       │  • characters_present      (⊆ scene cast)
│       │  • shot_size               (7-value taxonomy)
│       │  • composition             (12-value taxonomy)
│       │  • action                  (micro-beats, not single verbs)
│       │  • camera                  (Minimax motion vocabulary)
│       │  • audio                   (foley + ambient + impact)
│       │  • dialogue                (cid: "line" format)
│       │  • transition              (8-value grammar)
│       │
│       ▼
│   ANIMATION (action: field → video prompt → Minimax render)
│       │
│       ▼
│   SOUND (audio: field + overall_soundscape + non_diegetic_music)
```

### Generation continuity (tail-video conditioning)

No bridge generations are used. Continuity between adjacent generations is
handled at render time:

```
g1 → g2 → g3 → ... → final_film.mp4
```

- Generations render **sequentially** — each generation after g1 is
  conditioned on the previous generation's rendered tail (3s) via `ref_videos`.
- `g1` has no tail ref (first generation of the run).
- Cross-scene: the tail of the last generation in scene N is passed to
  `g1` of scene N+1.
- `TARGET_story = TARGET_delivery` (no additive bridge seconds).

---

## 7. Asset System (Cross-Episode)

```
outputs/story-maker-v3/<story>/
├── assets/                          ← STORY-LEVEL SHARED (never wiped)
│   ├── asset_registry.json          ← shared registry: characters + locations + objects + sheets
│   ├── characters/
│   │   ├── char_01.webp             (4K, generated once, reused across episodes)
│   │   └── char_02.webp
│   ├── locations/
│   │   ├── loc_jungle_stream.webp   (4K wide-angle 360°, generated once)
│   │   └── loc_battle_clearing.webp
│   └── objects/
│       ├── obj_01.webp              (4K, generated once)
│       └── obj_02.webp
├── epi-1/                           ← EPISODE-LOCAL
│   ├── developed_story.md
│   ├── beat_board.md
│   ├── scenes.md
│   ├── storyboard_s1.md
│   ├── image_prompts/
│   ├── critique_report.md
│   ├── storyboard_sheet_s1_g1.webp  (4K, per generation)
│   ├── video_prompts/
│   ├── clips/
│   ├── scene_s1.mp4
│   └── ...
├── epi-2/                           ← EPISODE 2 reads existing registry
│   └── ...                          (only NEW characters/locations/objects are generated)
└── ...
```

### AssetRegistry (`tools/image_pipeline.py`)

```python
class AssetRegistry:
    # Lives at <story>/assets/asset_registry.json (story-level, shared)
    # Auto-migrates from legacy per-episode registries

    # Sections:
    #   characters: {char_01: {output_path, fal_image_url}}
    #   locations:  {loc_01:  {output_path, fal_image_url}}
    #   objects:    {obj_01:  {output_path, fal_image_url}}
    #   sheets:     {s1_g1:   {output_path, fal_image_url}}  (episode-local)

    def character(cid) -> dict
    def location(lid) -> dict
    def object(oid) -> dict
    def sheet(sid) -> dict
    def save() / load()
```

### Dynamic reference images (`ref_images:`)

Any prompt file may begin with:
```
ref_images: loc_kitchen, char_01, obj_stick
```

The backend:
1. Parses the `ref_images:` line (`parse_ref_images()`)
2. Resolves names via the registry (`resolve_ref_names()` — objects → locations → characters → sheets)
3. Attaches up to 10 reference URLs to the image generation call
4. Deduplicates and caps at the provider/model limit

---

## 8. Image Generation Subsystem

```
┌─────────────────────────────────────────────────────────────────┐
│                   IMAGE GENERATION FLOW                         │
│                                                                 │
│  scripts/build_images.py                                        │
│    │                                                            │
│    ├── --assets-only  →  build_assets()                         │
│    │     ├── generate_character_sheet()  →  4K character plate  │
│    │     ├── generate_location_lock()    →  4K 360° panorama    │
│    │     └── generate_object_sheet()     →  4K object plate     │
│    │                                                            │
│    └── --scene sN     →  build_sheets()                         │
│          ├── generate_storyboard_sheet() →  4K panel grid       │
│          └── (bridge sheet generation removed)                   │
│                                                                 │
│  tools/image_pipeline.py                                        │
│    ├── AssetRegistry (story-level shared registry)              │
│    ├── build_sheet_ref_urls()    (location → prev sheet → chars)│
│    ├── (bridge ref URLs removed)                                  │
│    ├── parse_ref_images()        (extract ref_images: line)     │
│    └── resolve_ref_names()       (resolve names → registry URLs)│
│                                                                 │
│  tools/grok_tools.py  (dispatcher)                              │
│    ├── generate_grok_t2i()   →  text-to-image (with ref_urls)   │
│    └── generate_grok_edit()  →  image edit (with ref_urls)      │
│                                                                 │
│  tools/grok_replicate.py  (Replicate backend)                   │
│    └── openai/gpt-image-2 at 3840×2160, quality=medium, webp    │
│                                                                 │
│  tools/grok_fal.py  (fal backend)                               │
│    └── openai/gpt-image-2 (alternative backend)                 │
│                                                                 │
│  Sheet builders:                                                │
│    tools/char_sheet_builder.py    (character sheet prompt)      │
│    tools/location_sheet_builder.py (location lock prompt)       │
│    tools/object_sheet_builder.py  (object sheet prompt)         │
└─────────────────────────────────────────────────────────────────┘
```

### Reference image ordering

**Storyboard sheet refs:** `location lock → previous sheet → character sheets → agent-named refs`

The storyboard sheet prompt is a hierarchical document:
**CANVAS → SCENE BIBLE → CHARACTER BIBLE → PROP CONTINUITY → CONTINUITY RULES
→ SEQUENCE PROGRESSION → PANEL DIRECTIONS → RENDERING STYLE → HARD EXCLUSIONS**.
When a `spatial_plan_sN.md` exists, `tools/spatial_prompt_builder.py` prepends a
**SPATIAL CONTINUITY BIBLE** at the top of the prompt with ENVIRONMENT BIBLE,
CONTINUITY RULES, and PANEL STAGING sections. This keeps immutable spatial
facts separate from Agent 4's creative direction.

**Bridge sheet refs:** `location lock → from sheet → to sheet → character sheets → agent-named refs`

### Image sizes

| Asset | Size | Quality |
|-------|------|---------|
| Character sheet | 3840×2160 (4K) | medium |
| Location lock | 3840×2160 (4K, wide-angle 360°) | medium |
| Object sheet | 3840×2160 (4K) | medium |
| Storyboard sheet | 3840×2160 (4K) | medium |
| Output format | webp, compression 90 | ~1-3MB per file |

---

## 9. Video Render Subsystem

```
┌─────────────────────────────────────────────────────────────────┐
│                    VIDEO RENDER FLOW                            │
│                                                                 │
│  scripts/render_all.py                                          │
│    │                                                            │
│    ├── Sequential: render generations in order                 │
│    │   └── _render_clip(scene, gen_id)                         │
│    │       ├── _find_sheet()  →  storyboard_sheet_sN_gK.webp   │
│    │       ├── video_prompts/sN_gK.txt  (Ref2VA prompt)        │
│    │       ├── ref_videos: [tail.mp4]  (previous gen's tail)   │
│    │       │   (dynamically wired into Minimax H3 node)        │
│    │       └── tools/minimax_workflow.py                       │
│    │           ├── load_api_workflow()  (ComfyUI JSON)         │
│    │           ├── patch_generation()   (wire sheet + prompt)  │
│    │           └── render_generation()  (ComfyUI API → mp4)    │
│    │                                                           │
│    ├── Extract: tail after each generation                     │
│    │   └── _extract_tail_ref()  (ffmpeg, 3s tail)              │
│    │                                                           │
│    └── Concat                                                  │
│        ├── tools/video_concat.py  (ffmpeg)                    │
│        ├── scene_sN.mp4  (g1, b1, g2, b2, g3, ...)            │
│        └── final_film.mp4  (all scenes)                       │
│                                                                 │
│  Backend: ComfyUI + Minimax H3 R2V                             │
│    ├── ref2va UNet                                              │
│    ├── video + audio VAEs                                      │
│    ├── qwen3vl CLIP                                             │
│    ├── Resolution: 0.6MP 16:9 → 1056×608 (default)            │
│    └── Native stereo audio                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Two-pass render

| Pass | What | Conditioned on |
|------|------|----------------|
| **Render** | Each generation (g1, g2, ...) sequentially | Sheet image + video prompt + ref_video (previous tail) |
| **Extract** | 3s tail of gK after rendering | Rendered clip of gK |
| **Concat** | Per-scene then final film | All rendered clips |

---

## 10. Validation Subsystem

```
┌─────────────────────────────────────────────────────────────────┐
│                    VALIDATION FLOW                              │
│                                                                 │
│  scripts/validate.py <artifact> --schema <schema>               │
│    │                                                            │
│    └── tools/validators.py  →  validate()                       │
│          │                                                      │
│          ├── beat_board   → validate_beat_board()               │
│          ├── scenes       → validate_scenes()                   │
│          │   (cross-checks beats: against beat_board.md)        │
│          ├── storyboard   → validate_storyboard()               │
│          │   (cross-checks against scenes.md)                   │
│          ├── prompts      → validate_prompts()                  │
│          │   (cross-checks against storyboard_sN.md)            │
│          ├── video_prompt → validate_video_prompt()             │
│          │   (cross-checks shot timestamps against storyboard)  │
│          └── critique     → validate_critique_report()          │
│              (from tools/critique_validator.py)                 │
│                                                                 │
│  Each validator:                                                │
│    1. Parses the markdown artifact                              │
│    2. Checks structure (fields, timing, vocabulary)             │
│    3. Returns ValidationResult {ok, errors, warnings}          │
│    4. Writes <artifact>.validation.json                         │
│    5. Exits nonzero on failure → Claude fixes and re-runs      │
│                                                                 │
│  No LLM calls — pure parsing + assertions                       │
└─────────────────────────────────────────────────────────────────┘
```

### Schema → validator mapping

| Schema | Validator | Key checks |
|--------|-----------|------------|
| `beat_board` | `validate_beat_board()` | 3+ beats, sequential, fields present, emotion vocab, sum check |
| `scenes` | `validate_scenes()` | Scene count, target sum, cast/location present, beat coverage |
| `spatial_plan` | `validate_spatial_plan()` | Landmark/zone uniqueness, panorama bounds, zone overlap, per-gen blocks, location_reference policy, generation_geography, position-in-zone, monotonic Z, no-teleport, shot coverage, facing/zoom vocabulary |
| `storyboard` | `validate_storyboard()` | Generation contiguity, 5-15s, shot contiguity, panels (6-12), transitions, shot_size, composition, new-information rule, no bridge generations |
| `prompts` | `validate_prompts()` | Char/location/object prompt files exist, sheet prompts per generation |
| `video_prompt` | `validate_video_prompt()` | 6 Ref2VA sections, shot timestamps match storyboard, no char_NN tokens, dialogue tags |
| `critique` | `validate_critique_report()` | All question IDs present, no FAIL, summary counts match |
| `spatial_qa` | `validate_spatial_qa_report()` | Per-sheet coverage, PASS/WARN status, summary counts match, WARN non-blocking |

---

## 11. Critique Subsystem (GATE 0)

```
┌─────────────────────────────────────────────────────────────────┐
│                    CRITIQUE FLOW (GATE 0)                       │
│                                                                 │
│  Agent 6 (Claude — LLM agent, not Python)                       │
│    │                                                            │
│    ├── Reads: developed_story.md                                │
│    ├── Reads: beat_board.md                                     │
│    ├── Reads: scenes.md                                         │
│    ├── Reads: all storyboard_sN.md                              │
│    ├── Reads: assets/directing-questions.md (200 questions)     │
│    │                                                            │
│    ├── Evaluates each question:                                 │
│    │   ├── Q1.1-Q1.30  (Story & Visual Storytelling)           │
│    │   ├── Q2.1-Q2.30  (Shot Design)                           │
│    │   ├── Q3.1-Q3.30  (Camera Movement)                       │
│    │   ├── Q4.1-Q4.30  (Composition)                           │
│    │   ├── Q5.1-Q5.30  (Editing & Cuts)                        │
│    │   ├── Q6.1-Q6.25  (Animation Direction)                   │
│    │   └── Q7.1-Q7.25  (Sound & Editing)                       │
│    │                                                            │
│    ├── Writes: critique_report.md                               │
│    │   (per question: Status: PASS/FAIL/ADVISORY + Notes)      │
│    │   (FAIL blocks include: Artifact + Fix)                    │
│    │                                                            │
│    └── Runs: validate --schema critique                         │
│        └── tools/critique_validator.py (deterministic)          │
│            ├── Checks: all 200 question IDs present             │
│            ├── Checks: no Status: FAIL remains                  │
│            └── Checks: summary counts match                     │
│                                                                 │
│  Fix loop:                                                      │
│    FAIL → director agent fixes artifact → re-validate           │
│        → re-critique → repeat until zero FAILs                  │
│                                                                 │
│  ═══ GATE 0 ═══  (blocks Stage B — no image spend until pass)  │
└─────────────────────────────────────────────────────────────────┘
```

### Question bank structure

`assets/directing-questions.md` — 200 questions across 7 sections:

| Section | Questions | Coverage |
|---------|-----------|----------|
| 1. Story & Visual Storytelling | 30 | Goals, conflict, stakes, arc, show-vs-tell, pacing |
| 2. Shot Design | 30 | Shot sizes, variety, establishing shots, reaction shots |
| 3. Camera Movement | 30 | Motivation, variety, Minimax vocabulary, static vs moving |
| 4. Composition | 30 | Subject clarity, 180° rule, leading lines, negative space |
| 5. Editing & Cuts | 30 | Motivated cuts, transition variety, generation continuity |
| 6. Animation Direction | 25 | Micro-beats, anticipation, follow-through, secondary motion |
| 7. Sound & Editing | 25 | Foley, ambient, impact, silence, music sync, dialogue |

---

## 12. Configuration

`config.py` — environment-driven configuration (loaded from repo-root `.env`):

| Setting | Default | Purpose |
|---------|---------|---------|
| `COMFYUI_URL` | `http://localhost:8188` | ComfyUI server for Minimax H3 |
| `COMFYUI_AUTH` | — | ComfyUI auth (if gated) |
| `FAL_KEY` | — | fal API key (alternative image backend) |
| `REPLICATE_API_TOKEN` | — | Replicate API key (primary image backend) |
| `PROVIDER` | `replicate` | Default image backend |
| `STORYBOARD_IMAGE_PROVIDER` | `replicate` | Storyboard sheet backend |
| `CHARACTER_SHEET_IMAGE_PROVIDER` | `replicate` | Character sheet backend |
| `GROK_REPLICATE_MODEL` | `openai/gpt-image-2` | Replicate model |
| `REPLICATE_SHEET_QUALITY` | `medium` | Sheet quality level |
| `REPLICATE_OUTPUT_FORMAT` | `webp` | Output format |
| `REPLICATE_OUTPUT_COMPRESSION` | `90` | webp compression |
| `CHARACTER_SHEET_SIZE` | `3840x2160` | Character sheet resolution (4K) |
| `STORYBOARD_SHEET_SIZE` | `3840x2160` | Storyboard sheet resolution (4K) |
| `MINIMAX_MEGAPIXELS` | `0.6` | Minimax render resolution |
| `MINIMAX_ASPECT` | `16:9` | Minimax render aspect ratio |
| `IMAGE_REF_LIMIT` | — | Override max reference images (default: provider-specific) |

### Reference image limits (per provider/model)

| Provider/Model | Max refs |
|----------------|----------|
| Replicate gpt-image-2 | 13 |
| Replicate Seedream | 10 |
| Replicate legacy Grok | 1 |
| fal gpt-image-2 | 13 |
| fal legacy Grok | 3 |

Application-level cap: **10 refs** (the agent may name up to 10 in `ref_images:`).

---

## 13. File Map

```
skills/story-maker-v3/
│
├── SKILL.md                          ← Main runbook (the source of truth)
├── config.py                         ← Environment-driven configuration
├── requirements.txt                  ← Python deps (replicate, fal-client, httpx, Pillow, numpy)
│
├── prompts/                          ← Agent instructions (Claude reads these)
│   ├── story_developer.md            ← Agent 1: develop the story
│   ├── beat_board.md                 ← Agent 1b: extract the beat board
│   ├── scene_writer.md               ← Agent 2: break into scenes
│   ├── storyboard_planner.md         ← Agent 3: storyboard each scene (the Director)
│   ├── image_prompter.md             ← Agent 4: author image prompts
│   ├── critique_agent.md             ← Agent 6: evaluate against 200+ questions
│   ├── video_prompter.md             ← Agent 5: author Ref2VA video prompts
│   ├── character_sheet_template.md   ← Character sheet prompt template
│   ├── location_sheet_template.md    ← Location lock prompt template (360°)
│   ├── object_sheet_template.md      ← Object sheet prompt template
│   └── storyboard_sheet_template.md  ← Storyboard sheet prompt template
│
├── assets/                           ← Reference documents (agents read these)
│   ├── directors-guide.md            ← 7-section directing cheat sheet
│   ├── directing-questions.md        ← 200+ question bank for critique
│   └── minimax-h3-prompt-bible.md    ← Minimax H3 vocabulary + Ref2VA spec
│
├── tools/                            ← Python modules (the "hands")
│   ├── validators.py                 ← Deterministic artifact validators
│   ├── critique_validator.py         ← Critique report parser + validator
│   ├── image_pipeline.py             ← Asset registry + sheet generation
│   ├── char_sheet_builder.py         ← Character sheet prompt builder
│   ├── location_sheet_builder.py     ← Location lock prompt builder
│   ├── object_sheet_builder.py       ← Object sheet prompt builder
│   ├── grok_tools.py                 ← Image generation dispatcher
│   ├── grok_replicate.py             ← Replicate image backend
│   ├── grok_fal.py                   ← fal image backend
│   ├── grok_image_common.py          ← Shared image utilities
│   ├── minimax_workflow.py           ← ComfyUI Minimax H3 workflow loader
│   ├── comfyui_tools.py              ← ComfyUI API client
│   ├── video_concat.py               ← ffmpeg concat
│   ├── video_frames.py               ← ffmpeg frame extraction
│   ├── duration_budget.py            ← Timing math (scene/gen/shot budgets)
│   └── seam_report.py                ← Seam jump quantification
│
├── scripts/                          ← CLI entry points
│   ├── validate.py                   ← Artifact validator CLI
│   ├── build_images.py               ← Image generation CLI
│   └── render_all.py                 ← Video render CLI (sequential + concat)
│
└── tests/
    └── test_phase2.py                ← 84 unit tests
```

---

## 14. Data Flow Diagrams

### Stage A → A-QA → B (planning to first image)

```
User story file
     │
     ▼
[Agent 1] ──▶ developed_story.md
     │           (Characters, Locations, Objects)
     ▼
[Agent 1b] ─▶ beat_board.md ──▶ validate --schema beat_board
     │           (8-15 beats: description + emotion + timing)
     ▼
[Agent 2] ─▶ scenes.md ──────▶ validate --schema scenes
     │           (N scenes: cast + location + objects + beats)
     ▼
[Agent 3] ─▶ storyboard_sN.md ▶ validate --schema storyboard  (per scene)
     │           (generations gK → shots)
     ▼
[Agent 4] ─▶ image_prompts/ ──▶ validate --schema prompts     (per scene)
     │           (char/loc/obj/sheet prompts + ref_images:)
     ▼
[Agent 6] ─▶ critique_report.md ▶ validate --schema critique
     │           (200 questions: PASS/FAIL/ADVISORY)
     │
     ═══ GATE 0 ═══ (zero FAILs required)
     │
     ▼
[Python]  ─▶ assets/*.webp ──── build_images.py --assets-only
     │           (4K characters, locations, objects — shared, resume-safe)
     ▼
[Python]  ─▶ storyboard_sheet_sN_gK.webp ── build_images.py --scene sN
     │           (4K panel grid, location → prev sheet → chars → named refs)
     ▼
     ═══ GATE 1 ═══ (user visually confirms sheets)
```

### Stage C → D (vision to final film)

```
storyboard_sheet_sN_gK.webp (image)
     │
     ▼
[Agent 5]  (vision: reads sheet image)
     │  + storyboard_sN.md
     │  + minimax-h3-prompt-bible.md
     ▼
video_prompts/sN_gK.txt ──▶ validate --schema video_prompt
     │           (6-section Ref2VA: subject_definitions, summary,
     │            retention_analysis, detailed_description,
     │            overall_soundscape, non_diegetic_music)
     │
     ═══ GATE 2 ═══ (user confirms before paid render)
     │
     ▼
[Python]  render_all.py
     │
     ├── Sequential: clips/sN/gK.mp4
     │   └── Minimax H3 R2V (sheet = ref image, video prompt = timeline)
     │       (≤15s, native stereo audio, 1056×608 default)
     │       (gK+1 conditioned on gK's rendered tail via ref_videos)
     │
     ├── Extract: 3s tail of gK after render (ffmpeg)
     │
     └── Concat:
         ├── scene_sN.mp4  (g1, g2, g3, ...)
         └── final_film.mp4  (all scenes, audio preserved)
```

### Cross-episode asset reuse

```
Episode 1:
  [Agent 1] → developed_story.md (Tom, Jerry, kitchen, hall)
  [Agent 4] → image_prompts/characters/char_tom.txt
              image_prompts/characters/char_jerry.txt
              image_prompts/locations/loc_kitchen.txt
  [Python]  → assets/characters/char_tom.webp     (4K, generated)
              assets/characters/char_jerry.webp    (4K, generated)
              assets/locations/loc_kitchen.webp    (4K, generated)
              asset_registry.json                  (updated with all 3)

Episode 2:
  [Agent 1] → developed_story.md (Tom, Jerry, kitchen, hall, Spike)
  [Agent 4] reads asset_registry.json
              → char_tom EXISTS → skip
              → char_jerry EXISTS → skip
              → loc_kitchen EXISTS → skip
              → char_spike NEW → generate
              → loc_hall NEW → generate
              → loc_hall prompt includes: ref_images: loc_kitchen
                 (attach kitchen as visual reference for the new hall)
  [Python]  → assets/characters/char_spike.webp   (4K, generated)
              assets/locations/loc_hall.webp       (4K, generated with kitchen ref)
              asset_registry.json                  (updated with 2 new entries)
```
