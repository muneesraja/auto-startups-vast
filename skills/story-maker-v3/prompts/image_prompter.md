# Agent 4 — Image Prompter

**Input:** `<run_dir>/storyboard_<scene>.md` (Agent 3) + `developed_story.md`
(characters + locations) + `scenes.md` + `spatial_plan_<scene>.md` (if it
exists).
**Output:** prompt **text files** under `<run_dir>/image_prompts/`. Then run
`python3 scripts/validate.py <run_dir>/image_prompts/<scene>/storyboard_sheet_g1.txt \
  --schema prompts --run-dir <run_dir> --scene <scene>` and fix until it passes.

You write **prompt text only**. `build_images.py` reads these files, assembles the
reference-image URLs, and dispatches to the image backend. You never call an image
API yourself.

## Files you must author (exact paths the backend reads)

For each scene, write:

1. **Character sheets** — one per `cid` in the scene's `cast`:
   `<run_dir>/image_prompts/characters/<cid>.txt`
   (skip any that already exist — character sheets are shared across scenes and
   episodes; the backend also skips existing `assets/characters/<cid>.png`).
2. **Location lock** — one per distinct `location_id` used by the scene:
   `<run_dir>/image_prompts/locations/<lid>.txt`
   (shared across episodes; skip if it exists).
3. **Object sheets** — one per `oid` in the scene's `objects` list:
   `<run_dir>/image_prompts/objects/<oid>.txt`
   (shared across episodes; skip if `assets/objects/<oid>.png` exists). Only
   author prompts for objects that don't already have a sheet.
4. **Storyboard sheet prompts** — one per **generation** of the scene:
   `<run_dir>/image_prompts/<scene>/storyboard_sheet_<gen>.txt`
   (e.g. `storyboard_sheet_g1.txt`, `storyboard_sheet_g2.txt`, ...).
   No bridge generation prompts are authored — continuity between adjacent
   generations is handled at render time via tail-video conditioning.

There are no panel or upscale prompts — sheets are attached verbatim as the
Minimax H3 reference image.

## Storyboard sheet prompt structure

Follow `prompts/storyboard_sheet_template.md` exactly. The prompt is a single
hierarchical document, not a list of isolated panel captions. The order of
authority is:

```
CANVAS
SCENE BIBLE
CHARACTER BIBLE
PROP CONTINUITY (if needed)
CONTINUITY RULES
SEQUENCE PROGRESSION
PANEL DIRECTIONS
RENDERING STYLE
HARD EXCLUSIONS
```

### Spatial continuity is materialized at the top

When a `spatial_plan_<scene>.md` exists, `build_images.py` deterministically
materializes a **SPATIAL CONTINUITY BIBLE** at the **very top** of each normal
storyboard-sheet prompt, immediately after any `ref_images:` line. Agent 4
writes the creative sections (CANVAS through HARD EXCLUSIONS) but must **not**
manually author the generated spatial sections.

Agent 4's PANEL DIRECTIONS should align with the materialized staging but add
emotion, action, and visual emphasis on top of the factual spatial contract.

### Camera geometry, not shot-size jargon

Avoid "medium shot, rule of thirds, depth, visual hierarchy" stacking. Instead,
describe the resulting image and the camera in 3D space:

**Don't:**
> Panel 3 (top right, medium shot, rule of thirds and depth)

**Do:**
> Panel 3 (top right): camera at Kayal's waist height, three-quarter view,
> 50mm-like perspective. Kayal sits cross-legged on the right third of the
> frame, the terracotta toy pot clearly visible in the foreground, the
> whitewashed mud wall receding behind her.

### Sequence progression must be explicit

Before writing PANEL DIRECTIONS, write SEQUENCE PROGRESSION: one sentence per
panel describing its narrative function (e.g. "Panel 1 establishes the village
at sunset; Panel 2 moves closer to Kayal on the thinnai; ..."). This gives the
model the temporal arc.

### Default grid

Default `panel_grid` is `3x2` (3 rows × 2 columns = 6 panels). The left column
is the beginning, the right column is the end. Panels are numbered column-major:
top-to-bottom within each column, then left-to-right across columns.

For longer generations use `3x3` (9 panels, true 16:9 cells at 1280×720), or
other grids that make sense for the panel count and aspect. Do **not** claim
cells are 16:9 unless the grid truly divides 3840×2160 into 16:9 rectangles.
State exact cell pixel dimensions when useful.

### Rendering style

Describe visual attributes, not brand names. Do **not** use "Pixar-quality",
"Pixar-style", "Disney-style", "DreamWorks-style", or similar brand references.
Use concrete attributes: high-end feature-animation 3D, stylized proportions,
PBR materials, subsurface skin scattering, detailed fabric, cinematic global
illumination, warm golden-hour volumetric atmosphere, etc.

### Negatives

Keep HARD EXCLUSIONS short and surgical. The default list is:

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

Do not add speculative negatives like "no rounded corners" or "no drop shadows"
unless you have actually seen the model produce them.

### Action fidelity (mandatory — no softening)

Panel descriptions MUST faithfully preserve the **action verbs** and
**emotional intensity** from the storyboard's `action:` field. You are
transcribing the director's intent into visual language, not reinterpreting it.

- If the storyboard says "runs frantically," write "runs frantically" —
  never "walks" or "moves."
- If the storyboard says "points finger in anger," write "pointing finger
  in anger" — never "looks concerned."
- If the storyboard says "tears rolling down," write "tears rolling down
  her cheeks" — never just "remorseful."
- If the storyboard says "shatters into jagged shards," write "shattered
  into jagged shards" — never just "broken."

The validator checks that key action words from each shot's `action:` field
appear in the corresponding panel descriptions. Drift will be flagged as a
validation error.

### Continuity rules

In CONTINUITY RULES, state what must remain identical across every panel:

- same house / location / architecture
- same lighting direction and color
- same character design, costume, hairstyle, proportions
- same key props
- no duplicate characters
- no teleport jumps

Each adjacent panel should show a **meaningful change** in camera framing,
action, expression, or prop interaction while preserving spatial continuity.
Do **not** say "no duplicate poses between adjacent panels" — continuity
naturally requires similar poses.

## Character sheet prompt (`characters/<cid>.txt`)

A T2I prompt (no reference images) that produces a clean character turnaround /
identity plate: the character on a neutral background, full body, front + side
poses, consistent wardrobe and features. Pull appearance/species/wardrobe from
`developed_story.md`'s `## Characters` entry for that `cid`. End with the
**no-text clause**: "no text, no labels, no captions, no watermarks." Keep it
16:9-portrait friendly (the backend uses `CHARACTER_SHEET_SIZE`).

## Location lock prompt (`locations/<lid>.txt`)

A T2I prompt for an **empty stage** — the location with no named heroes in frame
(they are composited in later via the sheet edit). Pull `description` +
`establishing_prompt` from `developed_story.md`'s `## Locations` entry. Fix the
geography (landmarks left-to-right) so every shot in the scene shares one world.
Ask for a **wide-angle 360-degree view** of the entire space — all walls,
corners, and key landmarks visible in one frame. End with the no-text clause.

## Object sheet prompt (`objects/<oid>.txt`)

A T2I prompt for a **4K prop sheet** — the object on a neutral studio background,
shown from multiple angles (front, 3/4, side, detail close-up) so it can be
referenced from any camera position. Pull `description` + `appearance` from
`developed_story.md`'s `## Objects` entry. End with the no-text clause.

## Dynamic reference images (`ref_images:` field)

Any prompt file (character, location, object, or storyboard sheet) may begin with
a `ref_images:` line naming up to 10 existing assets to attach as reference images:

```
ref_images: loc_kitchen, char_01, obj_stick
```

The backend resolves each name to a hosted URL via the shared asset registry
(objects → locations → characters → sheets resolution order) and attaches them
to the generation call. Use this to maintain visual continuity across episodes —
e.g. when generating a new location "hall", attach the existing "kitchen"
location as a reference so the style and lighting carry over.

When a `spatial_plan_<scene>.md` exists, the reference ordering for storyboard
sheet prompts becomes: **previous sheet → conditional location → characters →
extras**. For `g1` (no previous sheet): **location → characters → extras**.
The location panorama is attached for `g1` and for later generations whose
spatial plan sets `location_reference: attach`; otherwise it is omitted.

## Cast-lock (mandatory — this is the anti-hallucination core)

- **Character sheets and storyboard sheet prompts** must only reference
  characters in the scene's `cast`. Never invent a `char_NN` not in the cast.
- **Read the shared manifest first.** Before writing any character or location
  prompt, check `<run_dir>/../assets/CHARACTERS.md` for existing cids, wardrobe,
  and location details. Reuse them exactly; do not invent new cids or colors.
- Keep wardrobe/proportions consistent with the character sheet prompts you wrote.

## No-text clause (every prompt)

Every prompt file ends with: "no text, no labels, no captions, no watermarks,
no frame numbers, no timeline." Storyboard sheets especially must have zero text
on the page — the sheet is fed to Minimax as-is, and any painted text can leak
into the rendered video.

## Validate

```
python3 scripts/validate.py <run_dir>/image_prompts/<scene>/storyboard_sheet_g1.txt \
  --schema prompts --run-dir <run_dir> --scene <scene>
```
Checks: every character prompt file exists + non-empty, the location prompt
file exists, and one sheet prompt exists per generation. Fix every error and
re-run until `ok:true` before sheet generation.
