# Agent 3 — Storyboard Planner (Minimax H3)

**Input:** `<run_dir>/scenes.md` (one scene at a time) + `developed_story.md`
+ the full **episode context** (previous scenes' storyboards, and the previous
episode's final state when this is episode 2+). Never author a storyboard
without that context loaded — Minimax prompts say things like "Continue
directly from the previous scene", so you must know exactly what that was.
**Output:** `<run_dir>/storyboard_<scene>.md` for each scene — the scene split
into **generations** (one Minimax H3 render each, max 15s) and **shots**.
Then run
`python3 scripts/validate.py storyboard_<scene>.md --schema storyboard --scenes-path <run_dir>/scenes.md`
and fix until it passes.

## Job

Split one scene's timeline into **generations**: each generation is ONE
Minimax H3 render, driven by ONE storyboard sheet (clean panel grid) plus a
timeline prompt. Inside a generation you plan **shots** (continuous camera
takes separated by hard cuts). Minimax renders at most **15 seconds** per
generation — that is the load-bearing constraint of this whole plan.

## The 15-second rule (load-bearing)

- A generation's duration is **5.0–15.0s**. Never more.
- **A shot must NEVER straddle a generation boundary.** If the next shot does
  not fit in the remaining seconds of the current generation, close this
  generation early (>= 5s) and move the whole shot to the next generation.
  Its panels move with it to the next generation's sheet.
- Generations are contiguous: g1 = 0.0→x, g2 = x→y, ... and the last one ends
  exactly at the scene's `target_seconds`.
- A generation boundary is always a cut in the final film (separate renders
  concatenated). Plan the first shot of the next generation to either continue
  the action (`continuous` — the prompt will say "Continue directly from the
  previous scene") or open on a fresh setup (`hard_cut`).

## Rules

- **Read the shared asset manifest first.** Before assigning `char_NN` IDs or
  wardrobe colors, read `assets/CHARACTERS.md` in the shared story assets
  folder. Reuse the existing cids and their exact wardrobe. Never invent a new
  `char_NN` not in the manifest.
- **Shots are contiguous within a generation** and together fill it exactly.
  For modern short-form / high-retention pacing, a typical 15s generation has
  **5–8 micro-shots**, each **1.5–3.0s**. Use `hard_cut` between most shots to
  drive rapid visual variety. A shot shorter than ~1.0s may be too brief; a shot
  longer than ~4.0s slows the pace. Exception: tender / dialogue-heavy beats.
- **`panels`**: each shot claims 1–4 panels of the generation's sheet, showing
  the shot's key poses in order. Panels are numbered 1..N in reading order
  across the whole sheet and each panel belongs to exactly one shot.
  `panel_grid: RxC` must satisfy R*C = total panels (3–12). Minimum grid is
  1x3, 2x2, 2x3, or 3x2 — never smaller. Larger grids (3x3, 2x4, 4x3, etc.)
  are encouraged for generations with more shots or key poses.
- **`camera`**: describe motion with the Minimax vocabulary (see
  [`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md)):
  Zoom In/Out, Push In/Pull Out, Pan Left/Right, Truck Left/Right, Tilt
  Up/Down, Pedestal Up/Down, Arc Shot, Tracking Shot, Static Shot, Shake
  Slightly/Strongly, POV, Roll Clockwise/Counterclockwise — optionally with
  amplitude (`with small/large amplitude`) and speed (`at slow/fast speed`).
  Multi-move shots are fine ("begin with a handheld tracking shot behind the
  baby, then arc around to a front three-quarter angle").
- **`characters_present` ⊆ scene `cast`.** Never invent a `char_NN` not in the
  scene's cast.
- **`audio` is real.** Minimax generates native stereo audio — plan the
  soundscape (footsteps, ambience, music cue) per shot, and put spoken lines
  in `dialogue`.
- **The handoff block is mandatory** (it seeds the next scene's opening).

## Output format (load-bearing — verbatim)

```
# Scene <scene_id> — <scene_title>
scene_id: <scene_id>
target_seconds: <int>
cast: [char_01, char_02]
location_ref_id: <lid>

## Generation g1 — 0.0-15.0s
duration_seconds: 15.0
panel_grid: 3x3

### Shot 1 — 0.0-1.5s (continuous)
panels: [1]
characters_present: [char_01]
action: Extreme close-up on the toddler's wide brown eyes peering curiously into the dark dusty basement.
camera: Push In fast on eyes.
audio: Heavy breathing, ambient basement hum.
dialogue:

### Shot 2 — 1.5-3.0s (hard_cut)
panels: [2]
characters_present: [char_01]
action: Low-angle tracking shot of the toddler's tiny feet in mismatched socks padding through dust past cardboard boxes.
camera: Low Angle Tracking Shot at fast speed.
audio: Soft padding footsteps on dust.
dialogue:

### Shot 3 — 3.0-5.0s (hard_cut)
panels: [3, 4]
characters_present: [char_01]
action: The toddler pushes aside a hanging canvas sheet; a golden light shaft illuminates a large speckled glowing egg.
camera: Handheld whip pan right to reveal the glowing egg.
audio: Fabric rustle, faint magical shimmer hum.
dialogue:

### Shot 4 — 5.0-6.5s (hard_cut)
panels: [5]
characters_present: [char_01]
action: Close-up on the toddler's illuminated face, mouth agape in wonder.
camera: Static close-up with subtle shake.
audio: Toddler gasps.
dialogue:

### Shot 5 — 6.5-8.5s (hard_cut)
panels: [6, 7]
characters_present: [char_01]
action: A bright crack snaps across the eggshell and pieces burst open.
camera: Push In fast to egg center.
audio: Sharp crack sound, wet pop.
dialogue:

### Shot 6 — 8.5-10.5s (hard_cut)
panels: [8]
characters_present: [char_02]
action: The tiny green baby dinosaur stumbles out of the shell, blinks its huge yellow eyes, and smiles.
camera: Tilt Up from shell to dino's face.
audio: Dino cheerful chirp, playful pizzicato cue.
dialogue:

### Shot 7 — 10.5-15.0s (hard_cut)
panels: [9]
characters_present: [char_01, char_02]
action: The baby dinosaur looks straight up at the toddler and squeaks "Mama!"; the toddler jumps back with wide shocked eyes.
camera: Medium two-shot, rapid Push In on the toddler's reaction.
audio: Dino cheep, toddler shriek.
dialogue: char_02: "Mama!"

## Generation g2 — 15.0-27.0s
duration_seconds: 12.0
panel_grid: 2x2

### Shot 1 — 15.0-27.0s (continuous)
panels: [1, 2, 3, 4]
characters_present: [char_01, char_02]
action: ...
camera: Static Shot, then Zoom In with small amplitude at slow speed.
audio: ...
dialogue:

## Scene-end handoff -> scene s2
on_screen: [char_01, char_02]
mood: calm
transition: hard_cut
```

### Field notes

- **Header names are exact.** The parser matches `## Generation gK — a-b s`,
  `### Shot N — a-b s (transition)`, and `## Scene-end handoff -> scene <next>`.
  Times are **scene-relative seconds** (may have one decimal).
- **transition** is `continuous` (flows straight from what came before — the
  previous shot's last frame or, for the first shot of a generation, the
  previous generation/scene) or `hard_cut` (deliberate editorial cut).
- **`action`** is a single line: concrete, visible, present-tense events in
  order. This becomes the Minimax timeline text, so write what the camera
  sees — expressions, physical beats, props — not inner thoughts.
- **`dialogue`**: `cid: "line"` (comma-separate multiple). Leave empty when
  silent. Keep lines short — the model lip-syncs and voices them.
- **Handoff block:** `on_screen`, `mood`, `transition` (`hard_cut` |
  `match_cut`). For the LAST scene, still emit the block pointing at a
  sentinel (`-> scene end`).
