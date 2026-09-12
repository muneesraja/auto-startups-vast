# Story Maker V5 — Canonical End-to-End Generation Example

> **Purpose:** This document provides a complete, production-grade, end-to-end reference walkthrough of how a story moves through the Story Maker V5 architecture. It details every artifact generated at each stage, explicitly identifies the AI models employed, explains how our **15-second generation limitation** is engineered into cohesive multi-minute stories, and documents exact prompt structures for characters, locations, objects, storyboard sheets, and video generations with canonical Ref2VA token bindings and dynamic 1-to-8 shot pacing.
>
> **Canonical story:** every artifact below is drawn from the same worked example — **"Ollie's Dive"** (adapted from the *Swapped* opening sequence analyzed in `Research/ollie/`). The compact cross-artifact reference lives in [`assets/example-ollie.md`](assets/example-ollie.md); this document is the long-form version. All agent prompts cite these same IDs (`char_01`, `loc_01`, `obj_01`, scene `s1`, generation `s1/g2`) so examples stay consistent across agents.

---

## 1. AI Model Infrastructure & Target Matrix

Every generative step in Story Maker V5 targets a specific, calibrated model backend. Python executes deterministic API calls; Claude Code authors and validates all prompt and structural specifications.

| Generative Task | Primary Production Model | Execution Engine | Resolution / Specs | Format & Notes |
|---|---|---|---|---|
| **Character Sheet (Turnaround)** | **OpenAI GPT-Image-2** (`openai/gpt-image-2.5-sunburst` or `openai/gpt-image-2`) | Replicate / fal API | 3840×2160 (4K UHD) | WebP, quality 90, neutral background, front/side/3-quarter + expression grid |
| **Location Lock (Persistent Environment)** | **OpenAI GPT-Image-2** | Replicate / fal API | 3840×2160 (4K UHD) | WebP, quality 90, wide establishing plate, persistent architecture, zero characters |
| **Hero Object / Prop Sheet** | **OpenAI GPT-Image-2** | Replicate / fal API | 3840×2160 (4K UHD) | WebP, quality 90, multiple angles/states, isolated clean plate |
| **Storyboard Sheet (Grid)** | **OpenAI GPT-Image-2** | Replicate / fal API | 3840×2160 (4K UHD) | WebP, quality 90, 6-panel (`3x2`) default/min to 9-panel (`3x3`) max grid, 4px thin gutters, text-free |
| **Video Generation (from Storyboard)** | **Minimax Hailuo H3 R2V** (`ref2va` pipeline) | ComfyUI API / Cloud (Vast.ai) | 1056×608 (0.6MP 16:9, snapped to 32px multiples) | 25 fps, native stereo audio, Ref2VA UNet + Video/Audio VAEs + Qwen3VL CLIP |
| **Video Continuation (Tail Conditioning)** | **Minimax Hailuo H3 R2V** | ComfyUI API / Cloud | 1056×608, 25 fps | Conditioned on 3.0s tail of previous generation via `ref_videos` input node |
| **Alternative Local Video Backend** | **Wan 2.2 / LTX-Video 2.3** | ComfyUI API (Vast.ai) | 1280×720 or 1056×608 | Keyframe / I2V workflow with prompt relay |
| **Audio Synthesis & Foley** | **Minimax H3 Native Audio** | Native inside H3 R2V | 48kHz Stereo | Synthesized directly from video prompt audio/foley lines |
| **Editorial Assembly & Concat** | **ffmpeg** | Local CLI | Match source stream | Stream copy (`-c copy`) or re-mux with audio normalization |

---

## 2. Engineering Around the 15-Second Video Constraint

### The Challenge
Diffusion-based video models with high temporal coherence, such as **Minimax Hailuo H3 R2V**, enforce a hard cap of **15 seconds** (or 375 frames at 25 fps) per generation pass. Attempting to render longer durations in a single pass leads to catastrophic memory consumption, hallucinated physics, and temporal drift.

### The Story Maker V5 Solution
Story Maker V5 achieves continuous 1-minute, 3-minute, or 5-minute films through four coordinated architectural pillars:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               15-SECOND CONTINUITY PIPELINE                                      │
│                                                                                                  │
│   Scene s1 (45s Target)                                                                          │
│   ├── Generation g1 (0.0s – 15.0s)                                                               │
│   │   ├── Conditioned on: storyboard_sheet_s1_g1.webp (GPT-Image-2)                              │
│   │   ├── Rendered via: Minimax H3 R2V → clips/s1/g1.mp4                                         │
│   │   └── Tail Extraction: ffmpeg extracts last 3.0s (12.0s–15.0s) → clips/s1/g1_tail.mp4        │
│   │                                                                                              │
│   ├── Generation g2 (15.0s – 30.0s)                                                              │
│   │   ├── Conditioned on: storyboard_sheet_s1_g2.webp + ref_videos: [clips/s1/g1_tail.mp4]       │
│   │   ├── Rendered via: Minimax H3 R2V (seamless physics & lighting continuation)                │
│   │   └── Tail Extraction: ffmpeg extracts last 3.0s (27.0s–30.0s) → clips/s1/g2_tail.mp4        │
│   │                                                                                              │
│   └── Generation g3 (30.0s – 45.0s) [conditioned on g2_tail.mp4]                                │
│                                                                                                  │
│   Final Concat: ffmpeg concats g1 + g2 + g3 → scene_s1.mp4                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Scene-to-Generation Budgeting**:
   - Every scene in `scenes.md` is partitioned into discrete generations of **5.0 to 15.0 seconds** (`g1`, `g2`, `g3`, etc.).
   - Shorter transitional scenes (e.g. 8–12s) occupy a single generation. Longer dramatic sequences (e.g. 45s) split into 3 balanced 15s generations.
   - **Hard Rule**: A cinematic shot never crosses a generation boundary. Cuts snap cleanly to generation edges.

2. **Dynamic Pacing & Visual Economy (1–8 Shots per Generation)**:
   - Within each 15-second generation, the narrative dynamically selects between **1 and 8 distinct shots** depending on scene tempo.
   - For rapid comedic action or montage, use 6–8 snappy shots (1.5–2.5s each).
   - For unbroken beats, use a **1-shot master take (oner)** — the sheet's panels become temporal milestones of the take.
   - For contemplative, emotional, or slow-paced scenes with only 1–2 shots, prompt detail is dramatically amplified (multi-phase micro-beats, living atmosphere, evolving camera) to prevent the 15 seconds from feeling static or boring.

3. **Keyframe-to-Panel Staging (3x2 Default to 3x3 Max)**:
   - Each 15s generation is anchored by **one storyboard sheet** featuring a **6-panel (`3x2` default/min)** to **9-panel (`3x3` max)** regular grid.
   - Every panel maps to visual keyframes that guide Minimax H3's camera moves, actor poses, lighting shifts, and spatial blocking.

4. **Dynamic Tail Conditioning (`ref_videos`)**:
   - Immediately after `g1.mp4` finishes rendering, Python invokes `ffmpeg` to extract the final 3.0 seconds (`clips/s1/g1_tail.mp4`).
   - For `g2.mp4`, the ComfyUI workflow dynamically patches `g1_tail.mp4` into Minimax's `ref_videos` input.
   - The model uses the tail's ending frame, lighting, character momentum, and motion vectors as the initial condition for `g2`, eliminating jarring jump-cuts and maintaining unbroken emotional immersion.
   - A `hard_cut` boundary opens fresh — no tail is attached and `<Video 1>` is not declared (see `tools/boundary.py`).

---

## 3. End-to-End Artifact Showcase: "Ollie's Dive — The Idea"

Below is the complete, concrete realization of **Scene s1 (45 seconds total)** from *Ollie's Dive*, with Generation `g2` (15.0s–30.0s, the canonical 1-shot oner) shown in full.

---

### Step 1: Developed Story Screenplay (`developed_story.md`)
*Authored by Agent 1 (Story Developer) following the v5.0.0 Animation Screenplay Standard.*

```markdown
# OLLIE'S DIVE

Episode: epi-1
Working Title: The Idea
Target Delivery: 45 seconds (Scene s1)

---

EXT. SUNLIT POND - DAY

Sunlight filters through wild clover and giant orange gerberas.

YOUNG OLLIE (5), a fuzzy Pookoo with wild spiky fur and massive green
eyes, sits on a mossy boulder, cradling a homemade bark basket adorned
with a spiral seashell and pink blossoms. He beams.

A glowing GREEN DRAGONFLY darts past his ears. Ollie turns abruptly.
His hind foot SLIPS.

The basket tips. SPLASH! It hits the water, dumping the shell and
flowers into the shallows.

Ollie gasps, dropping to his stomach at the water's edge. The empty
wooden cylinder bobs in the crystal-clear shallows.

OLLIE'S POV - THROUGH THE CYLINDER

Underwater light dances across river stones and swaying water-weeds —
an entirely different universe.

BACK TO SHORE

Ollie's eyes widen. A lightbulb goes off.

---

## Characters

### char_01 — Young Ollie
- **Role**: Protagonist
- **Species**: Pookoo (otter-like woodland creature), 5 years old
- **Appearance**: Fluffy chocolate-brown fur, spiky russet hair tuft, oversized black button nose, cream muzzle, huge emerald-green eyes.
- **Wardrobe**: None — bare fur.
- **Dramaturgical Function**: Vulnerable, curious, inventive, highly expressive physical comedy.

### char_02 — Caloo
- **Role**: Ollie's father
- **Species**: Adult Pookoo
- **Appearance**: Large shaggy auburn fur, broad paws, weathered whiskers, tired overprotective eyes.
- **Dramaturgical Function**: Off-screen presence in s1; rescuer and comic foil in s3.

---

## Locations

### loc_01 — Sunlit Pond Edge
- **Description**: Lush meadow shoreline. Flat mossy stone ledge at the waterline, clover patches, giant orange gerberas, glassy pond surface reflecting golden light. Warm, safe, inviting.

### loc_02 — Underwater Valley
- **Description**: Crystalline aquamarine water, mossy stone terraces, bioluminescent flora, cathedral light beams. Alien, vast, wondrous — and hiding the Giant Valley Fish.

---

## Objects

### obj_01 — Handmade Basket
- **Description**: Woven bark basket holding a spiral seashell and pink blossoms. Rough bark weave, glossy shell, bright petals. Sinks into the pond in s1 and is never carried underwater.

### obj_02 — Makeshift Diving Helmet
- **Description**: Hollowed wooden cylinder with a polished pebble faceplate, amber sap seals, and a woven leaf strap. Hero prop built across s1's prototype montage.

### obj_03 — Reed Snorkel
- **Description**: Long hollow plant stem lashed to the helmet, tipped with a buoyant bark-disc float that keeps it upright at the surface.
```

---

### Step 2: Beat Board (`beat_board.md`)
*Authored by Agent 1b (Beat Board Architect).*

```markdown
# Beat Board — Ollie's Dive
target_seconds: 224
scene_budget: 70

## Beat 1 — Pride
description: Ollie admires his handmade basket on the mossy boulder, beaming.
emotion: joy
estimated_seconds: 15

## Beat 2 — Spill
description: A dragonfly startles Ollie; the basket tumbles into the pond.
emotion: shock
estimated_seconds: 15

## Beat 3 — Discovery
description: Peering through the hollow cylinder, Ollie glimpses the glowing underwater world — an idea ignites.
emotion: wonder
estimated_seconds: 15

## Beat 4 — Trial and Error
description: Three helmet prototypes fail — no seal, no air, a flooding snorkel.
emotion: tension
estimated_seconds: 45
```

*(Beats 5–9 — Breakthrough, Wonder, Peril, Rescue, Button — continue in [`assets/example-ollie.md`](assets/example-ollie.md) §2.)*

---

### Step 3: Scenes Specification (`scenes.md`)
*Authored by Agent 2 (Scene Writer).*

```markdown
# Scenes
target_seconds: 224
scene_budget: 70

## Scene s1 — The Idea
scene_id: s1
target_seconds: 45
cast: [char_01]
characters_present: [char_01]
location_id: loc_01
objects: [obj_01, obj_02]
beats: [1, 2, 3]
style_target: high-fidelity stylized 3D CGI animation with tactile physical shaders and subsurface scattering
acting_beat: proud stillness → startled lurch → wide-eyed wonder
layout_strategy: boulder and basket foreground-right, pond opening midground-left, eye path follows the basket's fall into the water
visual_motif: round openings — basket mouth, cylinder rim, pond surface — each a portal that grows in meaning
sound_world: meadow birds, gentle water lap, whimsical acoustic strings
beat: A spilled basket reveals an underwater world to a young inventor.

### Scene-End Handoff -> Scene s2
on_screen: [char_01]
mood: wonder
transition: hard_cut
```

---

### Step 4: Spatial Plan (`spatial_plan_s1.md`)
*Authored by Agent 3a (Spatial Architect).*

```markdown
# Spatial Plan — Scene s1
scene_id: s1
location_ref_id: loc_01
panorama_resolution: 3840x2160
world_axis: pond on screen-left, meadow bank rising to screen-right
primary_anchor: rock_ledge
landmarks: [mossy_boulder, rock_ledge, waterline, gerbera_clump]
zones: [bank, ledge, shallows]

## Landmark rock_ledge
zone: ledge
description: flat stone ledge at the water's edge where the basket sat
panorama_xy: [1600, 1500]

## Landmark mossy_boulder
zone: bank
description: large moss-covered boulder where Ollie first sits with the basket
panorama_xy: [2900, 1400]

## Landmark waterline
zone: shallows
description: glassy pond surface meeting the ledge
panorama_xy: [900, 1600]

## Landmark gerbera_clump
zone: bank
description: cluster of giant orange gerberas framing the bank
panorama_xy: [3400, 900]

## Zone bank
relative_to: rock_ledge
x_range: [2100, 3840]
y_range: [600, 2160]
z_range: [3, 25]
distance_from_anchor_m: 8
lighting: warm golden sun from screen-left

## Zone ledge
relative_to: rock_ledge
x_range: [1100, 2100]
y_range: [1200, 2160]
z_range: [0, 3]
distance_from_anchor_m: 0
lighting: warm golden sun from screen-left

## Zone shallows
relative_to: waterline
x_range: [0, 1100]
y_range: [1200, 2160]
z_range: [0, 4]
distance_from_anchor_m: 2
lighting: bright water sparkle, refracted golden light

## Generation g1
location_reference: attach
generation_geography: wide view from the meadow bank showing Ollie on the mossy boulder, the ledge, and the glassy pond beyond
start_positions: char_01=bank@x=2900,y=1500,z=8m
end_positions: char_01=ledge@x=1500,y=1600,z=1m
movement_constraints: char_01=approach(rock_ledge)

### Shot 1
on_screen_positions: char_01=bank@x=2900,y=1500,z=8m:midground
camera_zone: bank
camera_facing: toward_waterline
camera_zoom: medium_closeup
character_facing: char_01=toward_camera
visible_landmarks: [mossy_boulder, gerbera_clump]

## Generation g2
location_reference: omit
generation_geography: Ollie prone on the rock ledge at the waterline, peering through the hollow cylinder toward the pond
start_positions: char_01=ledge@x=1500,y=1600,z=1m
end_positions: char_01=ledge@x=1550,y=1600,z=1m
movement_constraints: char_01=fixed_at(rock_ledge)

### Shot 1
on_screen_positions: char_01=ledge@x=1520,y=1600,z=1m:foreground
camera_zone: ledge
camera_facing: toward_waterline
camera_zoom: closeup
character_facing: char_01=toward_waterline
visible_landmarks: [rock_ledge, waterline]
```

---

### Step 5: Character Sheet Prompts (`image_prompts/characters/`)
*Target Model: **OpenAI GPT-Image-2** (3840×2160, WebP, quality=medium)*

#### `image_prompts/characters/char_01.txt`
```text
A clean character identity turnaround sheet of a small young Pookoo, an otter-like woodland creature, 5 years old, named Ollie. Fluffy chocolate-brown fur with soft visible strands, a spiky russet hair tuft on his crown, an oversized black button nose, a cream-colored muzzle and belly, and huge expressive emerald-green eyes with rounded pupils. Stubby rounded paws, short limbs, oversized head, childlike proportions. Full body turnaround displayed in front, three-quarter, and profile poses on a neutral light-gray background. Bottom half features a head-and-shoulders expression grid: proud beam, startled gasp, curious squint, wide-eyed wonder, and a sheepish toothy grin. High-fidelity stylized 3D CGI feature animation style. Subsurface scattering on fur, clean anatomical proportions, consistent design across all poses. No text, no labels, no captions, no numbers, no watermarks.
```

#### `image_prompts/characters/char_02.txt`
```text
A clean character identity turnaround sheet of a large adult Pookoo, an otter-like woodland creature, named Caloo. Shaggy auburn-brown fur with a heavier, weathered coat, broad shoulders, large paws, long whiskers, a cream-colored chest patch, and tired, warm, overprotective eyes under heavy brows. Stocky adult proportions — roughly three times Ollie's height. Full body turnaround displayed in front, three-quarter, and side views against a neutral light-gray studio backdrop. Lower strip features facial expressions: stern glare, exasperated sigh, softening smile, and alarmed wide-eyed lunge. Feature-film 3D animation aesthetic, soft tactile fur specular reflections. No text, no labels, no captions, no numbers, no watermarks.
```

---

### Step 6: Location & Object Prompts (`image_prompts/locations/` and `objects/`)
*Target Model: **OpenAI GPT-Image-2** (3840×2160, WebP, quality=medium)*

#### `image_prompts/locations/loc_01.txt`
```text
An empty, sun-drenched pond-edge establishing plate at golden hour. A flat mossy stone ledge juts into a glassy, crystal-clear pond on the left side of frame, surrounded by clover patches and giant orange gerberas. A large moss-covered boulder sits on the rising meadow bank to the right. Wild grasses and overhanging leaves frame the top of the composition. Warm volumetric sunlight streams from screen-left, sparkling on the water surface and casting long soft shadows. Warm amber, moss green, and soft gold tones. High-fidelity stylized 3D CGI feature animation cinematic set plate. Completely empty stage — no characters, no animals. No text, no labels, no watermarks, no frame borders.
```

#### `image_prompts/objects/obj_02.txt`
```text
A clean hero object reference sheet for a makeshift diving helmet built by a small woodland creature. The helmet is a hollowed weathered wooden cylinder sized to fit a small creature's head, with a polished round pebble set as a faceplate, seams sealed with glossy amber tree sap, and a woven leaf strap for securing it under the chin. Warm bark texture with visible carved tool marks. Shown in multiple states against a neutral backdrop: Left: the bare hollow cylinder, freshly found. Center: the cylinder with pebble faceplate and sap seals applied. Right: the completed helmet with leaf strap and lashed reed snorkel topped by a buoyant bark-disc float. High-fidelity stylized 3D CGI render, crisp studio lighting, tactile material detail. No text, no labels, no captions, no watermarks.
```

---

### Step 7: Storyboard Sheet Prompt (`image_prompts/s1/storyboard_sheet_g2.txt`)
*Target Model: **OpenAI GPT-Image-2** (3840×2160, WebP, quality=medium)*
*Grid: **6-panel 2x3 regular grid** — one continuous master take (oner) distributed as temporal milestones.*

```text
ref_images: loc_01, char_01, obj_02

Create one text-free cinematic pre-production storyboard sheet containing exactly six panels arranged in two rows and three columns (2x3 grid). Time flows column-major: read down Column 1 (Panels 1, 2), down Column 2 (Panels 3, 4), then down Column 3 (Panels 5, 6).

CANVAS AND GRID
Canvas: 3840 pixels wide by 2160 pixels tall.
Use a regular grid of six equal panels separated by crisp, uniform black divider lines exactly four pixels wide.
No outer borders, no rounded corners, no decorative elements, no overlapping cells.
ABSOLUTELY TEXT-FREE: No numbers, no panel labels, no timecodes, no dialogue text, no captions, no watermarks.

REFERENCE PRIORITY
1. Match the attached character sheet for char_01 (Ollie): fluffy chocolate-brown fur, russet tuft, oversized black button nose, huge emerald-green eyes.
2. Match the attached location reference loc_01: flat mossy ledge, clover, orange gerberas, glassy pond.
3. Match obj_02: the hollow weathered wooden cylinder (helmet base).
Maintain persistent 3D set geography across all six views.

SPATIAL CONTINUITY BIBLE
The pond sits screen-left; the meadow bank rises screen-right.
The flat rock ledge meets the waterline in a clean horizontal band.
Ollie is prone on the ledge throughout — this is ONE unbroken take, not six separate setups.

PANEL DIRECTIONS (6 PANELS — temporal milestones of one continuous take)

Column 1 — The Approach (15.0s – 20.0s)
Panel 1 (Top-Left): Low camera at the waterline. Ollie lies prone on the flat stone ledge, chocolate-brown fur sunlit, the hollow wooden cylinder resting beside his paws. The glassy pond fills the left half of frame.
Panel 2 (Bottom-Left): Same camera position: Ollie's paws lift the cylinder toward his face, its dark circular opening tilting toward camera.

Column 2 — The Peek (20.0s – 25.0s)
Panel 3 (Top-Center): Three-quarter view at Ollie's chest height. Ollie holds the cylinder to his eye, rim catching warm light — frame-within-frame through its dark opening.
Panel 4 (Bottom-Center): Tight close-up. Ollie peers through the tube; his emerald eyes widen, catching the refracted aquamarine shimmer.

Column 3 — The Idea (25.0s – 30.0s)
Panel 5 (Top-Right): Chest-height three-quarter angle. Ollie holds the cylinder up proudly; the lightbulb moment ignites on his face.
Panel 6 (Bottom-Right): Slightly wider medium composition. Ollie sits on the sunlit ledge grinning, cylinder in paw, ledge and waterline leading the eye to him. Warm, complete, resolved.

HARD EXCLUSIONS
No other characters, no underwater interiors, no text overlays, no dialogue bubbles, no split-screen cells within a panel.
```

---

### Step 8: Video Generation Prompt (`video_prompts/s1_g2.txt`)
*Target Model: **Minimax Hailuo H3 R2V** (ComfyUI Ref2VA workflow)*
*Duration: **15.0 seconds** | Resolution: **1056×608 (0.6MP)** | Audio: **Native Stereo***

```text
subject_definitions:
<Subject 1> is Young Ollie in <Picture 1>, a small otter-like Pookoo with fluffy chocolate-brown fur, a spiky russet hair tuft, an oversized black button nose, a cream muzzle, and huge emerald-green eyes.
<Picture 1> is the storyboard reference for [Shot 1], defining viewpoint, subject placement, and the take's progression.
<Video 1> is the previous generation's rendered tail and continuation starting point.
(S1) is <Subject 1>'s voice.

summary:
[video continuation + reference generation] The video seamlessly continues from <Video 1> as Ollie peers through the hollow cylinder and discovers the underwater world.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - fur, tuft, nose, muzzle, and eyes retained.
<Picture 1> (storyboard reference): fully_preserved - composition, lighting, and panel sequence.
<Video 1> (continuation starting point): fully_preserved - ending pose, staging, lighting, and motion state.

detailed_description:
High-fidelity stylized 3D CGI animation, warm sunlit meadow light, tactile fur shaders.
[Shot 1] Continuing seamlessly from <Video 1>, <Subject 1> lies prone on the flat stone ledge at the water's edge, matching the previous clip's ending pose and low camera height. He lifts the hollow wooden cylinder to his eye and peers through: shimmering aquamarine light, swaying water-weeds, drifting motes. His emerald eyes widen slowly, then spark — a grinning lightbulb moment, ears perking. The camera pushes in with small amplitude at slow speed toward the cylinder's dark opening. <Subject 1> (S1) gives a soft contented sniff, then a tiny gasp inside the tube, <d>[English] <gasp> Ooh... </d> Never generate duplicate characters or extra limbs.

overall_soundscape:
Muffled underwater hum resonating through the wooden tube, gentle water lapping against the ledge, distant meadow birds.

non_diegetic_music:
A single inquisitive celesta phrase over soft sustained strings.
```

---

### Step 9: Tail Continuation for Generation 3 (`video_prompts/s1_g3.txt`)
*Demonstrating how the 15-second boundary is crossed seamlessly with canonical Ref2VA tail conditioning.*

```text
subject_definitions:
<Subject 1> is Young Ollie in <Picture 1>, a small otter-like Pookoo with fluffy chocolate-brown fur and huge emerald-green eyes, continuing from <Video 1>.
<Subject 2> is the makeshift diving helmet in <Picture 1>, a hollow wooden cylinder with a polished pebble faceplate and woven leaf strap.
<Picture 1> is the 6-panel 3x2 storyboard sheet for generation 3 (storyboard_sheet_s1_g3.webp).
<Video 1> is the 3.0-second tail clip clips/s1/g2_tail.mp4 from the end of generation 2.

summary:
[video continuation + reference generation] The video seamlessly continues from <Video 1> as Ollie presses the cylinder over his head and dunks underwater — then sputters back up, soaked.

retention_analysis:
<Subject 1> (appears in [Shot 1]–[Shot 4]): fully_preserved - fur, tuft, nose, muzzle, and eyes retained.
<Subject 2> (appears in [Shot 1]–[Shot 4]): fully_preserved - cylinder form, pebble faceplate, leaf strap retained.
<Picture 1> (storyboard reference): fully_preserved - composition, lighting, and panel sequence.
<Video 1> (continuation starting point): fully_preserved - ending pose, staging, lighting, and motion state.

detailed_description:
High-fidelity stylized 3D CGI animation, warm sunlit meadow light, tactile fur shaders.
[Shot 1] Continuing seamlessly from <Video 1>, <Subject 1> lifts <Subject 2> over his head and pulls it down snug, pebble faceplate over his eyes...
```

---

### Step 10: Render Manifest & Verification (`render_manifest.json`)
*Generated deterministically by `scripts/build_manifest.py` to guarantee zero-tamper reproducible pipeline execution.*

```json
{
  "manifest_version": "1.0",
  "story": "ollies-dive",
  "episode": "epi-1",
  "target_duration_seconds": 45.0,
  "created_at": "2026-09-10T18:00:00Z",
  "models": {
    "image_backend": "openai/gpt-image-2",
    "video_backend": "minimax-h3-r2v",
    "concat_engine": "ffmpeg-7.0"
  },
  "asset_hashes": {
    "assets/characters/char_01.webp": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "assets/characters/char_02.webp": "sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    "assets/locations/loc_01.webp": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "sheets/storyboard_sheet_s1_g2.webp": "sha256:77963b7a931377ad4ab5ad6a9cd718aa5b2046e3ac563399da94e4bc66b48a20"
  },
  "generations": [
    {
      "id": "s1_g1",
      "scene_id": "s1",
      "duration_seconds": 15.0,
      "panel_grid": "3x3",
      "total_panels": 9,
      "total_shots": 6,
      "sheet_prompt": "image_prompts/s1/storyboard_sheet_g1.txt",
      "video_prompt": "video_prompts/s1_g1.txt",
      "tail_condition": null,
      "output_clip": "clips/s1/g1.mp4",
      "tail_extracted": "clips/s1/g1_tail.mp4",
      "validation_status": "PASS"
    },
    {
      "id": "s1_g2",
      "scene_id": "s1",
      "duration_seconds": 15.0,
      "panel_grid": "2x3",
      "total_panels": 6,
      "total_shots": 1,
      "sheet_prompt": "image_prompts/s1/storyboard_sheet_g2.txt",
      "video_prompt": "video_prompts/s1_g2.txt",
      "tail_condition": "clips/s1/g1_tail.mp4",
      "output_clip": "clips/s1/g2.mp4",
      "tail_extracted": "clips/s1/g2_tail.mp4",
      "validation_status": "PASS"
    }
  ],
  "gates": {
    "gate_0_critique": "PASSED (0 BLOCKERs, 2 MAJOR disposed)",
    "gate_1_sheets": "APPROVED_BY_USER",
    "gate_2_prompts": "APPROVED_BY_USER"
  }
}
```

---

## 4. Summary Checklist for Any Generation Run

When preparing or validating any Story Maker V5 run, ensure:
1. **Grid Selected Appropriately**:
   - `3x2` / `2x3` (6 panels) for standard 8–15s generations (default) and oners.
   - `3x3` (9 panels) for dense, rapid-cut 13–15s action generations.
2. **Shot-to-Panel Ratio**: Every panel belongs to exactly one shot. No shot spans across generation boundaries.
3. **Model Specifications Quoted**: All still prompts target **OpenAI GPT-Image-2** (3840×2160, WebP); video prompts target **Minimax Hailuo H3 R2V** (1056×608, 25fps, native stereo).
4. **Tail Continuity Configured**: Every non-`hard_cut` generation after the episode's first declares `<Video 1>` and gets `ref_videos: [previous_tail.mp4]`.
5. **No Text in Still Images**: Character, location, object, and storyboard prompts must explicitly forbid text, labels, numbers, captions, and watermarks.
