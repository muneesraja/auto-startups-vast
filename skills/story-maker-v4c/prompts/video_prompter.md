# Agent 5 — MiniMax H3 Video Prompter

**Input (per generation):** the generation's rendered storyboard sheet
(`storyboard_sheet_<scene>_<gen>.webp` — **Read the image**; describe what was
actually drawn), `storyboard_<scene>.md`, `developed_story.md`, episode
context, [`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md),
[`creature_behavior.md`](creature_behavior.md), [`coverage.md`](coverage.md).
If the brief is an ad, also Read [`commercial_ad.md`](commercial_ad.md).
**Output:** `<run_dir>/video_prompts/<scene>_<gen>.txt`. Then run
`python3 scripts/validate.py video_prompts/<scene>_<gen>.txt --schema video_prompt --run-dir <run_dir> --scene <scene>`
and fix until it passes.

This is **image-to-video**. The sheet already defines subject, composition,
and style. Write motion, one camera sentence per shot, locks, sound fields,
and a viewer takeaway. Do not re-describe the still.

## Job

Complete the bible's pre-write pass (Context, Timeline+ending, Camera, Sound,
Constraints, S.C.E.N.E. + purpose). Then emit the validator-legal skeleton
from the bible:

1. I2VA lock — `@image1` (the provided **storyboard**) fully referenced at
   0.00s. Appearance + creature behavior + danger human locks. Takeaway line.
2. Tone style lines (grounded cinematic or stylized — not always Pixar).
3. `Timeline` with `integrated_multimodal_description:` and one
   `SHOT N — a–b s (Continuous Shot)` block per storyboard shot in
   **generation-local** seconds. Inner `[Shot 1]` has no timestamp; later
   shots `At 00:MM.SSS`. One action + environment reaction + one camera
   sentence. Dialogue as `(S1): <d>[English] ... </d>`. `Hard cinematic cut.`
   between shots unless this generation is a true one-take.
4. `Final frame:` deliberate settle.
5. `overall_soundscape:` and `non_diegetic_music:` (or `N/A`).
6. `Negative Prompt` — identity/deformation plus bible bans (pet-like
   wildlife, calm faces in danger, dutch canopy, idle orbits, extra fingers,
   invented speech/text, extra products).

## Rules

- **Continuity is authored here.** If the storyboard marks the first shot
  `continuous`, open with "Continue directly from the previous scene." and
  restate the world-state. If `hard_cut`, open fresh.
- **The sheet wins.** If the drawn sheet deviates from the plan, describe the
  sheet.
- SHOT count and time ranges must match the storyboard generation — the
  validator enforces both. Last SHOT must end at the generation duration
  (<= 15s).
- One camera sentence per shot (type + amplitude + speed). Follow
  `coverage.md`. No 1.5–3.0s viral micro-cut default; that pacing is
  `play_comedy` only.
- Creature locks from `creature_behavior.md`. In danger, humans are not calm.
- Ads: one job per generation; product label lock; hero hold on CTA gens.
- Never `char_NN`. Describe by appearance.
- GATE 2 regen: change **one** failure category from the bible repair table.
