# Storyboard sheet spec (one sheet per Minimax generation) — for Agent 4

Agent 4 reads this spec and composes ONE GPT Image 2 (Replicate) prompt per
**generation** that paints that generation's clean panel grid. The prompt text
is saved to `<run_dir>/image_prompts/<scene>/storyboard_sheet_<gen>.txt`;
`build_images.py` dispatches it with the location lock (optional) + previous
sheet + character sheets as edit references. For fast-paced short-form work,
no location lock is attached; the previous sheet chain provides the world.

This is a **spec**, not a fill-in template. Agent 4 turns one generation block
of `storyboard_<scene>.md` (Agent 3's plan) into a single prompt that produces
the sheet image. The sheet is NOT cropped or upscaled — it is attached
verbatim as the Minimax H3 reference image for that generation's render, so
the sheet IS the visual contract: composition, framing, character appearance,
environment, and sequence progression.

## Layout (load-bearing — the Minimax render depends on it)

- The grid is the generation's `panel_grid` (e.g. `2x3` = 2 rows × 3 columns),
  row-major: Panel 1 = row 1 col 1, ... left→right, top→bottom.
- Panel order = time order. Panels belonging to one shot form a readable
  progressive motion morph; a shot boundary (`hard_cut`) may open on a new
  framing.
- Sheet size is **3840×2160** landscape (Replicate); every cell equal-sized,
  16:9, fully painted.
- **Clean panels only.** Use only thin, straight, 4-pixel white or black
  gutters. NO text, NO timecodes, NO panel numbers, NO captions, NO labels,
  NO watermarks — all timing/camera/sound information lives in the Minimax
  timeline prompt, not in the image. No rounded corners, drop shadows,
  frames, decorative separators, overlapping panels, blank cells, or variable
  cell sizes.

## Continuity (this is the whole point)

- Within a shot, adjacent panels are consecutive animation keys: same cast,
  geography, screen direction, lighting — pose/expression/position visibly
  advancing. No identical twin panels; no teleport jumps.
- Across a `hard_cut` shot boundary, the framing may change (new angle/shot
  size) but world, cast identity, wardrobe, and lighting logic stay locked.
- The FIRST panel of generation gK (K>1) must be paintable as a continuation
  of the previous generation's LAST panel (same world-state) — the previous
  sheet is attached as a reference for exactly this.
- Character identity, wardrobe, and proportions must be perfectly consistent
  across all panels, matching the attached character sheets (sheets retexture
  identity only; the storyboard plan wins for pose/composition/cast count).

## Prompt structure Agent 4 should produce

Describe the generation as a **cinematic pre-production storyboard sheet**,
not a flat contact sheet. GPT Image 2 will compose the panels; your job is to
give it the right visual narration.

1. **Grid + format line.**
   "A text-free cinematic pre-production storyboard sheet of <N> panels in a
   <R> rows × <C> columns landscape grid on a 3840×2160 page, thin 4px straight
   white or black gutters, equal 16:9 cells, no text, numbers, or labels of any
   kind." For micro-shot pacing, prefer grids like `3x3`, `2x4`, `3x4`, or
   `4x3` so each 1.5–3.0s shot can have its own distinct camera setup.
2. **High-level scene synopsis + emotional arc.** Two or three sentences
   describing the place, the characters, and the dramatic progression in time
   order. Write like a film director describing the sequence: "... first we see
   the baby discover the egg from a wide tracking shot, then we push in tight as
   it cracks, then the dino's face fills the frame."
3. **Shot variety directive (important).** Explicitly ask for varied cinematic
   shot sizes and angles across the panels: wide establishing shots, medium
   shots, medium close-ups, close-ups, over-the-shoulder, low angles, profile
   shots. Avoid six identical framings. Each panel should feel like a different
   camera setup from a real animation storyboard.
4. **Visual style + continuity locks.** Pixar-quality 3D, warm or cool
   lighting, character descriptions, and a note to keep the sequence
   progressively readable.
5. **Negative/forbidden line.** no text, numbers, timecodes, labels, captions,
   watermarks, speech bubbles, blank cells, twin panels, invented characters,
   duplicated poses between adjacent panels, rounded corners, drop shadows,
   frames, decorative layouts, overlapping panels, or cells of different sizes.

## Reference roles (attached by build_images.py, in order)

1. Location lock for the scene's `location_ref_id` (world geography anchor).
2. Previous sheet (the same scene's previous generation, or the last
   generation of the previous scene) — cross-generation continuity.
3. Character sheets for the scene cast (identity retexture).

Agent 4 does NOT need to name the reference images in the prompt; the backend
attaches them. Agent 4 only writes the panel/scene description text above.
