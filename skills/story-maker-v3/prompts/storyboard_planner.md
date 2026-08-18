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

## Spatial plan prerequisite

Before authoring `storyboard_<scene>.md`, Agent 3a must author
`spatial_plan_<scene>.md` (see [`prompts/spatial_planner.md`](spatial_planner.md)).
The spatial plan is the authoritative scene geography: landmarks, zones,
distances, camera geography, and per-generation/per-shot spatial state. The
storyboard must be consistent with the spatial plan — every normal generation
in the storyboard must have a matching `## Generation gK` block in the spatial
plan, and every shot's `characters_present` must appear in that shot's
`on_screen_positions` in the spatial plan. The spatial validator cross-checks
this automatically.

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

## Generation continuity

No bridge generations are used. Continuity between adjacent generations is
handled at render time: `render_all.py` renders generations sequentially and
conditions each generation on the previous generation's rendered tail (3s)
as a `ref_video`. This means:

- **The scene timeline is exactly the sum of generation durations** — no
  additive bridge seconds. `TARGET_story = TARGET_delivery`.
- **Each generation after g1 should describe its opening as continuing from
  the previous generation's ending state.** The video prompt for g(K+1) will
  be rendered with the tail of gK attached, so the model sees the actual
  ending frames.
- **g1 of each scene after the first** also receives the tail of the previous
  scene's last generation (cross-scene continuity).

## Rules

- **Read the shared asset manifest first.** Before assigning `char_NN` IDs or
  wardrobe colors, read `assets/CHARACTERS.md` in the shared story assets
  folder. Reuse the existing cids and their exact wardrobe. Never invent a new
  `char_NN` not in the manifest.
- **Shots are contiguous within a generation** and together fill it exactly.
  For modern short-form / high-retention pacing, a typical 15s generation has
  **5–8 micro-shots**, each **1.5–3.0s**. A shot shorter than ~1.0s may be too
  brief; a shot longer than ~4.0s slows the pace. Exception: tender /
  dialogue-heavy beats — these can run 6–15s in a single shot with multiple
  action-motivated camera moves (see the dragon exemplar in
  `Research/minimax-h3/dragon/story-board-2.md`: 2 shots / 15s, 1 hard cut,
  3 camera moves inside shot 1).

### Transition grammar (8 values)

Choose the transition that best fits each shot boundary. **A cut must add new
information** (subject, space, state, viewpoint, time) — if only framing or
angle changes, use `camera_move` instead of cutting. The validator warns on
same-character `hard_cut` and on 3+ consecutive identical transitions.

| transition | when to use | canonical phrase in the video prompt |
|---|---|---|
| `continuous` | same take continues; no cut | *(no phrase)* + "Camera remains completely continuous throughout the shot." |
| `hard_cut` | new subject, space, state, viewpoint, or time | `Hard cinematic cut.` |
| `cut_on_action` | mid-motion cut; movement carries across the boundary | `Cut on the action.` |
| `reaction_cut` | action → face/reaction beat | `Cut to the reaction.` |
| `match_cut` | graphic or positional match on a named element | `Match cut on <element>.` (name the element in `action:`) |
| `whip_pan` | camera-motivated transition; fast pan | `Whip pan transition.` |
| `audio_led` | next shot's sound starts before the visual (L/J cut) | `Audio leads the cut.` (requires non-empty `audio:` on this shot) |
| `camera_move` | only framing/angle changes — **not a cut** | *(renders as a camera line, no cut phrase)* |

**Anti-monotony**: vary transitions within a generation. The validator warns
when all transitions are identical or when 3+ consecutive shots share the same
transition type. Default to `cut_on_action` or `reaction_cut` for same-character
boundaries — reserve `hard_cut` for genuine subject/space/time changes.

### Shot design (`shot_size:` field)

Every shot must carry a `shot_size:` field from the 7-value taxonomy (see
[`assets/directors-guide.md`](../assets/directors-guide.md) Section 2 for the
"why" behind each):

| `shot_size` | When to use |
|---|---|
| `extreme_wide` | Establish geography, scale, isolation |
| `wide` | Environment + character position |
| `full` | Character body language, posture |
| `medium` | Interaction, two-character dynamics |
| `medium_closeup` | Emotion + context (the everyday shot) |
| `closeup` | Emotion, important detail, intimacy |
| `extreme_closeup` | Micro-detail, intense emotion, symbolic object |

**Vary shot sizes across a generation.** Six identical `medium` shots feel
flat. The new-information rule uses shot_size to distinguish framing-only
changes from real cuts: same characters + same shot_size + `hard_cut` →
**error** (use `camera_move` instead). Same characters + different shot_size +
`hard_cut` → OK (the size change IS new information).

### Composition (`composition:` field)

Every shot must carry a `composition:` field — one or more comma-separated
values from the 12-value taxonomy (see
[`assets/directors-guide.md`](../assets/directors-guide.md) Section 4):

`rule_of_thirds`, `center`, `symmetry`, `leading_lines`, `negative_space`,
`depth`, `silhouette`, `frame_within_frame`, `visual_hierarchy`, `headroom`,
`look_room`, `screen_direction`

**One clear subject per frame.** If the audience doesn't know where to look,
the composition has failed. Use `visual_hierarchy` to make the subject
unmissable. Maintain `screen_direction` across cuts (180° rule — keep
characters facing the same way shot to shot).

### Motivated-cut thinking

Before cutting, ask: Does this cut answer a question the previous shot raised?
Reveal new information? Change the emotional register? Move the story forward?
If none of these, **don't cut** — use camera motion instead. See
[`assets/directors-guide.md`](../assets/directors-guide.md) Section 5 for the
question→answer pattern and the motivated-cut checklist.

### Animation direction (writing `action:` as micro-beats)

Animation is not "the character turns around." Animation is a sequence of
micro-beats: **hear sound → freeze → eyes move → head turns → body follows →
reaction.** Write `action:` as comma-separated micro-beats in time order, not
a single verb. See [`assets/directors-guide.md`](../assets/directors-guide.md)
Section 6 for the full animation principles reference.

**Instead of:** `action: The baby turns around.`
**Write:** `action: The baby freezes, eyes dart to the sound, head turns, body follows, mouth drops open.`

Animation principles to apply:
- **Anticipation**: wind-up before action (crouch before a jump, pull back before a throw)
- **Follow-through**: continue after the action stops (hair swings after the head turns)
- **Timing & weight**: heavy things move slowly, light things move fast
- **Exaggeration**: push poses beyond realism for emotional clarity
- **Secondary motion**: cloth, hair, ears, tail follow the primary action with delay

- **`panels`**: each shot claims 1–4 panels of the generation's sheet, showing
  the shot's key poses in order. Panels are numbered 1..N **column-major**
  (top-to-bottom within each column, then left-to-right across columns) and
  each panel belongs to exactly one shot.
  `panel_grid: RxC` must satisfy R*C = total panels (6–12). Default grid is
  `3x2` (3 rows × 2 columns — left column = beginning, right column = end).
  For longer generations, use `3x3` (beginning → middle → end across columns).
  Minimum grid is 2x3 or 3x2 — never smaller. Larger grids (3x3, 2x4, 4x3,
  etc.) are encouraged for generations with more shots or key poses.
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
shot_size: extreme_closeup
composition: visual_hierarchy, negative_space
action: Extreme close-up on the toddler's wide brown eyes peering curiously into the dark dusty basement.
camera: Push In fast on eyes.
audio: Heavy breathing, ambient basement hum.
dialogue:

### Shot 2 — 1.5-3.0s (cut_on_action)
panels: [2]
characters_present: [char_01]
shot_size: wide
composition: leading_lines, depth
action: Low-angle tracking shot of the toddler's tiny feet in mismatched socks padding through dust past cardboard boxes.
camera: Low Angle Tracking Shot at fast speed.
audio: Soft padding footsteps on dust.
dialogue:

### Shot 3 — 3.0-5.0s (reaction_cut)
panels: [3, 4]
characters_present: [char_01]
shot_size: medium
composition: rule_of_thirds, leading_lines
action: The toddler pushes aside a hanging canvas sheet; a golden light shaft illuminates a large speckled glowing egg.
camera: Handheld whip pan right to reveal the glowing egg.
audio: Fabric rustle, faint magical shimmer hum.
dialogue:

### Shot 4 — 5.0-6.5s (reaction_cut)
panels: [5]
characters_present: [char_01]
shot_size: closeup
composition: center, visual_hierarchy
action: Close-up on the toddler's illuminated face, mouth agape in wonder.
camera: Static close-up with subtle shake.
audio: Toddler gasps.
dialogue:

### Shot 5 — 6.5-8.5s (hard_cut)
panels: [6, 7]
characters_present: [char_01]
shot_size: extreme_closeup
composition: center, depth
action: A bright crack snaps across the eggshell and pieces burst open.
camera: Push In fast to egg center.
audio: Sharp crack sound, wet pop.
dialogue:

### Shot 6 — 8.5-10.5s (cut_on_action)
panels: [8]
characters_present: [char_02]
shot_size: medium
composition: rule_of_thirds, negative_space
action: The tiny green baby dinosaur stumbles out of the shell, blinks its huge yellow eyes, and smiles.
camera: Tilt Up from shell to dino's face.
audio: Dino cheerful chirp, playful pizzicato cue.
dialogue:

### Shot 7 — 10.5-15.0s (reaction_cut)
panels: [9]
characters_present: [char_01, char_02]
shot_size: medium
composition: center, visual_hierarchy
action: The baby dinosaur looks straight up at the toddler and squeaks "Mama!"; the toddler jumps back with wide shocked eyes.
camera: Medium two-shot, rapid Push In on the toddler's reaction.
audio: Dino cheep, toddler shriek.
dialogue: char_02: "Mama!"

## Generation g2 — 15.0-27.0s
duration_seconds: 12.0
panel_grid: 2x3

### Shot 1 — 15.0-27.0s (continuous)
panels: [1, 2, 3, 4, 5, 6]
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
