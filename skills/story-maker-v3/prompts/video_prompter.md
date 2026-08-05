# Agent 5 — Minimax Video Prompter

**Input (per generation):** the generation's rendered storyboard sheet
(`storyboard_sheet_<scene>_<gen>.png` — **Read the image**; describe what was
actually drawn, not what you wished for), `storyboard_<scene>.md`,
`developed_story.md` (character/location appearance), the episode context
(what the previous generation/scene ended on), and
[`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md).
**Output:** `<run_dir>/video_prompts/<scene>_<gen>.txt` — the exact text sent
to Minimax H3 with the sheet attached as the reference image. Then run
`python3 scripts/validate.py video_prompts/<scene>_<gen>.txt --schema video_prompt --run-dir <run_dir> --scene <scene>`
and fix until it passes.

## Job

Write one dragon-style timeline prompt (see the bible's skeleton, modeled on
`Research/minimax-h3/dragon/story-board-2.md`) per generation:

1. **Reference block** — "Use the provided storyboard as the exact visual
   guide..."; maintain-appearance locks naming each character BY APPEARANCE
   (never `char_NN` — the validator rejects internal ids) and the location;
   behavior locks where drift is likely.
2. **Style block** — short one-quality-per-line lines matching the episode's
   render style.
3. **`Timeline`** — one `SHOT N — a–b s (Continuous Shot)` block per
   storyboard shot, with **generation-local** timecodes (shot start minus
   generation start; the last shot ends at the generation's duration, <= 15s).
   Inside each shot: action lines in order, dialogue inline in quotes, sound
   direction, then explicit camera lines using the bible's motion vocabulary.
   Separate shots with the literal line `Hard cinematic cut.` End with a
   `Final frame:` description.
4. **`Negative Prompt`** — the standard identity/deformation/text block plus
   scene-specific bans.

## Rules

- **Continuity is authored here.** If the storyboard marks the first shot
  `continuous`, open with "Continue directly from the previous scene." and
  restate the world-state it continues from. If `hard_cut`, open fresh.
- **The sheet wins.** If the drawn sheet deviates from the plan (pose, prop,
  count), describe the sheet. Do not fight the reference image.
- SHOT count and time ranges must match the storyboard generation exactly —
  the validator enforces both.
- Direct the audio in every shot (Minimax generates native stereo audio).
- Keep lines short; one visible event per line.
