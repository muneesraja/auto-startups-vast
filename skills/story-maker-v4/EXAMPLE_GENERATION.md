# Story Maker V4 — Canonical End-to-End Generation Example

> **Purpose:** This document provides a complete, production-grade, end-to-end reference walkthrough of how a story moves through the Story Maker V4 architecture. It details every artifact generated at each stage, explicitly identifies the AI models employed, explains how our **15-second generation limitation** is engineered into cohesive multi-minute stories, and documents exact prompt structures for characters, locations, objects, storyboard sheets, and video generations.

---

## 1. AI Model Infrastructure & Target Matrix

Every generative step in Story Maker V4 targets a specific, calibrated model backend. Python executes deterministic API calls; Claude Code authors and validates all prompt and structural specifications.

| Generative Task | Primary Production Model | Execution Engine | Resolution / Specs | Format & Notes |
|---|---|---|---|---|
| **Character Sheet (Turnaround)** | **OpenAI GPT-Image-2** (`openai/gpt-image-2.5-sunburst` or `openai/gpt-image-2`) | Replicate / fal API | 3840×2160 (4K UHD) | WebP, quality 90, neutral background, front/side/3-quarter + expression grid |
| **Location Lock (Persistent Environment)** | **OpenAI GPT-Image-2** | Replicate / fal API | 3840×2160 (4K UHD) | WebP, quality 90, wide establishing plate, persistent architecture, zero characters |
| **Hero Object / Prop Sheet** | **OpenAI GPT-Image-2** | Replicate / fal API | 3840×2160 (4K UHD) | WebP, quality 90, multiple angles/states, isolated clean plate |
| **Storyboard Sheet (Grid)** | **OpenAI GPT-Image-2** | Replicate / fal API | 3840×2160 (4K UHD) | WebP, quality 90, 6-panel (`3x2`) or 9-panel (`3x3`) regular grid, 4px thin gutters, text-free |
| **Video Generation (from Storyboard)** | **Minimax Hailuo H3 R2V** (`ref2va` pipeline) | ComfyUI API / Cloud (Vast.ai) | 1056×608 (0.6MP 16:9, snapped to 32px multiples) | 25 fps, native stereo audio, Ref2VA UNet + Video/Audio VAEs + Qwen3VL CLIP |
| **Video Continuation (Tail Conditioning)** | **Minimax Hailuo H3 R2V** | ComfyUI API / Cloud | 1056×608, 25 fps | Conditioned on 3.0s tail of previous generation via `ref_videos` input node |
| **Alternative Local Video Backend** | **Wan 2.2 / LTX-Video 2.3** | ComfyUI API (Vast.ai) | 1280×720 or 1056×608 | Keyframe / I2V workflow with prompt relay |
| **Audio Synthesis & Foley** | **Minimax H3 Native Audio** | Native inside H3 R2V | 48kHz Stereo | Synthesized directly from video prompt audio/foley lines |
| **Editorial Assembly & Concat** | **ffmpeg** | Local CLI | Match source stream | Stream copy (`-c copy`) or re-mux with audio normalization |

---

## 2. Engineering Around the 15-Second Video Constraint

### The Challenge
Diffusion-based video models with high temporal coherence, such as **Minimax Hailuo H3 R2V**, enforce a hard cap of **15 seconds** (or 375 frames at 25 fps) per generation pass. Attempting to render longer durations in a single pass leads to catastrophic memory consumption, hallucinated physics, and temporal drift.

### The Story Maker V4 Solution
Story Maker V4 achieves continuous 1-minute, 3-minute, or 5-minute films through four coordinated architectural pillars:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               15-SECOND CONTINUITY PIPELINE                                      │
│                                                                                                  │
│   Scene s1 (60s Target)                                                                          │
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
│   ├── Generation g3 (30.0s – 45.0s) [conditioned on g2_tail.mp4]                                │
│   └── Generation g4 (45.0s – 60.0s) [conditioned on g3_tail.mp4]                                │
│                                                                                                  │
│   Final Concat: ffmpeg concats g1 + g2 + g3 + g4 → scene_s1.mp4                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Scene-to-Generation Budgeting**:
   - Every scene in `scenes.md` is partitioned into discrete generations of **5.0 to 15.0 seconds** (`g1`, `g2`, `g3`, etc.).
   - Shorter transitional scenes (e.g. 8–12s) occupy a single generation. Longer dramatic sequences (e.g. 60s) split into 4 balanced 15s generations.
   - **Hard Rule**: A cinematic shot never crosses a generation boundary. Cuts snap cleanly to generation edges.

2. **Micro-Pacing & Visual Economy (3–6 Shots per Generation)**:
   - Within each 15-second generation, the narrative progresses through **3 to 6 distinct shots** (averaging 1.5 to 3.5 seconds per cut).
   - This rhythm mirrors modern animation direction (Pixar, DreamWorks, anime), ensuring high dynamism without visual clutter.

3. **Keyframe-to-Panel Staging**:
   - Each 15s generation is anchored by **one storyboard sheet** featuring a **6-panel (`3x2`)** or **9-panel (`3x3`)** grid.
   - The panels provide the frozen visual keyframes that guide Minimax H3's camera moves, actor poses, lighting shifts, and spatial blocking across the timeline.

4. **Dynamic Tail Conditioning (`ref_videos`)**:
   - Immediately after `g1.mp4` finishes rendering, Python invokes `ffmpeg` to extract the final 3.0 seconds (`clips/s1/g1_tail.mp4`).
   - For `g2.mp4`, the ComfyUI workflow dynamically patches `g1_tail.mp4` into Minimax's `ref_videos` input.
   - The model uses the tail's ending frame, lighting, character momentum, and motion vectors as the initial condition for `g2`, eliminating jarring jump-cuts and maintaining unbroken emotional immersion.

---

## 3. End-to-End Artifact Showcase: "Bamboo the Dino — Mama"

Below is the complete, concrete realization of **Scene 1 (60 seconds total, Generation 1: 0.0s–15.0s)** from *Bamboo the Dino*.

---

### Step 1: Developed Story Screenplay (`developed_story.md`)
*Authored by Agent 1 (Story Developer) following the v4.2.0 Animation Screenplay Standard.*

```markdown
# BAMBOO THE DINO

Episode: epi-1
Working Title: Mama
Target Delivery: 60 seconds

---

EXT. SUNLIT LAWN - DAY

A bumblebee BUZZES past green dandelion stems.

INT. BASEMENT - CONTINUOUS

Shafts of honey-colored sunlight pierce the grime of a high ground-level window, illuminating swirls of golden dust motes.

Stacks of yellowing cardboard boxes and draped white sheets form a subterranean maze.

In the shadows, an ancient wooden steamer trunk sits ajar. Deep within the trunk, nestled in dry straw:

A speckled, luminescent egg — the size of a honeydew melon. It pulses with a warm, rhythmic amber GLOW.

Patter-patter. TINY BARE FEET in mismatched socks step into the shaft of light.

LEO (2), chubby-cheeked with a shock of untamed brown curls and wearing a star-patterned onesie, toddles into the clearing.

His wide brown eyes fixate on the pulsing glow.

LEO
(whispering, awed)
Ooh...

Leo drops to his knees. Pushes aside a hanging canvas sheet with a dry RUSTLE.

The egg SHUDDERS.

A hairline FRACTURE races across the speckled shell.

SNAP! A chunk of shell pops free with a moist POP.

Leo falls backward onto his padded diaper, mouth forming an 'O' of astonishment.

Two tiny three-toed lime-green claws grip the cracked opening.

A rounded snout pushes through, followed by oversized, liquid-yellow eyes.

BABY BAMBOO (newborn dino) blinks against the dust-mote light. Scales glisten lime-green over a soft cream-colored belly.

Bamboo spots Leo. Bamboo's stubby tail WAGS vigorously against the straw.

BAMBOO
(soft high-pitched squeak)
Ma-ma!

Leo's eyes bulge. He scrambles backward on all fours, heels kicking up puffs of basement DUST.

LEO
(panicked babble)
No mama! No mama!

Leo scrambles behind a towering stack of encyclopedias.

Bamboo tilts his head, lets out a cheerful TRILL, and waddles forward in hot pursuit.

---

## Characters

### char_01 — Leo (Toddler)
- **Role**: Protagonist
- **Species**: Human toddler, 2 years old
- **Appearance**: Chubby cheeks, button nose, wide expressive brown eyes, messy tuft of soft brown hair.
- **Wardrobe**: Cream-white long-sleeved onesie with small faded navy star pattern. Mismatched knitted socks: left sock bright sky blue, right sock pastel yellow. No shoes.
- **Dramaturgical Function**: Vulnerable, curious, startled easily, highly expressive physical comedy.

### char_02 — Bamboo (Baby Dino)
- **Role**: Deuteragonist
- **Species**: Baby miniature dinosaur (fictional domestic herbivore)
- **Appearance**: Size of a plump house cat. Bright lime-green fine pebbled scales, cream underbelly and throat. Giant round golden-yellow eyes with circular pupils. Small rounded snout with no visible teeth. Tiny forearms, stubby tail that wags like a puppy's. Soft scalloped darker-green ridges along spine.
- **Dramaturgical Function**: Completely harmless, joyful, innocent, imprints instantly on Leo.

---

## Locations

### loc_basement — Dusty Sunlit Basement
- **Description**: Residential suburban basement. Rough fieldstone foundation walls, smooth concrete floor with fine dust layer. A single rectangular ground-level window high on the north wall lets in direct late-afternoon golden shafts. Left wall lined with dark mahogany wardrobes. Right side filled with stacked moving boxes, draped furniture, forgotten bicycles, and an open steamer trunk with straw. Center floor is an open dusty clearing. Warm, cozy, safe ambiance.

---

## Objects

### obj_egg — Glowing Dinosaur Egg
- **Description**: Ovoid egg, 25cm tall. Mottled sage-green and cream shell covered in faint iridescent speckles. Emits internal pulsating amber-gold bioluminescence. In cracked state, fractures emit bright white-gold light beams.
```

---

### Step 2: Beat Board (`beat_board.md`)
*Authored by Agent 1b (Beat Board Architect).*

```markdown
# Beat Board — Episode 1: Mama
target_seconds: 60
scene_budget: 70

## Beat 1 — The Discovery
beat_id: b1
source_scene_id: s1
description: Leo pads into the dusty basement and discovers a pulsating golden egg inside the open steamer trunk.
emotion: curious wonder
estimated_seconds: 8.0
characters_present: [char_01]
forbidden_characters: [char_02]
required_props: [obj_egg]
hard_constraints:
  - char_02 must not appear before shell fractures.
  - Golden sunlight shaft must highlight egg.

## Beat 2 — The Hatching
beat_id: b2
source_scene_id: s1
description: The egg shell snaps and Baby Bamboo emerges, shaking off albumen and blinking at the world.
emotion: suspense to delightful surprise
estimated_seconds: 7.0
characters_present: [char_01, char_02]
forbidden_characters: []
required_props: [obj_egg]
hard_constraints:
  - First co-presence of Leo and Bamboo occurs at 8.5s.
  - Dino must look completely harmless and cute.

## Beat 3 — The Imprint ("Mama!")
beat_id: b3
source_scene_id: s1
description: Bamboo locks eyes with Leo, wags his stubby tail, and squeaks his first word: "Ma-ma!"
emotion: heart-melting affection
estimated_seconds: 10.0
characters_present: [char_01, char_02]
forbidden_characters: []
required_props: []
hard_constraints:
  - Spoken dialogue "Ma-ma!" must be synchronized to dino beak opening.

## Beat 4 — The Panic Retreat
beat_id: b4
source_scene_id: s1
description: Leo freaks out, protests "No mama!", and scrambles backward behind cardboard box fortress.
emotion: comedic terror
estimated_seconds: 12.0
characters_present: [char_01, char_02]
forbidden_characters: []
required_props: []
hard_constraints:
  - Mismatched sock colors (blue left, yellow right) must remain visible during crawl.
```

---

### Step 3: Scenes Specification (`scenes.md`)
*Authored by Agent 2 (Scene Writer).*

```markdown
# Scenes
target_seconds: 60
scene_budget: 70

## Scene s1 — Mama
scene_id: s1
target_seconds: 60
cast: [char_01, char_02]
characters_present: [char_01, char_02]
location_id: loc_basement
objects: [obj_egg]
beats: [b1, b2, b3, b4]
beat: A curious toddler explores a sunlit dusty basement, witnesses a glowing egg hatch into a tiny lime-green baby dinosaur, and panics when the baby dinosaur happily calls him "Mama."

### Scene-End Handoff -> Episode 2
on_screen: [char_01, char_02]
mood: playful standoff transitioning to friendship
position: Leo peeking around cardboard box at x=1200; Bamboo sitting happily in center floor light pool at x=1920.
facing: Leo facing camera right; Bamboo facing camera left.
lighting: warm golden afternoon sunset shaft fading to amber twilight.
audio: Bamboo soft purr, Leo nervous giggle.
transition: fade_to_black
```

---

### Step 4: Spatial Plan (`spatial_plan_s1.md`)
*Authored by Agent 3a (Spatial Architect).*

```markdown
# Spatial Plan — Scene s1: Mama
scene_id: s1
location_ref_id: loc_basement
primary_anchor: window_light_shaft
world_axis: High window on North wall (Z=100); Camera looks North from South open floor (Z=0). Left=West (wardrobes), Right=East (boxes).

## Landmarks & Coordinates (Canvas 3840×2160 Normalized)
- `window_light_shaft`: X=[1600, 2400], Y=[0, 2160], Z=[10, 80] — Main spotlight.
- `steamer_trunk`: X=[1900, 2300], Y=[1200, 1700], Z=[35] — Open wooden trunk with straw.
- `wardrobe_wall`: X=[0, 800], Y=[200, 2160], Z=[10, 90] — Deep shadow boundary screen-left.
- `box_fortress`: X=[2800, 3840], Y=[600, 2160], Z=[15, 70] — Stacked brown moving boxes screen-right.
- `open_dust_clearing`: X=[1000, 2800], Y=[1100, 2000], Z=[5, 30] — Center staging arena.

## Character Blocking & Movement Vector
- **char_01 (Leo)**:
  - Enters from screen-left foreground (X=900, Z=5) at 0.0s.
  - Kneels at center-left clearing (X=1500, Z=20) facing trunk at 5.0s.
  - Falls back to (X=1300, Z=15) when egg cracks at 8.0s.
  - Scrambles backward toward box fortress (X=2600, Z=25) at 12.0s.
- **char_02 (Bamboo)**:
  - Absent 0.0s – 7.5s.
  - Emerges inside trunk at (X=2100, Z=35) at 8.5s.
  - Steps out of trunk onto dust floor at (X=2000, Z=30) at 10.5s.
  - Faces Leo (screen-left) continuously.

## Visibility & Exclusion Constraints
- `char_02` must have 0% visibility in panels 1–5 (Shots 1–4).
- `char_01` left sock must be Blue (#2A75D3), right sock Yellow (#E8C832) in all full/medium shots.
```

---

### Step 5: Character Sheet Prompts (`image_prompts/characters/`)
*Target Model: **OpenAI GPT-Image-2** (3840×2160, WebP, quality=medium)*

#### `image_prompts/characters/char_01.txt`
```text
A clean character identity turnaround sheet of a chubby human toddler boy, 2 years old, named Leo. Round button face, rosy pink cheeks, large curious hazel-brown eyes, messy tuft of soft brown hair with baby cowlick. He wears a plain cream-white cotton onesie with small faded navy stars printed across the fabric. Mismatched hand-knitted socks: left foot has a bright sky-blue sock, right foot has a soft pastel-yellow sock. Barefoot in socks only, no shoes. Full body turnaround displayed in front, three-quarter, and profile poses on a neutral light-gray background. Bottom half features a head-and-shoulders expression grid: curious wonder, surprised gasp, joyful laugh, and wide-eyed mild panic. Pixar-quality cinematic 3D animation style. Subsurface scattering on skin, clean anatomical proportions, consistent wardrobe across all poses. No text, no labels, no captions, no numbers, no watermarks.
```

#### `image_prompts/characters/char_02.txt`
```text
A clean character identity turnaround sheet of a tiny, adorable baby dinosaur named Bamboo, the size of a plump house cat. Bright lime-green scales with fine pebbled texture, contrasting soft cream-colored belly and throat. Oversized, circular liquid-golden eyes with rounded friendly pupils. Short rounded snout with friendly nostrils and no visible sharp teeth — completely harmless and endearing. Two stubby arms with three rounded baby claws, short sturdy hind legs, and a plump tapering tail that wags happily. A crest of soft, rounded darker-green scalloped spines runs down his back from crown to tail tip. Full body turnaround in front, three-quarter, and side views against a neutral light-gray studio backdrop. Lower strip features facial expressions: sleepy hatching blink, joyful smiling chirp, curious head tilt, and wide-mouthed squeak. Feature-film 3D animation aesthetic, soft tactile specular reflections. No text, no labels, no captions, no numbers, no watermarks.
```

---

### Step 6: Location & Object Prompts (`image_prompts/locations/` and `objects/`)
*Target Model: **OpenAI GPT-Image-2** (3840×2160, WebP, quality=medium)*

#### `image_prompts/locations/loc_basement.txt`
```text
An empty, atmospheric residential basement interior bathed in late-afternoon golden sunlight streaming through a single high ground-level window on the far concrete wall. Rough rustic fieldstone walls, smooth dusty concrete floor with swirling patterns in the fine gray dust. On the left: tall antique mahogany wardrobes creating a solid architectural boundary. On the right: an organized maze of stacked brown cardboard boxes with packing tape and old furniture draped in dusty white cotton drop cloths. In the center: an open floor clearing with a vintage wooden steamer trunk sitting open with clean dry straw inside. A brilliant diagonal sunbeam cuts through the air, highlighting swirling golden dust motes in suspended motion. Warm amber, honeyed brown, and deep slate tones. Pixar-style feature animation cinematic set plate. Completely empty stage — no human characters, no animals. No text, no labels, no watermarks, no frame borders.
```

#### `image_prompts/objects/obj_egg.txt`
```text
A clean hero object reference sheet for an ancient glowing dinosaur egg. The egg is approximately 25 centimeters tall, ovoid with slightly flattened bottom. Mottled sage-green and cream ceramic-like shell texture with delicate turquoise speckles. The egg radiates a soft internal golden-amber bioluminescence that shines through translucent micro-fractures in the shell. Shown in three sequential states against a neutral backdrop: Left: pristine glowing intact egg resting on golden straw. Center: hairline glowing fractures spiderwebbing across the shell surface. Right: top section cleanly cracked open like a geode, revealing warm golden radiant interior void and small shell shards resting on the ground. Pixar-quality 3D render, crisp studio lighting, volumetric light glow. No text, no labels, no captions, no watermarks.
```

---

### Step 7: Storyboard Sheet Prompt (`image_prompts/s1/storyboard_sheet_g1.txt`)
*Target Model: **OpenAI GPT-Image-2** (3840×2160, WebP, quality=medium)*
*Grid: **9-panel 3x3 regular grid** (1280×720 equal cells, thin 4px white gutters).*

```text
ref_images: loc_basement, char_01, char_02, obj_egg

Create one text-free cinematic pre-production storyboard sheet containing exactly nine panels arranged in three rows and three columns (3x3 grid). Time flows column-major: read down Column 1 (Panels 1, 2, 3), down Column 2 (Panels 4, 5, 6), then down Column 3 (Panels 7, 8, 9).

CANVAS AND GRID
Canvas: 3840 pixels wide by 2160 pixels tall.
Use a regular grid of nine equal widescreen panels, each exactly 1280x720 pixels (true 16:9 ratio).
Separate all panels with crisp, uniform white divider lines exactly four pixels wide.
No outer borders, no rounded corners, no decorative elements, no overlapping cells.
ABSOLUTELY TEXT-FREE: No numbers, no panel labels, no timecodes, no dialogue text, no captions, no watermarks.

REFERENCE PRIORITY
1. Match the attached character sheet for char_01 (Leo): chubby toddler, onesie with navy stars, mismatched socks (blue left, yellow right).
2. Match the attached character sheet for char_02 (Bamboo): lime-green baby dino, giant yellow eyes, cream belly.
3. Match the attached location reference loc_basement: fieldstone walls, stacked boxes right, wardrobe left, golden sun shaft.
4. Match obj_egg: mottled sage-green glowing egg in steamer trunk.
Maintain persistent 3D set geography across all nine views.

SPATIAL CONTINUITY BIBLE
The high sunlit window is North. Sunbeam strikes center floor at the open steamer trunk.
Cardboard boxes remain on screen-right; dark wardrobe remains on screen-left.
Leo enters from screen-left; egg is positioned center-right.

PANEL DIRECTIONS (9 PANELS)

Column 1 — The Approach (0.0s – 5.0s)
Panel 1 (Top-Left): Extreme Close-Up of Leo's wide brown eyes peering curiously into the dusty basement gloom, golden light reflecting in his irises.
Panel 2 (Mid-Left): Low-angle tracking shot at floor level. Leo's tiny feet padding through gray dust. Blue sock clearly on left foot, yellow sock on right foot. Cardboard box corner visible.
Panel 3 (Bottom-Left): Medium shot from behind Leo. Leo parts a hanging canvas drop-cloth; a glowing golden beam reveals the open steamer trunk with the pulsing amber egg nestled in straw.

Column 2 — The Hatching (5.0s – 10.5s)
Panel 4 (Top-Center): Close-Up of Leo's illuminated face, mouth open in a soft gasp of awe, rosy cheeks glowing in amber light.
Panel 5 (Mid-Center): Close-Up on the egg inside the trunk. A bright jagged fissure snaps across the shell with glowing white light escaping from within.
Panel 6 (Bottom-Center): Three-quarter view of the egg cracking open. Tiny lime-green clawed hands push shell fragments outward into the straw.

Column 3 — The Encounter (10.5s – 15.0s)
Panel 7 (Top-Right): Medium shot. Baby Bamboo the dino stumbles out of the cracked shell, blinks huge round yellow eyes, and smiles with sheer innocent delight.
Panel 8 (Mid-Right): Close-Up on Bamboo's face as he opens his mouth in a cheerful high-pitched trill, stubby tail wagging in motion blur.
Panel 9 (Bottom-Right): Wide two-shot. Bamboo steps eagerly toward Leo. Leo sits abruptly on his diaper on the dusty floor, hands thrown back in shock, mouth agape in panic.

HARD EXCLUSIONS
No other humans, no adult dinosaurs, no exterior shots, no text overlays, no dialogue bubbles, no split-screen cells within a panel.
```

---

### Step 8: Video Generation Prompt (`video_prompts/s1_g1.txt`)
*Target Model: **Minimax Hailuo H3 R2V** (ComfyUI Ref2VA workflow)*
*Duration: **15.0 seconds** | Resolution: **1056×608 (0.6MP)** | Audio: **Native Stereo***

```text
Reference

Use <Picture 1> (the 9-panel 3x3 storyboard sheet) as the strict reference for framing, character designs, color palette, staging, and lighting.
Maintain the exact appearance of toddler Leo: white onesie with faded star pattern, mismatched socks (blue on left foot, yellow on right foot), chubby rosy cheeks.
Maintain the exact appearance of baby dino Bamboo: lime-green scales, cream belly, enormous round yellow eyes, rounded snout.
Maintain the persistent environment: dusty basement with warm golden window light beam, stacked boxes right, open trunk center.

Generate a cinematic 15.0-second fast-paced sequence with rapid hard cuts, faithfully translating the 9-panel storyboard progression into continuous motion.

Pixar-quality feature 3D animation style.
Rich tactile surfaces: dust particles floating in volumetric light, soft cotton fabric, pebbled reptilian skin.
Snappy expressive character animation with natural weight and inertia.
Warm amber, golden-hour basement lighting with soft cinematic shadows.

Timeline

SHOT 1 — 0.0–1.5s (Continuous Shot)
Extreme close-up on Leo's wide brown eyes blinking in the darkness. The irises catch a pulsing amber reflection.
Camera: Slow Push In toward pupils.
Audio: Soft childlike breathing, quiet ambient basement room tone.

Hard cinematic cut.

SHOT 2 — 1.5–3.2s (Continuous Shot)
Low-angle tracking shot following Leo's tiny feet across dusty concrete. The blue left sock and yellow right sock kick up tiny puffs of dust.
Camera: Tracking shot moving backwards at toddler walking pace.
Audio: Soft rhythmic patter-patter of socked feet on concrete floor.

Hard cinematic cut.

SHOT 3 — 3.2–5.0s (Continuous Shot)
Medium shot. Leo's small hands pull back a heavy draped white sheet, revealing the glowing amber egg sitting in straw inside the steamer trunk.
Camera: Pan right with Leo's arm movement.
Audio: Dry fabric rustling, rising resonant magical amber hum.

Hard cinematic cut.

SHOT 4 — 5.0–6.8s (Continuous Shot)
Close-up on Leo's face bathed in golden light. His eyes widen in pure wonder, mouth parting as he whispers softly.
Camera: Static lock-off with subtle organic handheld float.
Dialogue: LEO: "(whispering) Ooh..."
Audio: Soft intake of breath, resonant hum continues.

Hard cinematic cut.

SHOT 5 — 6.8–8.5s (Continuous Shot)
Tight shot on the egg. A bright fracture violently zips across the shell surface. Pieces burst outward with an energetic pop.
Camera: Quick snap zoom into the fissure.
Audio: Sharp ceramic SNAP, wet suction pop, sudden chime release.

Hard cinematic cut.

SHOT 6 — 8.5–11.0s (Continuous Shot)
Tilt up from the cracked shell as tiny lime-green Bamboo emerges, shaking sticky shell pieces off his head. His enormous yellow eyes blink twice and lock onto Leo.
Camera: Tilt up smoothly from straw to Bamboo's smiling face.
Audio: Cute reptilian chirp, rustling dry straw, upbeat pizzicato string swell.

Hard cinematic cut.

SHOT 7 — 11.0–13.0s (Continuous Shot)
Close-up of Bamboo happily opening his rounded snout, stubby tail wagging like a puppy's against the trunk wood.
Camera: Static close-up on Bamboo.
Dialogue: BAMBOO: "(squeaky baby chirp) Ma-ma!"
Audio: High-pitched cheerful vocal squeak, rapid tail thumps on wood (thump-thump-thump).

Hard cinematic cut.

SHOT 8 — 13.0–15.0s (Continuous Shot)
Wide two-shot. Bamboo hops out of the trunk toward Leo. Leo's expression turns from shock to pure comedic panic; he falls backward onto his diaper and rapidly kicks his feet to scramble away.
Camera: High-angle wide shot holding both characters in frame.
Dialogue: LEO: "(panicked scramble) No mama!"
Audio: Thud of diaper landing on floor, chaotic dust scuffling, comedic brass slide whistle accent.

Transitions
Cuts between shots are instantaneous hard cuts occurring precisely at 1.5s, 3.2s, 5.0s, 6.8s, 8.5s, 11.0s, and 13.0s. No dissolves, no cross-fades, no wipe transitions.

Soundscape
Overall mix: Intimate character foley (sock footsteps, cloth rustle, egg fracture, tail thumps) layered over a warm, dusty basement ambience with a gentle orchestral animation score that pivots from mysterious wonder to playful comedic panic.
```

---

### Step 9: Tail Continuation for Generation 2 (`video_prompts/s1_g2.txt`)
*Demonstrating how the 15-second boundary is crossed seamlessly.*

```text
ref_videos: clips/s1/g1_tail.mp4

Reference

Use <Picture 1> (storyboard_sheet_s1_g2.webp) for staging and composition.
CRITICAL: Condition motion, lighting, and actor position on the attached 3-second tail video <Video 1>.
At 0.0s of this generation, Leo MUST be sitting on the floor at the exact position shown at the end of <Video 1>, scrambling backward on his hands and knees.
Bamboo MUST be mid-waddle at center floor, cheerfully bounding after him.

Generate a cinematic 15.0-second sequence (15.0s – 30.0s of Scene 1) continuing the comedic chase through the cardboard box maze.
...
```

---

### Step 10: Render Manifest & Verification (`render_manifest.json`)
*Generated deterministically by `scripts/build_manifest.py` to guarantee zero-tamper reproducible pipeline execution.*

```json
{
  "manifest_version": "1.0",
  "story": "bamboo-the-dino",
  "episode": "epi-1",
  "target_duration_seconds": 60.0,
  "created_at": "2026-09-10T18:00:00Z",
  "models": {
    "image_backend": "openai/gpt-image-2",
    "video_backend": "minimax-h3-r2v",
    "concat_engine": "ffmpeg-7.0"
  },
  "asset_hashes": {
    "assets/characters/char_01.webp": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "assets/characters/char_02.webp": "sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    "assets/locations/loc_basement.webp": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "sheets/s1/storyboard_sheet_g1.webp": "sha256:77963b7a931377ad4ab5ad6a9cd718aa5b2046e3ac563399da94e4bc66b48a20"
  },
  "generations": [
    {
      "id": "s1_g1",
      "scene_id": "s1",
      "duration_seconds": 15.0,
      "panel_grid": "3x3",
      "total_panels": 9,
      "total_shots": 8,
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
      "panel_grid": "3x2",
      "total_panels": 6,
      "total_shots": 5,
      "sheet_prompt": "image_prompts/s1/storyboard_sheet_g2.txt",
      "video_prompt": "video_prompts/s1_g2.txt",
      "tail_condition": "clips/s1/g1_tail.mp4",
      "output_clip": "clips/s1/g2.mp4",
      "tail_extracted": "clips/s1/g2_tail.mp4",
      "validation_status": "PASS"
    }
  ],
  "gates": {
    "gate_0_critique": "PASSED (0 FAILs, 2 ADVISORY)",
    "gate_1_sheets": "APPROVED_BY_USER",
    "gate_2_prompts": "APPROVED_BY_USER"
  }
}
```

---

## 4. Summary Checklist for Any Generation Run

When preparing or validating any Story Maker V4 run, ensure:
1. **Grid Selected Appropriately**:
   - `3x2` (6 panels, 8:3 ratio) for standard 8–12s generations (default).
   - `3x3` (9 panels, 16:9 ratio) for dense, rapid-cut 13–15s action generations.
2. **Shot-to-Panel Ratio**: Every panel belongs to exactly one shot. No shot spans across generation boundaries.
3. **Model Specifications Quoted**: All still prompts target **OpenAI GPT-Image-2** (3840×2160, WebP); video prompts target **Minimax Hailuo H3 R2V** (1056×608, 25fps, native stereo).
4. **Tail Continuity Configured**: Every generation after `g1` declares `ref_videos: [previous_tail.mp4]`.
5. **No Text in Still Images**: Character, location, object, and storyboard prompts must explicitly forbid text, labels, numbers, captions, and watermarks.
