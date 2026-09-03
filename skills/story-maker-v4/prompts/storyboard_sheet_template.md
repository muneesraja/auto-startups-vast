# Storyboard sheet spec (one sheet per Minimax generation) — for Agent 4

Agent 4 reads this spec and composes ONE GPT Image 2 (Replicate) prompt per
**generation** that paints that generation's clean panel grid. The prompt text
is saved to `<run_dir>/image_prompts/<scene>/storyboard_sheet_<gen>.txt`;
`build_images.py` dispatches it with the location lock (optional) + previous
sheet + character sheets as edit references. The sheet is the reference image
for the Minimax H3 video render, so it must be visually readable and
continuity-locked.

This is a **spec**, not a fill-in template. Agent 4 turns one generation block
of `storyboard_<scene>.md` (Agent 3's plan) into a single prompt. The sheet is
NOT cropped or upscaled — it is attached verbatim as the Minimax H3 reference
image for that generation's render, so the sheet IS the visual contract:
composition, framing, character appearance, environment, and sequence
progression.

When a `spatial_plan_<scene>.md` exists, `build_images.py` materializes a
**SPATIAL CONTINUITY BIBLE** at the **top** of the prompt file before the paid
image call. Agent 4 writes the creative sections (CANVAS, SEQUENCE
PROGRESSION, PANEL DIRECTIONS, RENDERING STYLE, HARD EXCLUSIONS) and must
**not** manually author the generated spatial sections.

## Layout (load-bearing — the Minimax render depends on it)

- **Canvas**: 3840×2160 landscape (4K).
- **Default grid `3x2`**: 3 rows × 2 columns = 6 panels. The left column is the
  generation's **beginning**, the right column is the **end**. Within each
  column, panels read top-to-bottom.
- **Alternative grid `3x3`**: 3 rows × 3 columns = 9 panels for longer
  generations. The left column is the **beginning**, middle column is the
  **middle**, right column is the **end**. Each cell is exactly 1280×720, which
  is a true 16:9 panel.
- **Panel numbering is column-major**: Panel 1 = row 1 col 1, Panel 2 = row 2
  col 1, Panel 3 = row 3 col 1, Panel 4 = row 1 col 2, Panel 5 = row 2 col 2,
  Panel 6 = row 3 col 2. This means time flows down each column, then left to
  right across columns.
- **Cells are equal rectangular panels**, separated by thin 4px straight black
  or white gutters. They fill the entire canvas. Do **not** claim cells are
  16:9 unless the grid divides 3840×2160 into true 16:9 rectangles (e.g.
  3x3 → 1280×720).
- **NO text, NO timecodes, NO panel numbers, NO captions, NO labels, NO
  watermarks, NO speech bubbles, NO decorative frames, NO overlapping panels,
  NO blank cells, NO cells of different sizes.** All timing/camera/sound info
  lives in the video prompt, not in the image.

### Exact cell dimensions

| grid | rows | cols | cell size (px) | cell aspect |
|------|------|------|----------------|-------------|
| 3x2  | 3    | 2    | 1920×720       | 8:3         |
| 2x3  | 2    | 3    | 1280×1080      | ~4:3        |
| 3x3  | 3    | 3    | 1280×720       | 16:9        |
| 2x4  | 2    | 4    | 960×1080       | 8:9         |
| 4x3  | 4    | 3    | 1280×540       | 64:27       |

Use `3x2` as the default. If you want true 16:9 cells and need 9 panels, use
`3x3`.

## Prompt structure Agent 4 should produce

Keep the hierarchy. Immutable facts first, creative direction second, surgical
negatives last.

```
CANVAS
SCENE BIBLE
CHARACTER BIBLE
PROP CONTINUITY (if props matter)
CONTINUITY RULES
SEQUENCE PROGRESSION
PANEL DIRECTIONS
RENDERING STYLE
HARD EXCLUSIONS
```

### 1. CANVAS

One paragraph stating:
- "3840×2160 text-free cinematic pre-production storyboard sheet"
- Grid dimensions and exact panel count
- PANEL MAP (literal text diagram)
- Gutter style and thickness
- Cell size if relevant
- That all cells are fully painted, equal-sized, and touch the gutters cleanly

### 2. SCENE BIBLE

Global facts that do not change panel-to-panel. Extract from the storyboard
and any spatial plan:

- **Setting**: one or two sentences describing the location, time of day,
  weather/atmosphere.
- **Lighting**: direction, color, quality (e.g. "warm golden-hour sunset from
  screen-left, long soft shadows, amber bounce on mud walls").
- **Geography / landmarks**: list the key architectural or environmental
  landmarks and their relationships. Keep it spatially consistent.
- **Atmosphere / mood**: the emotional color of the whole generation.

### 3. CHARACTER BIBLE

Per on-screen character, list identity locks that must remain identical across
all panels:

- Name + `cid` if needed
- Age, ethnicity, body type, proportions
- Wardrobe (exact garments, colors, patterns)
- Hairstyle (exact style, accessories)
- Distinguishing features
- Where the character begins and ends the generation (per spatial plan)

Do **not** repeat full turnaround sheets here; the character reference images are
attached separately. This section is only for the in-shot identity lock.

### 4. PROP CONTINUITY

If the scene has important props (e.g. a toy clay pot, a stick, a lantern):

- List the prop and its appearance.
- State when it first appears and how it persists across panels.
- Note any transformations (shatters, drops, etc.) and in which panel they
  happen.

### 5. CONTINUITY RULES

Bullet list of invariants. Example:

- Same house architecture and materials in every panel.
- Same red-oxide thinnai and courtyard geography.
- Same sunset direction and lighting color.
- Same Kayal: face, hair, clothing, proportions.
- Same Mother: saree, hair, proportions.
- Same toy pot across panels 3–6.
- No duplicate characters.
- No teleport jumps; movement is continuous.

### 6. SEQUENCE PROGRESSION

One sentence per panel describing its narrative function and place in the
generation. This gives the model the temporal arc. Example for `3x2`:

- Panel 1: Establish the peaceful village courtyard at sunset.
- Panel 2: Move closer to Kayal playing on the thinnai.
- Panel 3: Reveal the toy pot and her playful activity.
- Panel 4: Capture her delighted reaction close-up.
- Panel 5: Emphasize the pot as she holds it up.
- Panel 6: Settle on a warm concluding composition.

### 7. PANEL DIRECTIONS

One subsection per panel. Name each panel as a **beat**, not a shot number.
Use `### PANEL N — BEAT NAME`. Each panel description should include:

1. **Panel position**: `(top left)`, `(middle left)`, `(bottom left)`,
   `(top right)`, etc. Use the column-major map.
2. **Camera geometry**: concrete spatial description instead of shot-size
   jargon. E.g.:
   - "camera positioned several metres back in the courtyard, low angle,
     looking up at the house facade, extreme wide"
   - "camera at Kayal's chest height, 3/4 view, 50mm-like perspective,
     framed from the waist up"
   - "camera close to Kayal's face, slightly below eye level, tight close-up
     on her expression"
3. **Staging**: who is in the panel, where they are, what they are doing, their
   expression/pose.
4. **Action / emotion**: the beat this panel captures. Use concrete visual
   verbs. Do not soften emotion from the storyboard action field.
5. **Landmarks / props**: which must be visible and which must not, if relevant.

Avoid stacking cinematography terms (`medium shot, rule of thirds, depth,
visual hierarchy`). Instead, describe the resulting image:

**Don't:**
> Panel 3 (top right, medium shot, rule of thirds and depth): Kayal sits on the
> thinnai with the toy pot.

**Do:**
> Panel 3 (top right): camera at Kayal's waist height, three-quarter view. Kayal
> sits cross-legged on the red-oxide thinnai, occupying the right third of the
> frame, the painted terracotta toy pot clearly visible in the foreground. The
> whitewashed mud wall recedes behind her. Warm sunset light catches her face,
> the pot, and the polished verandah floor.

### 8. RENDERING STYLE

Describe the visual attributes, not a brand/style reference. E.g.:

- High-end feature-animation 3D rendering.
- Stylized but believable child proportions.
- Rich physically based materials.
- Soft subsurface scattering on skin.
- Detailed fabric and terracotta materials.
- Cinematic global illumination.
- Natural depth of field.
- Warm golden-hour volumetric atmosphere.
- Authentic South Indian Tamil village architecture, materials, and props.
- Cinematic composition with clear foreground / middle-ground / background
  separation.

**Do not use** "Pixar-quality", "Pixar-style", "Disney-style", or other brand
references.

### 9. HARD EXCLUSIONS

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

Remove low-value items like "no rounded corners" or "no drop shadows" unless you
have actually seen the model produce them.

## Spatial Continuity Bible (materialized by build_images.py)

When a `spatial_plan_<scene>.md` exists, `build_images.py` inserts a generated
**SPATIAL CONTINUITY BIBLE** at the very top of the prompt file (after any
`ref_images:` line). It contains:

- **ENVIRONMENT BIBLE**: generation geography, lighting, landmarks, world axis.
- **CONTINUITY RULES**: character start/end positions, movement constraints,
  landmark visibility rules per panel range.
- **PANEL STAGING**: per-shot camera zone, facing, zoom translated into
  geometry, and subject placement/facing for each panel range.

Agent 4 must **not** manually author this block. The spatial plan data is the
source of truth for geography, positions, and landmark visibility. Agent 4's
PANEL DIRECTIONS should align with the materialized staging and use the same
landmarks / zones, but may add emotion, action, and visual emphasis.

## Example prompt (3x2 default, g1 of a peaceful village scene)

```
ref_images: loc_01, char_01

A text-free cinematic pre-production storyboard sheet. 3840×2160 landscape
page. Exactly six fully painted, equal rectangular panels arranged in a
3×2 grid (3 rows × 2 columns). Column-major numbering: down the left column,
then down the right column.

PANEL MAP:
Top row:    [Panel 1] [Panel 4]
Middle row: [Panel 2] [Panel 5]
Bottom row: [Panel 3] [Panel 6]

Thin 4px straight black gutters. No outer decorative frame. Panels touch the
gutters cleanly. No text, numbers, labels, captions, watermarks, speech bubbles,
blank cells, or decorative graphics.

## SCENE BIBLE

SETTING: A peaceful traditional South Indian Tamil village house at golden
sunset. The house is whitewashed mud construction with a raised polished
red-oxide verandah thinnai along the front wall. The courtyard has clean
earthen ground, several earthenware pots, a simple wooden doorway, and distant
coconut palms.

LIGHTING: Warm amber golden-hour sunlight coming from screen-left, long soft
shadows, rich warm bounce light on the red-oxide floor and mud walls. The same
sun direction, color, and quality across every panel.

LANDMARKS: whitewashed mud house facade; raised polished red-oxide thinnai;
wooden doorway into the house; clean earthen courtyard; distant coconut palms.

ATMOSPHERE: Calm, innocent, warm, quiet village evening.

## CHARACTER BIBLE

KAYAL (char_01):
- Six-year-old Tamil village girl.
- Childlike proportions, dark expressive eyes.
- Yellow blouse and maroon pavadai sattai with red ribbon details.
- Two messy oiled pigtails tied with red ribbons.
- Bare feet or simple sandals.
- Same face, hairstyle, clothing, and proportions in every panel.

## CONTINUITY RULES

- The same whitewashed mud house, thinnai, courtyard, and doorway in every
  panel.
- The same golden-hour sunset direction and lighting color.
- The same Kayal in every panel.
- No extra or duplicate characters.
- No teleport jumps; camera and character movement read as continuous.

## SEQUENCE PROGRESSION

- Panel 1: Establish the peaceful village courtyard at sunset with Kayal
  small on the thinnai.
- Panel 2: Move closer to Kayal; show her happily playing with a toy pot.
- Panel 3: Reveal the toy pot and her stirring motion in the foreground.
- Panel 4: Capture a close-up of her delighted, laughing expression.
- Panel 5: Show her proudly holding the same pot up toward the warm light.
- Panel 6: Settle on a warm concluding medium composition of Kayal and the pot.

## PANEL DIRECTIONS

### PANEL 1 — ESTABLISH

(top left). Camera positioned several metres back in the courtyard, low angle,
looking up at the front of the house. Extreme-wide composition showing the
complete whitewashed mud house facade, raised red-oxide thinnai, courtyard,
wooden doorway, and distant coconut palms. Kayal sits small on the thinnai,
facing screen-left. The environment dominates the frame. Strong leading lines
from the courtyard and verandah guide the eye toward Kayal. Peaceful, quiet,
warm golden-sunset atmosphere.

### PANEL 2 — MOVE CLOSER

(middle left). Camera has moved significantly closer while remaining in the
courtyard, maintaining the same viewing direction. Wide cinematic composition.
Kayal is now clearly readable on the red-oxide thinnai. Show the earthenware
pots, polished red-oxide floor, whitewashed mud wall, and distant coconut palms.
Kayal sits facing screen-left, stirring dry leaves in her miniature painted
terracotta toy pot with a tiny twig. The composition should read as a natural
continuation of Panel 1, not a new location.

### PANEL 3 — REVEAL ACTIVITY

(bottom left). Camera at Kayal's waist height, three-quarter view. Kayal sits
cross-legged on the thinnai, occupying the right third of the frame, the
painted terracotta toy pot clearly visible in the foreground. Her hands stir
dry leaves inside the pot. The whitewashed mud wall recedes behind her. Warm
sunset light catches her face, the pot, and the polished verandah floor. This
is the first panel where the playful activity becomes the visual focus.

### PANEL 4 — REACTION

(top right). Tight close-up. Camera close to Kayal's face, slightly below eye
level. Kayal laughs innocently while pretending to taste her imaginary food.
Her dark expressive eyes sparkle. Her messy oiled pigtails bounce naturally.
The toy pot and twig may partially enter the foreground. Background details
become softly blurred while preserving the warm golden-hour color and visual
identity of the location. This panel is an emotional reaction close-up.

### PANEL 5 — EMPHASIZE PROP

(middle right). Camera at chest height, three-quarter angle. Kayal proudly holds
up the same painted miniature terracotta toy pot. The pot catches the warm
golden sunset light. Kayal's expression is proud and delighted. Keep the
red-oxide thinnai and whitewashed mud wall recognizable behind her. The
composition emphasizes the relationship between Kayal and the pot.

### PANEL 6 — CONCLUSION

(bottom right). Camera slightly wider than Panel 5, medium composition. Kayal
sits naturally on the sunlit thinnai, smiling warmly while admiring the same
toy pot. Use the thinnai and house architecture as leading lines toward Kayal.
The final frame feels peaceful, emotionally warm, and complete, visually
resolving the sequence established in Panel 1.

## RENDERING STYLE

High-end feature-animation 3D rendering. Stylized but believable child
proportions. Rich physically based materials. Soft subsurface scattering on
skin. Detailed fabric and terracotta materials. Cinematic global illumination.
Natural depth of field. Warm golden-hour volumetric atmosphere. Authentic South
Indian Tamil village architecture, materials, props, and environmental details.
Cinematic composition with clear foreground, middle-ground, and background
separation. The six panels should feel like frames from the same animated film.

## HARD EXCLUSIONS

No text of any kind. No numbers. No labels. No captions. No subtitles. No
speech bubbles. No timecodes. No watermarks. No logos. No invented characters.
No duplicate characters. No duplicated panels. No split scenes inside a panel.
No overlapping panels. No blank panels. No decorative storyboard graphics. No
frames inside the panels.
```

## Action fidelity (mandatory — no softening)

Panel descriptions MUST faithfully preserve the **action verbs** and
**emotional intensity** from the storyboard's `action:` field. You are
transcribing the director's intent into visual language, not reinterpreting or
softening it.

- If the storyboard says "runs frantically," write "runs frantically" —
  never "walks" or "moves."
- If the storyboard says "points finger in anger," write "pointing finger
  in anger" — never "looks concerned."
- If the storyboard says "tears rolling down," write "tears rolling down
  her cheeks" — never just "remorseful."
- If the storyboard says "shatters into jagged shards," write "shattered
  into jagged shards" — never just "broken."

The validator checks that key action words from each shot's `action:` field
appear in the corresponding panel descriptions. Drift will be flagged.

## Reference roles (attached by build_images.py, in order)

When a `spatial_plan_<scene>.md` exists, the reference ordering is:

1. **Previous sheet** (the same scene's previous generation, or the last
   generation of the previous scene) — cross-generation continuity.
   For `g1` (no previous sheet), this slot is skipped.
2. **Location lock** for the scene's `location_ref_id` — attached for `g1`
   and for later generations whose spatial plan sets `location_reference:
   attach`; otherwise omitted.
3. **Character sheets** for the scene cast (identity retexture).
4. **Named extras** from the prompt's `ref_images:` line.

When no spatial plan exists (legacy), the ordering is: location lock →
previous sheet → character sheets → extras.

**No spatial anchor image is generated or attached.** The spatial plan's
geography, positions, facing, zoom, and landmark visibility are
deterministically materialized as a `SPATIAL CONTINUITY BIBLE` block at the
top of this prompt by `build_images.py` before the paid image call.

Agent 4 does NOT need to name the reference images in the prompt; the backend
attaches them. Agent 4 only writes the CANVAS, SCENE BIBLE, CHARACTER BIBLE,
PROP CONTINUITY, CONTINUITY RULES, SEQUENCE PROGRESSION, PANEL DIRECTIONS,
RENDERING STYLE, and HARD EXCLUSIONS sections.
