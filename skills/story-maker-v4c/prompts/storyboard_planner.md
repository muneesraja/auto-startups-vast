# Agent 3 — Storyboard Planner (Minimax H3)

**Input:** `<run_dir>/scenes.md` (one scene at a time) + `developed_story.md`
+ the full **episode context** (previous scenes' storyboards, and the previous
episode's final state when this is episode 2+). Never author a storyboard
without that context loaded — Minimax prompts say things like "Continue
directly from the previous scene", so you must know exactly what that was.
Must Read [`creature_behavior.md`](creature_behavior.md) and
[`coverage.md`](coverage.md) (and [`commercial_ad.md`](commercial_ad.md) if
the brief is an ad).
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
  Follow [`coverage.md`](coverage.md): situation then subject. **5–8
  micro-shots** (1.5–3.0s) only for `play_comedy`. Otherwise prefer fewer
  shots with a clear Event; a cut only if it adds information. Split ideas
  that need several locations or will not fit in 15s.
- **`panels`**: each shot claims 1–4 panels of the generation's sheet, showing
  the shot's key poses in order. Panels are numbered 1..N in reading order
  across the whole sheet and each panel belongs to exactly one shot.
  `panel_grid: RxC` must satisfy R*C = total panels (3–12). Minimum grid is
  1x3, 2x2, 2x3, or 3x2 — never smaller. Larger grids (3x3, 2x4, 4x3, etc.)
  are encouraged for generations with more shots or key poses.
- **`camera`**: **one** H3 sentence from [`coverage.md`](coverage.md) — shot
  size + subject + situation + type + amplitude + speed (vocabulary in
  [`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md)).
  Do not chain multiple moves. Never “cinematic” alone. Ban subject-less whip
  pans.
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
panel_grid: 2x3

### Shot 1 — 0.0-5.0s (continuous)
panels: [1, 2]
characters_present: [char_01, char_02]
action: Establish: a leopard (predator, stalk) crouches in cover at flight_zone; the child stands exposed on the path; the mother's face is already tight.
camera: Wide establish, slow Push In with small amplitude at slow speed.
audio: Insects, distant river, child's footsteps, no music swell.
dialogue:

### Shot 2 — 5.0-9.0s (hard_cut)
panels: [3]
characters_present: [char_01, char_02]
action: Discover: insert of the leopard's shoulder through grass, ears forward, weight shifting; it does not look at camera or smile.
camera: Animal through cover, Static Shot.
audio: Grass whisper, low breath, no chirps.
dialogue:

### Shot 3 — 9.0-15.0s (hard_cut)
panels: [4, 5, 6]
characters_present: [char_01, char_02, char_03]
action: Protect: the mother steps between child and leopard, palm out, jaw set; the child freezes behind her hip; the leopard holds stalk, does not close.
camera: Medium two-shot OTS, adults as shield, slow Push In with small amplitude at slow speed.
audio: Mother's quiet "Stay.", fabric, held breath.
dialogue: char_03: "Stay."

## Generation g2 — 15.0-27.0s
duration_seconds: 12.0
panel_grid: 2x2

### Shot 1 — 15.0-27.0s (continuous)
panels: [1, 2, 3, 4]
characters_present: [char_01, char_02, char_03]
action: Emotion: MCU on the mother's tense face as she backs the child away; the leopard's eyes stay on them through cover; nobody smiles.
camera: MCU human reaction, Static Shot then Zoom In with small amplitude at slow speed.
audio: Quiet voices, river under, no playful cue.
dialogue:

## Scene-end handoff -> scene s2
on_screen: [char_01, char_02, char_03]
mood: tense
transition: hard_cut
```

### Field notes

- **Header names are exact.** The parser matches `## Generation gK — a-b s`,
  `### Shot N — a-b s (transition)`, and `## Scene-end handoff -> scene <next>`.
  Times are **scene-relative seconds** (may have one decimal).
- **transition** is `continuous` (flows straight from what came before — the
  previous shot's last frame or, for the first shot of a generation, the
  previous generation/scene) or `hard_cut` (deliberate editorial cut).
- **`action`** is a single line: event + human face/body + every animal's
  role/state/intent. Visible, present tense. Not inner thoughts.
- **Handoff `mood`** must match the last shot (tense after danger, not calm
  because a mascot smiled).
- **`dialogue`**: `cid: "line"` (comma-separate multiple). Leave empty when
  silent. Keep lines short — the model lip-syncs and voices them.
- **Handoff block:** `on_screen`, `mood`, `transition` (`hard_cut` |
  `match_cut`). For the LAST scene, still emit the block pointing at a
  sentinel (`-> scene end`).
