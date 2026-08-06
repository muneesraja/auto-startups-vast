# Agent 4 — Image Prompter

**Input:** `<run_dir>/storyboard_<scene>.md` (Agent 3) + `developed_story.md`
(characters + locations) + `scenes.md`.
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
   (skip any that already exist — character sheets are shared across scenes; the
   backend also skips existing `assets/characters/<cid>.png`).
2. **Location lock** — one per distinct `location_id` used by the scene:
   `<run_dir>/image_prompts/locations/<lid>.txt`
   (shared; skip if it exists).
3. **Storyboard sheet prompts** — one per **generation** of the scene:
   `<run_dir>/image_prompts/<scene>/storyboard_sheet_<gen>.txt`
   (e.g. `storyboard_sheet_g1.txt`, `storyboard_sheet_g2.txt`, ...).

There are no panel or upscale prompts — sheets are attached verbatim as the
Minimax H3 reference image.

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

### Storyboard sheet prompt (`<scene>/storyboard_sheet_<gen>.txt`)

Follow `prompts/storyboard_sheet_template.md` exactly: a single prompt that
paints that generation's strict regular `panel_grid` landscape sheet (3840×2160
page, thin 4px straight white or black gutters, equal 16:9 cells, ZERO text /
numbers / labels on the page). For fast-paced short-form work, prefer dense
grids like `3x3`, `2x4`, `3x4`, or `4x3` so each 1.5–3.0s micro-shot gets its
own panel. Fold in the generation's shots panel-by-panel in row-major order —
each panel naming its `characters_present`, framing, camera angle, and beat —
emphasizing visible progressive motion between adjacent panels of a shot and the
continuation from the previous generation's last panel.
Reference roles (location lock → previous sheet → character sheets) are
attached automatically by `build_images.py`; you do NOT name them in the prompt.

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
