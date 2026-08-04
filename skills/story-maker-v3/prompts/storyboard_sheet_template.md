# Storyboard album sheet spec (3 rows × 3 cols) — for Agent 4

Agent 4 reads this spec and composes ONE GPT Image 2 (Replicate) prompt that
paints the full 3×3 album sheet for a scene. The prompt text Agent 4 writes is
saved to `<run_dir>/image_prompts/<scene>/storyboard_sheet.txt`; `build_images.py`
dispatches it with the location lock + previous sheet + character sheets as edit
references.

This is a **spec**, not a fill-in template. Agent 4 turns the scene's
`storyboard_<scene>.md` (Agent 3's 3×3 plan) into a single prompt that produces the
sheet image. The sheet is then cropped into 9 panels and each panel is upscaled.

## Layout (load-bearing — the renderer depends on it)

- Exactly **3 rows × 3 columns** (row-major: left→right, top→bottom).
  - Panel 1 = row 1 col 1, Panel 2 = row 1 col 2, Panel 3 = row 1 col 3
  - Panel 4 = row 2 col 1, Panel 5 = row 2 col 2, Panel 6 = row 2 col 3
  - Panel 7 = row 3 col 1, Panel 8 = row 3 col 2, Panel 9 = row 3 col 3
- **Session layout:** each row is one LTX Director session (3 panels: start, middle, end).
  - Session 1 = Panels 1-3 (row 1)
  - Session 2 = Panels 4-6 (row 2)
  - Session 3 = Panels 7-9 (row 3)
- Sheet size is **3840×2160** landscape (Replicate). Divided 3×3, each cell is
  exactly **1280×720** (16:9) and needs no recomposing — only a pure upscale.
- Use only thin, straight, 4-pixel white or black gutters. No colored, blurred,
  invisible, or decorative separators; no rounded corners, drop shadows, frames,
  labels, text, watermarks, overlapping panels, or variable cell sizes. Every cell
  must be the same size and fully painted with scene content — no blank/placeholder cells.

## Continuity (this is the whole point)

- **Each LTX session (3 panels) is a continuous chain: start → middle → end.**
  Adjacent panels in a row share a boundary pose: the end of panel 1 is the start
  of panel 2, and the end of panel 2 is the start of panel 3 (same cast, geography,
  screen direction, lighting). Paint a readable **progressive motion morph**
  left→right across the three panels of a row.
- **A new row is a cut** (a new LTX session). Row 2 and row 3 do NOT need to morph
  from the previous row's last panel.
- **No identical twin panels** in a row; no teleport jumps between adjacent
  panels.
- **Characters must visibly move / change between columns.** If the same character
  appears in two adjacent panels, their pose, expression, head turn, limb position,
  or screen position must shift enough that the frames read as consecutive animation
  keys, not a duplicated still.
- Character identity, wardrobe, and proportions must be perfectly consistent across
  all 9 panels, matching the attached character sheets (sheets retexture identity
  only; the album layout wins for pose/composition/cast count).

## What each panel must convey (from Agent 3's storyboard_<scene>.md)

For each panel, Agent 4 folds in the corresponding Agent 3 cell:
- `characters_present` (who is in the panel — never add or omit vs the cell)
- `position_xy` + `depth_per_char` (spatial layout / foreground-background)
- `camera_angle` + `facing` + `angle` (camera and body orientation)
- `expression` + `mood` + `intent` (the emotional/beat content of the beat)
- `spatial_relation` (where every element sits relative to every other element —
  distances, screen sides, who touches what)
- `must_not_show` (exactly what the image must NOT contain — anti-deformation,
  anti-beat-jump, anti-hallucination)
- the inter-column `camera_motion_hint` (implied by the pose progression)

Agent 4 writes the panel descriptions in row-major order (Panel 1 … Panel 9), as a
single prompt, so the model lays them out in the 3×3 grid in that order.

## Prompt structure Agent 4 should produce

1. One line: "A text-free, strict regular contact sheet of 9 cinematic animation
   stills in a 3 rows × 3 columns landscape grid on a 3840×2160 page, thin 4px
   straight white or black gutters, equal 1280x720 cells, no text or labels."
2. Scene look/lighting/location anchor (from the scene's location lock + Agent 3).
3. Panel-by-panel descriptions, row-major. For every panel include:
   - **Spatial clause:** copy `spatial_relation` and expand it (positions, distances,
     which side of the frame, who is seated/standing, what touches what).
   - **Emotional/pose clause:** copy `expression`, `mood`, `intent`, `camera_angle`,
     and describe the exact visual beat — especially transitional moments (e.g.
     "tears still wet, crying just stopping, mouth only beginning to turn up").
   - **Negative/must_not_show clause:** copy `must_not_show` verbatim and add any
     physical impossibilities. This is the anti-deformation / anti-beat-jump clause.
   - **Inter-column motion clause:** explicitly state how this panel advances from the
     previous panel in the same session (e.g. "the parrot lifts off the shoulder and
     flaps a wing, the girl's head tilts 10 degrees further toward it, the dog takes
     one step closer"). Never allow identical poses across adjacent panels.
4. Character-consistency line: "Match the attached character sheets for identity,
   wardrobe, and proportions; keep cast count and poses exactly as described."
5. Negative/forbidden line: no text, labels, captions, watermarks, blank cells,
   twin panels, invented characters, duplicated poses between adjacent panels,
   rounded corners, drop shadows, frames, decorative layouts, overlapping panels,
   or cells of different sizes.

## Reference roles (attached by build_images.py, in order)

1. Location lock for the scene's `location_ref_id` (world geography anchor).
2. Previous scene's storyboard sheet (cross-scene continuity — same world).
3. Character sheets for the scene cast (identity retexture).

Agent 4 does NOT need to name the reference images in the prompt; the backend
attaches them. Agent 4 only writes the panel/scene description text above.
