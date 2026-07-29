# Storyboard album sheet spec (4 rows × 2 cols) — for Agent 4

Agent 4 reads this spec and composes ONE GPT Image 2 (Replicate) prompt that
paints the full 4×2 album sheet for a scene. The prompt text Agent 4 writes is
saved to `<run_dir>/image_prompts/<scene>/storyboard_sheet.txt`; `build_images.py`
dispatches it with the location lock + previous sheet + character sheets as edit
references.

This is a **spec**, not a fill-in template. Agent 4 turns the scene's
`storyboard_<scene>.md` (Agent 3's 4×2 plan) into a single prompt that produces the
sheet image. The sheet is then cropped into 8 panels and each panel is upscaled.

## Layout (load-bearing — the renderer depends on it)

- Exactly **4 rows × 2 columns** (row-major: left→right, top→bottom).
  - Panel 1 = row 1 col 1, Panel 2 = row 1 col 2
  - Panel 3 = row 2 col 1, Panel 4 = row 2 col 2
  - Panel 5 = row 3 col 1, Panel 6 = row 3 col 2
  - Panel 7 = row 4 col 1, Panel 8 = row 4 col 2
- **Session layout:** Each LTX Director session is still 4 panels, but visually it
  occupies a 2×2 sub-block:
  - Session 1 = Panels 1-4 (visual rows 1-2, cols 1-2)
  - Session 2 = Panels 5-8 (visual rows 3-4, cols 1-2)
- Sheet size is **2160×3840** portrait (Replicate). Divided 4×2, each cropped cell
  is 1080×1920 and then recomposed to a true 16:9 panel during the upscale step.
- Thin uniform black or white gutters only as separators. No text, labels, captions,
  shot numbers, timelines, or watermarks anywhere on the page.
- Every cell fully painted with scene content — no blank/placeholder cells.

## Continuity (this is the whole point)

- **Each LTX session (4 panels) is a continuous FLF2V chain.** Adjacent panels in a
  session share a boundary frame: the END pose of panel N is the START pose of panel
  N+1 (same cast, geography, screen direction, lighting). Paint a readable
  **progressive motion morph** left→right and top→bottom across the four panels of a
  session.
- **A new session block is a cut** (a new LTX session). Session 2 does NOT need to
  morph from session 1's last panel.
- **No identical twin panels** in a session; no teleport jumps between adjacent
  panels.
- **Characters must visibly move / change between columns.** If the same character
  appears in two adjacent panels, their pose, expression, head turn, limb position,
  or screen position must shift enough that the frames read as consecutive animation
  keys, not a duplicated still.
- Character identity, wardrobe, and proportions must be perfectly consistent across
  all 8 panels, matching the attached character sheets (sheets retexture identity
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

Agent 4 writes the panel descriptions in row-major order (Panel 1 … Panel 8), as a
single prompt, so the model lays them out in the 4×2 grid in that order.

## Prompt structure Agent 4 should produce

1. One line: "A text-free Pixar-style photo album / contact sheet of 8 cinematic
   animation stills in a 4 rows × 2 columns portrait grid on a 2160×3840 page,
   thin gutters, no text or labels."
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
   twin panels, invented characters, duplicated poses between adjacent panels.

## Reference roles (attached by build_images.py, in order)

1. Location lock for the scene's `location_ref_id` (world geography anchor).
2. Previous scene's storyboard sheet (cross-scene continuity — same world).
3. Character sheets for the scene cast (identity retexture).

Agent 4 does NOT need to name the reference images in the prompt; the backend
attaches them. Agent 4 only writes the panel/scene description text above.
