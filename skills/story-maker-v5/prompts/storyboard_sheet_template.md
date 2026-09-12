# Storyboard sheet spec (one sheet per generation) — for Agent 4

Agent 4 reads this spec and composes ONE GPT Image 2 (Replicate) prompt per
**generation** (`storyboard_sheet_<gen>.txt`), saved to
`<run_dir>/image_prompts/<scene>/storyboard_sheet_<gen>.txt`.
`build_images.py` dispatches it with the location lock (per the spatial plan's
`location_reference`), the previous generation's sheet, and the character
sheets as edit references. The rendered sheet is attached verbatim as
`<Picture 1>` in that generation's Minimax H3 video prompt.

**Canonical convention: per-generation sheets only.** There is no scene-level
`storyboard_sheet.txt`. `validate_prompts` rejects it, `build_images.py` and
`render_all.py` never read it.

Panel allocation is per generation, driven by that generation's shots:

- Each shot claims 1–4 panels in **column-major** order (matching the
  storyboard's `panels:` field exactly — the validator checks coverage).
- A **1-shot Master Take / Oner** (an unbroken continuous take) uses the
  panels as *temporal milestones* of the single take: opening staging, a
  mid-take action peak or dynamic progression, and the concluding settle.
- A **2-shot** generation splits panels proportionally to duration (e.g.
  on a 3x2 grid: Panels 1–3 for a 10s setup, Panels 4–6 for a 5s
  reaction).
- A **3–8 shot** dynamic arc gives each shot its dedicated key panel(s).

This is a **spec**, not a fill-in template. Agent 4 turns the storyboard and
spatial plan into a cohesive sheet for one generation. The sheet is NOT
cropped or upscaled — it is attached verbatim as `<Picture 1>` in the Minimax
H3 video prompt, serving as the definitive visual contract: composition,
camera angle, character appearance, environment, and temporal progression.

When a `spatial_plan_<scene>.md` exists, `materialize_spatial_prompts.py` (or
`build_images.py`) materializes a **SPATIAL CONTINUITY BIBLE** at the **top**
of the prompt file before the image call. Agent 4 writes the creative
sections (CANVAS, SEQUENCE PROGRESSION, PANEL DIRECTIONS, RENDERING STYLE,
HARD EXCLUSIONS) and must **not** manually author the generated spatial
sections.

## Layout (load-bearing — the Minimax render depends on it)

- **Canvas**: 3840×2160 landscape (4K).
- **Default grid `3x2`**: 3 rows × 2 columns = 6 panels. The left column is
  the generation's **beginning**, the right column is the **end**. Within
  each column, panels read top-to-bottom.
- **Alternative grid `3x3`**: 3 rows × 3 columns = 9 panels for longer,
  faster-paced generations. The left column is the **beginning**, middle
  column is the **middle**, right column is the **end**. Each cell is
  exactly 1280×720 — a true 16:9 panel.
- **Panel numbering is column-major**: on 3x2, Panel 1 = row 1 col 1,
  Panel 2 = row 2 col 1, Panel 3 = row 3 col 1, Panel 4 = row 1 col 2,
  Panel 5 = row 2 col 2, Panel 6 = row 3 col 2. Time flows down each column,
  then left to right across columns.
- **Cells are equal rectangular panels**, separated by thin 4px straight
  black or white gutters. They fill the entire canvas. Do **not** claim
  cells are 16:9 unless the grid divides 3840×2160 into true 16:9
  rectangles (3x3 → 1280×720).
- **NO text, NO timecodes, NO panel numbers, NO captions, NO labels, NO
  watermarks, NO speech bubbles, NO decorative frames, NO overlapping
  panels, NO blank cells, NO cells of different sizes.** All
  timing/camera/sound info lives in the video prompt, not in the image.

### Exact cell dimensions (6 to 9 panels)

| grid | rows | cols | cell size (px) | cell aspect | use case |
|------|------|------|----------------|-------------|----------|
| **3x2** *(Default/Min)* | 3 | 2 | 1920×720 | 8:3 | Standard 1 to 4 shots (balanced setup / resolution) |
| **2x3** | 2 | 3 | 1280×1080 | ~4:3 | 6-panel vertical/character emphasis |
| **3x3** *(Max)* | 3 | 3 | 1280×720 | **16:9** (True) | Dense, fast-paced 5 to 8 shots |

Use `3x2` (6 panels) as the minimum and default. If you need true 16:9 cells
for rapid-cut sequences (5–8 shots), use `3x3` (9 panels). No grids smaller
than 6 or larger than 9 panels.

## Prompt structure Agent 4 should produce

Keep the hierarchy. Immutable facts first, creative direction second,
surgical negatives last.

```
OUTPUT AND GRID
REFERENCE PRIORITY
SCENE BIBLE & SPATIAL CONTINUITY
CHARACTER BIBLE
PROP CONTINUITY & ERGONOMICS (if props matter)
CONTINUITY RULES
SEQUENCE PROGRESSION
PANEL DIRECTIONS (ACTION CONTRACT: VISIBLE POSE ONLY)
RENDERING STYLE
HARD EXCLUSIONS
FINAL CONTINUITY CHECK
```

### 1. OUTPUT AND GRID

One paragraph stating:
- "3840×2160 text-free cinematic pre-production storyboard sheet"
- Grid dimensions and exact panel count (e.g. `3x2` 6 panels, or `3x3` 9 panels)
- Thin, straight, uniform white divider lines approximately four pixels
  wide, overlaid on grid boundaries
- Every cell must contain a complete image touching gutters cleanly
- Plain prose reading order: "Read panels column-major: top-left,
  middle-left, bottom-left, top-right, middle-right, bottom-right. The
  panel numbers below are instructions only; do not render them."
- **CRITICAL**: Never insert a literal text diagram or ASCII box labeled
  `PANEL MAP` into the prompt — image models will render the diagram as
  visible text or page content. Describe reading order in prose only.

### 2. REFERENCE PRIORITY

Always establish visual authority:
1. **Match attached character sheets** for identity, wardrobe, facial
   anatomy, hair, and proportions.
2. **Match supplied location reference** for architecture, materials,
   lighting, and environmental furnishings.
3. **Treat all panels as camera views of one persistent 3D set**, not
   independently designed illustrations. Maintain a constant height
   relationship between characters and architectural anchors.
4. **Match the previous generation's sheet** (attached automatically for
   continuation generations) for the exact state the prior take ended on —
   pose, prop positions, lighting — when this generation's boundary is a
   continuation.

### 3. SCENE BIBLE & SPATIAL CONTINUITY

Global facts that do not change panel-to-panel. Extract from the storyboard
and any spatial plan:

- **Setting & Geography**: One cohesive layout throughout. Establish the
  physical arrangement (e.g., pantry on left, refrigerator immediately
  right, counter continuing right). If supplied location reference differs,
  preserve that arrangement instead.
- **Fixed Camera Side**: Keep the camera on the open-space side of the
  action to maintain screen direction and avoid 180° line-crossing. Vary
  camera height, distance, and framing without reversing geography.
- **Physical Reachability & Anchors**: Ensure props sit on reachable
  surfaces relative to character scale. Close-ups must retain recognizable
  background or surface cues connecting them to the wider set.
- **Lighting**: direction, color, quality (e.g. "warm golden-hour sunset
  from screen-left, long soft shadows, amber bounce on mud walls"). Fixed
  light source direction across all panels.
- **Geography / landmarks**: list the key architectural or environmental
  landmarks and their relationships. Keep it spatially consistent.
- **Atmosphere / mood**: the emotional color of the whole generation.

### 4. CHARACTER BIBLE

Per on-screen character, list identity locks that must remain identical
across all panels:

- Name + `cid` if needed
- Age, ethnicity, body type, proportions
- Wardrobe (exact garments, colors, patterns)
- Hairstyle (exact style, accessories)
- Distinguishing features
- Where the character begins and ends the generation (per spatial plan)

Do **not** repeat full turnaround sheets here; the character reference
images are attached separately. This section is only for the in-shot
identity lock.

### 5. PROP CONTINUITY

If the generation has important props (e.g. a toy clay pot, a stick, a
lantern, food vessels):

- List the prop and its appearance.
- State when it first appears and how it persists across panels.
- Note any transformations (shatters, drops, etc.) and in which panel they
  happen.
- **Multi-Character Prop Ergonomics (MANDATORY)** — canonical rule lives in
  `assets/production-rules.md`: allocate distinct individual props/vessels
  per character; never prompt multiple characters eating out of a single
  shared vessel simultaneously; distinguish serving vessels from eating
  vessels.

### 6. CONTINUITY RULES

Bullet list of invariants. Example (canonical worked example,
[`assets/example-ollie.md`](../assets/example-ollie.md)):

- Same sunlit pond edge, ledge, and waterline in every panel.
- Same golden-hour direction and lighting color.
- Same Ollie: fur color, russet tuft, button nose, proportions.
- Same hollow wooden cylinder across panels 2–6.
- No duplicate characters.
- No teleport jumps; movement is continuous.

### 7. SEQUENCE PROGRESSION

One sentence per panel describing its narrative function and place in the
generation. This gives the model the temporal arc. Example for `3x2`:

- Panel 1: Establish the pond edge at golden hour.
- Panel 2: Move closer to Ollie lying prone on the ledge.
- Panel 3: Reveal the hollow cylinder he lifts to his eye.
- Panel 4: Capture his widening-eyed reaction close-up.
- Panel 5: Emphasize the cylinder rim as the idea ignites on his face.
- Panel 6: Settle on a warm concluding composition of Ollie grinning.

### 8. PANEL DIRECTIONS

One subsection per panel. Name each panel as a **beat**, not a shot number.
Use `### PANEL N — BEAT NAME`. Each panel description should include:

1. **Panel position**: `(top left)`, `(middle left)`, `(bottom left)`,
   `(top right)`, etc. Use the column-major map.
2. **Camera geometry**: concrete spatial description instead of shot-size
   jargon. E.g.:
   - "camera positioned several metres back in the courtyard, low angle,
     looking up at the house facade, extreme wide"
   - "camera at Ollie's chest height, 3/4 view, 50mm-like perspective,
     framed from the waist up"
   - "camera close to Ollie's face, slightly below eye level, tight
     close-up on his expression"
3. **Staging**: who is in the panel, where they are, what they are doing,
   their expression/pose.
4. **Action / emotion**: the beat this panel captures. Use concrete visual
   verbs. Do not soften emotion from the storyboard action field.
5. **Landmarks / props**: which must be visible and which must not, if
   relevant.

Avoid stacking cinematography terms (`medium shot, rule of thirds, depth,
visual hierarchy`). Instead, describe the resulting image:

**Don't:**
> Panel 3 (top right, medium shot, rule of thirds and depth): Ollie sits on
> the ledge with the cylinder.

**Do:**
> Panel 3 (top right): camera at Ollie's waist height, three-quarter view.
> Ollie lies prone on the flat stone ledge, occupying the right third of
> the frame, the hollow wooden cylinder clearly visible in the foreground.
> The glassy pond recedes behind him. Warm golden-hour light catches his
> fur, the cylinder rim, and the wet ledge.

### 9. RENDERING STYLE

Describe the visual attributes, not a brand/style reference. E.g.:

- High-fidelity stylized 3D CGI feature animation.
- Soft fur with visible strand detail and tactile physical shaders.
- Subsurface scattering on fur and petals.
- Detailed bark, moss, and water-surface materials.
- Cinematic global illumination.
- Natural depth of field.
- Warm golden-hour volumetric atmosphere.
- Sunlit meadow pond-edge environment, materials, and flora.
- Cinematic composition with clear foreground / middle-ground / background
  separation.

**Do not use** "Pixar-quality", "Pixar-style", "Disney-style", or other
brand references.

### 10. HARD EXCLUSIONS

Short, surgical list. The model only needs to know what must not appear.

Keep:
- no text of any kind
- no numbers
- no labels
- no captions
- no subtitles
- no speech bubbles
- no watermarks
- no logos
- no invented characters
- no duplicate characters
- no duplicated panels
- no split scenes inside a panel
- no overlapping panels
- no blank panels
- no decorative storyboard graphics
- no frames inside the panels
- no gutter text

### 11. FINAL CONTINUITY CHECK

Include a final continuity check block at the end of the prompt:
- Preserve character identity, clothing, proportions, architecture, light
  direction, and prop scale across all panels.
- Track moving props across panels (e.g. from table top, to hand, to
  floor). Props move only as required by the sequence; architecture must
  never move.
- Action contract: each panel shows one distinct frozen moment. Believable
  hand grips, foot placement, natural wrist angle, object contact, depth,
  and occlusion.
- No duplicated props, extra limbs, impossible reaches, floating objects,
  mirrored layouts, blank cells, or repeated adjacent compositions.

## Spatial Continuity Bible (materialized by build_images.py)

When a `spatial_plan_<scene>.md` exists, `build_images.py` inserts a
generated **SPATIAL CONTINUITY BIBLE** at the very top of the prompt file
(after any `ref_images:` line). It contains:

- **ENVIRONMENT BIBLE**: generation geography, lighting, landmarks, world
  axis.
- **CONTINUITY RULES**: character start/end positions, movement
  constraints, landmark visibility rules per panel range.
- **PANEL STAGING**: per-shot camera zone, facing, zoom translated into
  geometry, and subject placement/facing for each panel range.

Agent 4 must **not** manually author this block. The spatial plan data is
the source of truth for geography, positions, and landmark visibility.
Agent 4's PANEL DIRECTIONS should align with the materialized staging and
use the same landmarks / zones, but may add emotion, action, and visual
emphasis.

## Example prompt (2x3 oner — the canonical Ollie worked example)

The example below is `s1/g2` — a single continuous master take distributed
across a `2x3` grid as temporal milestones, from the canonical worked
example [`assets/example-ollie.md`](../assets/example-ollie.md). All prompt
files use this same story (Ollie, the pond, the basket) so examples stay
consistent across agents.

```
ref_images: loc_01, char_01, obj_02

A text-free cinematic pre-production storyboard sheet. 3840×2160 landscape
page. Exactly six fully painted, equal rectangular panels arranged in a
2×3 grid (2 rows × 3 columns). Column-major reading order: down the left
column, then down the right column — the left column is the beginning of
the take, the right column is the end.

Thin 4px straight black gutters. No outer decorative frame. Panels touch
the gutters cleanly. No text, numbers, labels, captions, watermarks, speech
bubbles, blank cells, or decorative graphics.

## SCENE BIBLE

SETTING: A sunlit pristine pond edge — flat mossy stone ledge, clover
patches, orange gerberas, glassy water surface, dappled golden light.
The ledge meets the waterline at a clean horizontal line.

LIGHTING: Warm golden-hour sunlight from screen-left, long soft shadows,
bright sparkle on the water. The same sun direction, color, and quality
across every panel.

LANDMARKS: flat mossy stone ledge; clover patch; orange gerberas; glassy
pond surface; overhanging leaves.

ATMOSPHERE: Curious, quiet, warm afternoon discovery.

## CHARACTER BIBLE

OLLIE (char_01):
- A small young Pookoo — soft cream fur, russet-colored head tuft, round
  expressive eyes, small button nose, stubby paws.
- Childlike proportions, oversized head, short limbs.
- Bare fur, no clothing.
- Same face, fur color, tuft, and proportions in every panel.

## PROP CONTINUITY

CYLINDER (obj_02):
- A hollow weathered wooden cylinder — open at both ends, hand-carved,
  light-brown bark texture, roughly the size of Ollie's head.
- Ollie found it half-submerged at the waterline.
- Same cylinder across panels 2–6.

## CONTINUITY RULES

- The same pond edge, ledge, and waterline in every panel.
- The same golden-hour direction and lighting color.
- The same Ollie in every panel.
- The same cylinder across panels 2–6.
- No extra or duplicate characters.
- No teleport jumps; camera and character movement read as continuous.

## SEQUENCE PROGRESSION

- Panel 1: Establish the pond edge at golden hour with Ollie small on the
  ledge (take begins).
- Panel 2: Move closer — Ollie lifts the hollow cylinder from the water.
- Panel 3: Reveal the cylinder rim as Ollie raises it to his eye.
- Panel 4: Capture a close-up of his widening-eyed reaction through the
  tube — the underwater world glimpsed.
- Panel 5: Emphasize the cylinder rim as the idea ignites on his face.
- Panel 6: Settle on a warm concluding composition of Ollie grinning
  (take ends).

## PANEL DIRECTIONS

### PANEL 1 — ESTABLISH

(top left). Camera positioned several metres back from the ledge, low
angle, looking across the glassy pond. Extreme-wide composition showing
the complete pond edge, flat mossy ledge, clover patches, gerberas, and
overhanging leaves. Ollie sits small on the ledge, facing screen-left
toward the water. The environment dominates the frame. Strong leading
lines from the ledge and waterline guide the eye toward Ollie. Curious,
quiet, warm golden-hour atmosphere.

### PANEL 2 — MOVE CLOSER

(bottom left). Camera has moved significantly closer while remaining at
the ledge, maintaining the same viewing direction. Wide cinematic
composition. Ollie is now clearly readable on the stone ledge, lying
prone at the waterline, paws reaching forward. Show the moss, water
ripples, and the cylinder's rim. The composition reads as a natural
continuation of Panel 1, not a new location.

### PANEL 3 — REVEAL PROP

(top middle). Camera at Ollie's waist height, three-quarter view. Ollie
lies prone on the ledge, occupying the right third of the frame, the
hollow wooden cylinder clearly visible in the foreground — its open rim
facing camera. The glassy pond recedes behind him. Warm golden-hour light
catches his fur, the cylinder's bark texture, and the wet ledge. This
panel is where the prop becomes the visual focus.

### PANEL 4 — REACTION

(bottom middle). Tight close-up. Camera close to Ollie's face, slightly
below eye level. Ollie peers through the cylinder at the underwater
world; his eyes widen, catching the refracted light. The cylinder rim
may partially enter the foreground. Background details become softly
blurred while preserving the warm golden-hour color and visual identity
of the location. This panel is the emotional peak of the take.

### PANEL 5 — EMPHASIZE PROP

(top right). Camera at chest height, three-quarter angle. Ollie proudly
holds up the same hollow cylinder, rim catching the warm golden light.
Ollie's expression is proud and delighted — the lightbulb moment. Keep
the ledge, waterline, and clover recognizable behind him. The
composition emphasizes the relationship between Ollie and the cylinder.

### PANEL 6 — CONCLUSION

(bottom right). Camera slightly wider than Panel 5, medium composition.
Ollie sits naturally on the sunlit ledge, grinning warmly while holding
the cylinder. Use the ledge and waterline as leading lines toward him.
The final frame feels peaceful, emotionally warm, and complete,
visually resolving the generation.

## RENDERING STYLE

High-fidelity stylized 3D CGI feature animation. Soft cream fur with
visible strand detail, tactile physical shaders, subsurface scattering.
Detailed bark and moss materials. Cinematic global illumination. Natural
depth of field. Warm golden-hour volumetric atmosphere. Sunlit pristine
pond-edge environment, materials, and environmental details. Cinematic
composition with clear foreground, middle-ground, and background
separation. The six panels should feel like frames from the same
animated film.

## HARD EXCLUSIONS

No text of any kind. No numbers. No labels. No captions. No subtitles. No
speech bubbles. No timecodes. No watermarks. No logos. No invented
characters. No duplicate characters. No duplicated panels. No split scenes
inside a panel. No overlapping panels. No blank panels. No decorative
storyboard graphics. No frames inside the panels. No gutter text.

## FINAL CONTINUITY CHECK

Preserve character identity, fur color, proportions, architecture, light
direction, and prop scale across all six panels. Track the cylinder's
position panel to panel (waterline → lifted → raised to eye → held up).
Each panel shows one distinct frozen moment — believable paw grips, foot
placement, natural wrist angles, object contact, depth, and occlusion. No
duplicated props, extra limbs, impossible reaches, floating objects,
mirrored layouts, blank cells, or repeated adjacent compositions.
```
