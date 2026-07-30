# Agent 4 — Image Prompter

**Input:** `<run_dir>/storyboard_<scene>.md` (Agent 3) + `developed_story.md`
(characters + locations) + `scenes.md`.
**Output:** prompt **text files** under `<run_dir>/image_prompts/`. Then run
`python3 scripts/validate.py <run_dir>/image_prompts/<scene>/storyboard_sheet.txt \
  --schema prompts --run-dir <run_dir> --scene <scene>` and fix until it passes.

You write **prompt text only**. `build_images.py` reads these files, assembles the
reference-image URLs, and dispatches to the image backend. You never call an image
API yourself.

## Files you must author (exact paths the backend reads)

For each scene, write:

1. **Character sheets** — one per `cid` in the scene's `cast`:
   `<run_dir>/image_prompts/characters/<cid>.txt`
   (skip any that already exist — character sheets are shared across scenes; the
   backend also skips existing `assets/characters/<cid>.png`).
2. **Location lock** — one per distinct `location_id` used by the scene:
   `<run_dir>/image_prompts/locations/<lid>.txt`
   (shared; skip if it exists).
3. **Storyboard sheet prompt** — one per scene:
   `<run_dir>/image_prompts/<scene>/storyboard_sheet.txt`
4. **Per-panel upscale prompts** — one per panel:
   `<run_dir>/image_prompts/<scene>/panel_<r><c>.txt` for r,c in {1,2}×{1,2,3,4}
   (panel_11 .. panel_24 — 8 files).

## Content rules

### Character sheet prompt (`characters/<cid>.txt`)

A T2I prompt (no reference images) that produces a clean character turnaround /
identity plate: the character on a neutral background, full body, front + side
poses, consistent wardrobe and features. Pull appearance/species/wardrobe from
`developed_story.md`'s `## Characters` entry for that `cid`. End with the
**no-text clause**: "no text, no labels, no captions, no watermarks." Keep it
16:9-portrait friendly (the backend uses `CHARACTER_SHEET_SIZE`).

### Location lock prompt (`locations/<lid>.txt`)

A T2I prompt for an **empty stage** — the location with no named heroes in frame
(they are composited in later via the sheet edit). Pull `description` +
`establishing_prompt` from `developed_story.md`'s `## Locations` entry. Fix the
geography (landmarks left-to-right) so every shot in the scene shares one world.
End with the no-text clause.

### Storyboard sheet prompt (`<scene>/storyboard_sheet.txt`)

Follow `prompts/storyboard_sheet_template.md` exactly: a single prompt that paints
the full **4 rows × 2 cols** portrait album sheet (2160×3840 page, thin gutters, no
text). Each LTX session occupies a 2×2 sub-block (session 1 = rows 1-2, session 2
= rows 3-4). Fold in the 8 Agent 3 cells in row-major order — each panel naming its
`characters_present`, depth, camera, expression, beat, `spatial_relation`, and
`must_not_show` — emphasizing the shared boundary pose and visible progressive motion
between adjacent panels in a session. Reference roles (location lock → previous
scene's sheet → character sheets) are attached automatically by `build_images.py`;
you do NOT name them in the prompt.

### Per-panel upscale prompt (`<scene>/panel_<r><c>.txt`)

A short edit prompt that upscales one cropped panel to a clean 16:9 still. The panel
crop is passed as Image 1, the character sheets of that panel's
`characters_present` are attached as refs, and the scene's location lock is also
attached when the provider's reference budget allows (all by `build_images.py`).
Your prompt must contain the following clauses, in order:

1. **Composition lock (mandatory first clause):** start with an explicit
   anti-drift instruction such as: "Preserve the exact composition, camera angle,
   and 2D layout of the attached crop. Do not reframe, do not pan, do not zoom, do
   not add or remove any character, and do not flatten or replace the background.
   Only increase detail, clean edges, and add texture while keeping every figure in
   the same screen position." This is the primary defense against the upscale
   re-imagining the panel.
2. **Spatial clause:** copy the cell's `spatial_relation` field and expand it into
   a clear description of where every element sits relative to every other element
   (distances, which side of frame, who is seated/standing, what touches what, who is
   mounted/on the ground/above). Be physically explicit (e.g. "dog char_03 stays on
   the dirt ground, never on the horse").
3. **Background clause:** one sentence describing **only what is visible in this
   panel's crop** — not the full location. For a sky shot, say "sky and forest
   canopy below"; for an interior close-up, say "shelter wall behind". Never
   list location features that are off-screen in the crop (e.g. if the panel
   shows only sky, do NOT mention "dirt paths" or "wooden enclosures"). This
   prevents the model from redesigning the background by adding elements that
   were never in the crop.
4. **Emotional/pose clause:** copy the cell's `expression`, `mood`, `intent`, and
   `camera_angle` and describe the exact visual beat — especially for transitional
   moments (e.g. "tears still wet, crying just stopping, mouth only beginning to turn
   up").
5. **Negative/must_not_show clause:** copy the cell's `must_not_show` field verbatim,
   prefix it with "NEVER:" and add any physical impossibilities the crop may contain.
   This is the anti-deformation and anti-beat-jump clause.

End with the no-text clause.

## Cast-lock (mandatory — this is the anti-hallucination core)

- **Only reference characters that are in the panel's `characters_present`.** Never
  name a `char_NN` that is not in that cell. The validator rejects any `char_NN`
  token in a panel prompt that is not in the scene cast.
- Do not invent characters. If a panel is a solo close-up of `char_03`, the prompt
  names only `char_03`.
- Keep wardrobe/proportions consistent with the character sheet prompts you wrote.

## No-text clause (every prompt)

Every prompt file ends with: "no text, no labels, no captions, no watermarks,
no frame numbers, no timeline." Storyboard sheets especially must have zero text on
the page (the cropper depends on clean gutters).

## Validate

```
python3 scripts/validate.py <run_dir>/image_prompts/<scene>/storyboard_sheet.txt \
  --schema prompts --run-dir <run_dir> --scene <scene>
```
The validator checks: every character prompt file exists + non-empty, the location
prompt file exists, the sheet prompt exists, all 8 `panel_<r><c>.txt` exist +
non-empty, and no panel prompt references a `char_NN` outside the scene cast. Fix
every error and re-run until `ok:true` before Stage B image generation.