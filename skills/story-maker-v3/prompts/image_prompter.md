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
   `<run_dir>/image_prompts/<scene>/panel_<r><c>.txt` for r,c in {1,2,3}×{1,2,3}
   (panel_11 .. panel_33 — 9 files).

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
a strict regular **3 rows × 3 cols** landscape album sheet (3840×2160 page,
thin 4px straight white or black gutters, equal 1280×720 16:9 cells, no text). Each
LTX session is one row of 3 panels (start, middle, end). Fold in the 9 Agent 3 cells
in row-major order — each panel naming its `characters_present`, depth, camera,
expression, beat, `spatial_relation`, and `must_not_show` — emphasizing the shared
boundary pose and visible progressive motion between adjacent panels in a row.
Reference roles (location lock → previous scene's sheet → character sheets) are
attached automatically by `build_images.py`; you do NOT name them in the prompt.

### Per-panel upscale prompt (`<scene>/panel_<r><c>.txt`) — **post-crop only**

These prompts are authored **after** the storyboard sheet has been generated and
panels have been cropped (after GATE 1). You must **Read** each 1280×720 crop PNG to see what was actually drawn before writing its prompt.

The crop is already 16:9, so the pipeline performs a pure upscale to
`PANEL_IMAGE_SIZE` (default 2048×1152). The mechanical lock in
`image_pipeline.py` instructs the model to preserve the exact composition, cast,
poses, camera, lighting, and background. Your prompt is appended to that lock and
must be **short** — one or two sentences of fine-detail / texture enhancement
that does not change the image.

**Rules (the validator rejects violations):**

1. **No `char_NN` tokens.** Do not name any character. The crop already has them;
   the model must not re-imagine who is in frame.
2. **No negative-cast phrasing.** Do not write "No humans", "no dog", "no extra
   characters", etc. Negative prompts cause the model to delete subjects.
3. **Enhance / texture only.** Describe polish that preserves the frame
   (e.g. "add cinematic lighting detail, sharpen edges, keep the composition
   exactly the same"). Do not re-frame, re-compose, or alter content.
4. **No composition, camera, or character instructions.** The mechanical lock
   already handles all of that. Your text is purely detail / finish guidance.

End with the no-text clause.

**Example good panel prompt:**
```
Add cinematic lighting detail and sharpen edges while preserving the exact
composition, cast, and pose. Keep the background texture consistent.
No text, no labels, no captions, no watermarks.
```

## Cast-lock (mandatory — this is the anti-hallucination core)

- **Character sheets and storyboard sheet prompts** must only reference
  characters in the scene's `cast`. Never invent a `char_NN` not in the cast.
- **Panel upscale prompts must NOT name any character at all.** The crop
  already contains the characters; the upscale model must not re-imagine who
  is in frame. The `panel_prompts` validator rejects any `char_NN` token.
- **Read the shared manifest first.** Before writing any character or location
  prompt, check `<run_dir>/../assets/CHARACTERS.md` for existing cids, wardrobe,
  and location details. Reuse them exactly; do not invent new cids or colors.
- Keep wardrobe/proportions consistent with the character sheet prompts you wrote.

## No-text clause (every prompt)

Every prompt file ends with: "no text, no labels, no captions, no watermarks,
no frame numbers, no timeline." Storyboard sheets especially must have zero text on
the page (the cropper depends on clean gutters).

## Validate

**Pre-generation (before Stage B sheet generation):**
```
python3 scripts/validate.py <run_dir>/image_prompts/<scene>/storyboard_sheet.txt \
  --schema prompts --run-dir <run_dir> --scene <scene>
```
Checks: every character prompt file exists + non-empty, the location prompt
file exists, and the sheet prompt exists. Fix every error and re-run until
`ok:true` before sheet generation.

**Post-crop (after GATE 1, before upscale):**
```
python3 scripts/validate.py <run_dir>/image_prompts/<scene>/panel_11.txt \
  --schema panel_prompts --run-dir <run_dir> --scene <scene>
```
Checks: all 9 `panel_<r><c>.txt` exist + non-empty, no `char_NN` tokens, no
negative-cast phrasing. Fix every error and re-run until `ok:true` before
running `build_images.py --upscale-only`.