# Canonical Worked Example — "Ollie's Dive"

One story, one scene, one generation, threaded through every artifact type.
**All agent prompts use this same example** — when you see `char_01`,
`loc_01`, `obj_01`, scene `s1`, or generation `s1/g2` in a prompt file, it
refers to this story. Do not invent a different example cast.

Source material: the opening sequence of *Swapped* (Netflix / Skydance),
analyzed in `Research/ollie/`. Adapted here as a self-contained episode.

## Canonical entities

These ids are stable across every artifact below:

| id | entity |
|---|---|
| `char_01` | **Young Ollie** — a small otter-like Pookoo: fluffy chocolate-brown fur, spiky russet hair tuft, oversized black button nose, cream muzzle, huge emerald-green eyes |
| `char_02` | **Caloo** — Ollie's father: large shaggy auburn-furred Pookoo, broad paws, weathered whiskers, tired overprotective eyes |
| `char_03` | **Giant Valley Fish** — immense freshwater fish, iridescent cyan-and-purple scales, kelp-like dorsal frills, deceptively placid wide-set eyes, expandable jaw |
| `loc_01` | **Sunlit Pond Edge** — lush meadow shoreline, mossy boulders, orange gerberas, clover, glassy pond |
| `loc_02` | **Underwater Valley** — crystalline aquamarine water, mossy stone terraces, bioluminescent flora, cathedral light beams |
| `obj_01` | **Handmade Basket** — woven bark basket holding a spiral seashell and pink blossoms |
| `obj_02` | **Makeshift Diving Helmet** — hollowed wooden cylinder, polished pebble faceplate, amber sap seals, woven leaf strap |
| `obj_03` | **Reed Snorkel** — long hollow plant stem lashed to the helmet, buoyant bark-disc float |

## The canonical scene and generation

The example scene is **`s1` — "The Idea"** (45s at `loc_01`), split into
three generations. The canonical worked generation is **`s1/g2`**
(15.0–30.0s): a **1-shot oner** in which Ollie peers through the hollow
wooden cylinder and discovers the underwater world — chosen because it
demonstrates a *continuation* boundary (tail ref, `<Video 1>`) and oner
panel allocation.

- `s1/g1` (0.0–15.0s, 6 shots, `3x3`): Ollie admires his basket, a
  dragonfly startles him, the basket tumbles into the pond.
- **`s1/g2` (15.0–30.0s, 1-shot oner, `2x3`)**: Ollie lies prone at the
  water's edge, peers through the hollow cylinder at the shimmering
  underwater world, and the idea ignites on his face.
- `s1/g3` (30.0–45.0s, 4 shots, `3x2`): Ollie presses the cylinder over
  his head and dunks underwater — and instantly sputters, soaked.
- Handoff to `s2` — "The Underwater World" (`loc_02`): `hard_cut`
  (new subject space — the next scene opens fresh, no tail ref).

---

## 1. `developed_story.md` excerpt (Agent 1)

```text
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
```

`## Characters` / `## Locations` / `## Objects` entries:

```markdown
## Characters
- id: char_01
  name: Young Ollie
  species: pookoo (otter-like woodland creature)
  age: 5
  appearance: fluffy chocolate-brown fur, spiky russet hair tuft,
    oversized black button nose, cream muzzle, huge emerald-green eyes

## Locations
- id: loc_01
  name: Sunlit Pond Edge
  description: lush meadow shoreline with mossy boulders, orange
    gerberas, clover, and a glassy pond
  establishing_prompt: wide-angle 360-degree view of a sunlit pond edge ...

## Objects
- id: obj_01
  name: Handmade Basket
  description: woven bark basket holding a spiral seashell and pink blossoms
  appearance: rough bark weave, glossy spiral shell, bright pink petals
```

`## Constraints` + `story.json` examples (canonical shapes):

```markdown
## Constraints
- id: H1
  type: co_presence_exclusion
  severity: BLOCKER
  subjects: [char_01, char_03]
  valid_until_scene: s2
  rule: Ollie and the Giant Valley Fish must not share a frame before
    the reveal shot in Scene 2.

- id: H2
  type: prop_state
  severity: BLOCKER
  subjects: [obj_01]
  rule: The basket sinks into the pond in Scene 1 and is never carried
    underwater or seen again.

- id: E1
  type: editorial
  rule: End title card is an editorial graphic, excluded from sheets.
```

```json
{
  "title": "Ollie's Dive",
  "intake_mode": "preserve_script",
  "duration_mode": "preserve_script",
  "target_seconds": 224,
  "characters": [
    {"id": "char_01", "name": "Young Ollie", "species": "pookoo", "age": 5},
    {"id": "char_02", "name": "Caloo", "species": "pookoo"},
    {"id": "char_03", "name": "Giant Valley Fish", "species": "fish"}
  ],
  "locations": [
    {"id": "loc_01", "name": "Sunlit Pond Edge",
     "landmarks": ["mossy_boulder", "rock_ledge", "waterline"]},
    {"id": "loc_02", "name": "Underwater Valley",
     "landmarks": ["mossy_terraces", "kelp_forest"]}
  ],
  "objects": [
    {"id": "obj_01", "name": "Handmade Basket",
     "states": ["held", "floating", "sunk"]},
    {"id": "obj_02", "name": "Makeshift Diving Helmet"}
  ],
  "constraints": [
    {"id": "H1", "type": "co_presence_exclusion",
     "subjects": ["char_01", "char_03"], "valid_until_scene": "s2",
     "severity": "BLOCKER"}
  ]
}
```

## 2. `beat_board.md` excerpt (Agent 1b)

```markdown
# Beat Board — Ollie's Dive

target_seconds: 224
beat_count: 9

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

## Beat 5 — Breakthrough
description: The bark-disc float keeps the snorkel upright; the rig finally works.
emotion: triumph
estimated_seconds: 20

## Beat 6 — Wonder
description: Ollie explores a bioluminescent paradise, dances with leaf-fish, and wakes a lakebed of blooming flower-snails.
emotion: awe
estimated_seconds: 75

## Beat 7 — Peril
description: A giant iridescent fish approaches; its friendly smile unhinges into a cavernous jaw.
emotion: fear
estimated_seconds: 25

## Beat 8 — Rescue
description: Caloo plunges in, snatches Ollie by the scruff, and outruns the lunging predator.
emotion: tension
estimated_seconds: 10

## Beat 9 — Button
description: Soaked under his father's glare, Ollie offers the wet helmet and a cheesy grin: "Hey, Dad... Thirsty?"
emotion: relief
estimated_seconds: 10
```

## 3. `scenes.md` excerpt (Agent 2)

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
style_target: high-fidelity stylized 3D CGI animation with tactile
  physical shaders and subsurface scattering
acting_beat: proud stillness → startled lurch → wide-eyed wonder
layout_strategy: boulder and basket foreground-right, pond opening
  midground-left, eye path follows the basket's fall into the water
visual_motif: round openings — basket mouth, cylinder rim, pond surface —
  each a portal that grows in meaning
sound_world: meadow birds, gentle water lap, whimsical acoustic strings
beat: A spilled basket reveals an underwater world to a young inventor.

## Scene s2 — The Underwater World
scene_id: s2
target_seconds: 100
cast: [char_01, char_03]
characters_present: [char_01, char_03]
location_id: loc_02
objects: [obj_02, obj_03]
beats: [6, 7]
...
```

## 4. `spatial_plan_s1.md` excerpt (Agent 3a)

```md
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

## Zone ledge
relative_to: rock_ledge
x_range: [1100, 2100]
y_range: [1200, 2160]
z_range: [0, 3]
distance_from_anchor_m: 0
lighting: warm golden sun from screen-left

## Generation g2
location_reference: omit
generation_geography: Ollie prone on the rock ledge at the waterline,
  peering through the hollow cylinder toward the pond
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

## 5. `storyboard_s1.md` excerpt (Agent 3)

```markdown
## Generation g2 — 15.0-30.0s
duration_seconds: 15.0
panel_grid: 2x3

### Shot 1 — 15.0-30.0s (continuous)
panels: [1, 2, 3, 4, 5, 6]
characters_present: [char_01]
shot_size: medium_closeup
composition: frame_within_frame, visual_hierarchy, depth
focus: shallow_focus
acting_beat: curious lean-in → eyes widen → grinning lightbulb moment
layout: Ollie prone on the ledge foreground-right, cylinder rim framing
  his face, waterline behind
screen_direction: left_to_right
camera_angle: low_angle
action: Unbroken continuous master take: Ollie lies prone at the pond
  edge, lifts the hollow wooden cylinder to his eye, peers through at the
  shimmering underwater world — light refractions, swaying weeds — and his
  eyes widen into a grinning lightbulb moment.
camera: Slow Push In with small amplitude at slow speed, drifting toward
  the cylinder opening.
audio: muffled underwater hum through the tube, water lap, a single
  inquisitive celesta note.
dialogue:
```

## 6. `image_prompts/s1/storyboard_sheet_g2.txt` excerpt (Agent 4)

```
ref_images: loc_01, char_01, obj_02

A text-free cinematic pre-production storyboard sheet. 3840×2160 landscape
page. Exactly six fully painted, equal rectangular panels arranged in a
2×3 grid (2 rows × 3 columns). Column-major reading order: top-left,
bottom-left, top-middle, bottom-middle, top-right, bottom-right — the
left column is the beginning of the take, the right column is the end.
...

## PANEL DIRECTIONS (temporal milestones of ONE unbroken take)

### PANEL 1 — PRONE AT THE EDGE
(top left). Camera low at the waterline, close on Ollie lying prone on
the flat stone ledge, chocolate-brown fur sunlit, the hollow wooden
cylinder resting beside his paws. The glassy pond fills the left half
of frame; his basket floats forgotten behind him.

### PANEL 2 — THE LIFT
(bottom left). Same camera position: Ollie's paws lift the cylinder
toward his face, its dark circular opening tilting toward camera.
...
```

## 7. `video_prompts/s1_g2.txt` excerpt (Agent 5)

```text
subject_definitions:
<Subject 1> is Young Ollie in <Picture 1>, a small otter-like Pookoo with
fluffy chocolate-brown fur, a spiky russet hair tuft, an oversized black
button nose, a cream muzzle, and huge emerald-green eyes.
<Picture 1> is the storyboard reference for [Shot 1], defining viewpoint,
subject placement, and the take's progression.
<Video 1> is the previous generation's rendered tail and continuation
starting point.
(S1) is <Subject 1>'s voice.

summary:
[video continuation + reference generation] The video seamlessly
continues from <Video 1> as Ollie peers through the hollow cylinder and
discovers the underwater world.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - fur, tuft, nose,
muzzle, and eyes retained.
<Picture 1> (storyboard reference): fully_preserved - composition,
lighting, and panel sequence.
<Video 1> (continuation starting point): fully_preserved - ending pose,
staging, lighting, and motion state.

detailed_description:
High-fidelity stylized 3D CGI animation, warm sunlit meadow light,
tactile fur shaders.
[Shot 1] Continuing seamlessly from <Video 1>, <Subject 1> lies prone on
the flat stone ledge at the water's edge, matching the previous clip's
ending pose and low camera height. He lifts the hollow wooden cylinder
to his eye and peers through: shimmering aquamarine light, swaying
water-weeds, drifting motes. His emerald eyes widen slowly, then spark —
a grinning lightbulb moment, ears perking. The camera pushes in with
small amplitude at slow speed toward the cylinder's dark opening. Soft
contented sniff; a tiny gasp inside the tube. Never generate duplicate
characters or extra limbs.

overall_soundscape:
Muffled underwater hum resonating through the wooden tube, gentle water
lapping against the ledge, distant meadow birds.

non_diegetic_music:
A single inquisitive celesta phrase over soft sustained strings.
```

## 8. `spatial_qa_report.md` excerpt (Agent 7)

```md
# Spatial QA Report — Scene s1

- Pass: 2
- Warn: 1
- Blocker: 0

## s1/g2
- Status: WARN
- image_sha256: <sha256 of storyboard_sheet_s1_g2.webp>
- spatial_plan_sha256: <sha256 of spatial_plan_s1.md>
- reviewed_at: 2026-01-01T00:00:00Z
- expected: Ollie prone on the rock ledge at the waterline, facing the
  pond; camera low from the ledge zone looking toward the waterline.
- observed: Ollie is prone on the ledge facing the water, but Panel 5
  drifts him midground-left of the ledge instead of foreground-right.
- recommendation: regenerate or accept — depth drift only; geography,
  landmarks, and facing are correct.
```
