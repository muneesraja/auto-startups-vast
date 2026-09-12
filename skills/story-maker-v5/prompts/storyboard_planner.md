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
- **Continuation generations describe their opening as continuing from the
  previous generation's ending state.** The video prompt for a continuation
  is rendered with the previous generation's rendered tail attached, so the
  model sees the actual ending frames.
- **The boundary rule is load-bearing** (`tools/boundary.py`): a generation
  whose first shot declares `hard_cut` opens fresh — the renderer attaches
  no tail and the prompt must not declare `<Video 1>`. For scene boundaries,
  the previous scene's `handoff.transition` decides: `hard_cut` = fresh
  scene boundary; anything else = the tail is attached. Keep the two
  declarations consistent — the validator errors when a `hard_cut` handoff
  is followed by a `continuous` shot 1.

## Rules

- **Read the shared asset manifest first.** Before assigning `char_NN` IDs or
  wardrobe colors, read `assets/CHARACTERS.md` in the shared story assets
  folder. Reuse the existing cids and their exact wardrobe. Never invent a new
  `char_NN` not in the manifest.
- **Shots are contiguous within a generation** and together fill it exactly.
- **Dynamic Shot Depth & Story-First Pacing (MANDATORY)**: shot count is a
  directing choice — **1 to 8 shots per generation**, chosen from the
  taxonomy in [`assets/production-rules.md`](../assets/production-rules.md)
  §1 (oner master take → asymmetric 2-shot → action arc → rapid montage).
  Oners are legal and mandatory when the beat demands an unbroken take;
  1–2 shot generations carry the mandatory high-detail requirement.
- **Multi-Character Prop Staging & Separation (MANDATORY)**: distinct
  individual props/vessels per character — canonical rule in
  [`assets/production-rules.md`](../assets/production-rules.md) §2.
- **Dialogue Progression & Anti-Loop Rule** — canonical rule in
  [`assets/production-rules.md`](../assets/production-rules.md) §3.
- **10-Second Commercial Button Formula (for Branded Stories/Ads)** —
  canonical formula in
  [`assets/production-rules.md`](../assets/production-rules.md) §4.

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

### Depth of field & focus (`focus:` field)

Shots may optionally carry a `focus:` field from the 4-value taxonomy (see
[`assets/directors-guide.md`](../assets/directors-guide.md) Section 2 and
[`assets/cinematography-bible.md`](../assets/cinematography-bible.md) Section C-bis):

| `focus` | When to use |
|---|---|
| `shallow_focus` | Character intimacy, isolating emotion, blurring busy backgrounds (default) |
| `deep_focus` | Ensemble staging, environmental context, multiple planes in sharp focus |
| `rack_focus` | Mid-shot focus shift from foreground to background (or reverse) |
| `soft_focus` | Dream sequence, memory, nostalgic flashback, hazy trance |

Default if omitted: `shallow_focus`. If using `rack_focus`, describe the focus shift progression in the shot's `action:` micro-beats.

### Motivated-cut thinking

Before cutting, ask: Does this cut answer a question the previous shot raised?
Reveal new information? Change the emotional register? Move the story forward?
If none of these, **don't cut** — use camera motion instead. See
[`assets/directors-guide.md`](../assets/directors-guide.md) Section 5 for the
question→answer pattern and the motivated-cut checklist.

### Shot production fields (`acting_beat:`, `layout:`, `screen_direction:`)

Every shot must also carry three anime-studio fields (validator-enforced):

- `acting_beat:` — the performance arc as a short chain: **anticipation → action
  → reaction/settle** (e.g. `crouch → leap → wobbly landing`). This is what the
  animator — and H3 — actually performs.
- `layout:` — the staging read: depth layers, eye path, silhouette separation
  (e.g. `foreground runner against flat lit background, eye path to the door`).
- `screen_direction:` — one of `left_to_right`, `right_to_left`,
  `toward_camera`, `away_from_camera`, `top_to_bottom`, `bottom_to_top`,
  `held`. Maintain it across cuts (180° rule).

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

- **Scene, Generation & Panel Grid Relationship**:
  * Each 5-15s video generation (`g1`, `g2`, ...) is anchored by exactly one
    storyboard sheet (`storyboard_sheet_<gen>.txt` — per-generation sheets are
    the only convention).
  * **Dynamic Shot Pacing (1 to 8 shots per generation)** — taxonomy in
    [`assets/production-rules.md`](../assets/production-rules.md) §1:
    - **Master Take / Oner (1 shot)**: continuous physical/emotional beats
      that must not be cut; panels become temporal milestones. Mandatory
      high detail.
    - **Slow-Paced / Emotional / Intimate / Tension (1–2 shots)**: mandatory
      high detail — multi-phase `acting_beat:`, evolving `camera:`, layered
      `audio:`.
    - **Moderate Dramatic Pace / Dialogue / Discovery (3 to 4 shots)**:
      balanced cuts averaging 3.5s to 5.0s per shot.
    - **Fast-Paced / Action / Comedy / Chase / Climax (5 to 8 shots)**:
      rapid cuts averaging 1.5s to 3.0s per shot for relentless momentum.
  * **Storyboard Grid Selection (Default/Min 3x2, Max 3x3)**:
    - **Default / Minimum Grid**: `3x2` (6 panels, 1920×720 widescreen cells). Ideal for 1 to 4 shots (each shot claims 1 to 6 panels showing progressive key poses/micro-beats — a oner claims all panels as temporal milestones).
    - **Maximum Grid**: `3x3` (9 panels, 1280×720 true 16:9 cells). Ideal for 5 to 8 shots (each shot claims 1 to 2 panels).
    - **Alternative**: `2x3` (6 panels, 1280×1080) for scenes emphasizing vertical architecture or tall characters.
    - `panel_grid: RxC` must satisfy `R * C == total_panels` (6 to 9 panels). Grids outside [6, 9] are rejected by the validator.
  * **Cross-Generation Seam Alignment Rule (CRITICAL for continuations)**:
    - For a continuation boundary, `render_all.py` extracts a 3-second tail
      from `gK` and conditions `gK+1` on it — the **closing shot of `gK` and
      the opening shot of `gK+1` MUST match in physical posture, camera
      framing, and actor positioning**. Never end `gK` on a standing
      close-up face and start `gK+1` on a wide shot of the character
      kneeling in a different room!
    - For a **fresh-cut boundary** (gK+1 shot 1 = `hard_cut`, or the next
      scene follows a `hard_cut` handoff) no tail is attached — the seam
      rule does not apply and the next generation may open on any setup.
- **Dynamic Cinematography Rule (MANDATORY)**:
  * Every shot must have an intentional camera angle from the taxonomy:
    `eye_level`, `low_angle`, `high_angle`, `bird_eye`, `worm_eye`, `side_profile`,
    `three_quarter`, `over_the_shoulder`, `dutch_angle`, `reverse_shot`.
  * **Static eye-level framing repeated across cuts triggers an anti-monotony warning in the validator.**
    Never default monotonously to front eye-level framing.
  * Pair contrasting, motivated camera angles shot-to-shot: pair a wide high-angle establishing
    shot with a low-angle hero close-up, a dynamic side-profile tracking shot, or a worm's-eye ground
    perspective followed by a canted dutch-angle tumble.
- **Motivated Camera Movement (MANDATORY)**:
  * Every shot must feature motivated camera movement using the Minimax vocabulary (see
    [`assets/minimax-h3-prompt-bible.md`](../assets/minimax-h3-prompt-bible.md)):
    `Tracking Shot`, `Push In`, `Pull Out`, `Crane Up/Down`, `Arc Shot`, `Tilt Up/Down`, `Whip Pan`,
    `Pedestal Up/Down`, `Zoom In/Out` — optionally with amplitude (`with small/large amplitude`)
    and speed (`at slow/fast speed`).
  * **Monotonous static camera shots repeated across cuts trigger an anti-monotony warning in the validator.**
- **`panels`**: each shot claims 1–4 panels of the sheet, showing the shot's key poses
  in order. Panels are numbered 1..N **column-major** (top-to-bottom within each column, then left-to-right across columns) and each panel belongs to exactly one shot.
- **`characters_present` ⊆ scene `cast`.** Never invent a `char_NN` not in the
  scene's cast.
- **`audio` is real.** Minimax generates native stereo audio — plan the
  soundscape (footsteps, ambience, music cue) per shot, and put spoken lines
  in `dialogue`.
- **Screenplay Extraction Authority (MANDATORY).** `developed_story.md` is a
  full animation screenplay. Extract `dialogue:`, `acting_beat:`, and sound
  events directly from it:
  - **`dialogue:`** must quote the screenplay's dialogue blocks verbatim
    (character cue + parenthetical + spoken line). Never invent dialogue that
    isn't in the screenplay.
  - **`acting_beat:`** should mirror the screenplay's action line micro-beats
    (e.g. screenplay says *"His hind foot SLIPS. The basket tips."* →
    `acting_beat: foot slips → lurch forward → basket tips`).
  - **`audio:`** should harvest ALL-CAPS sound cues from the screenplay's
    action lines into the soundscape (e.g. `SPLASH`, `CREAK`, `SNAP`).
- **The handoff block is mandatory** (it seeds the next scene's opening).

## Output format (load-bearing — verbatim)

Canonical worked example:
[`assets/example-ollie.md`](../assets/example-ollie.md) — all prompts use
this same story (Ollie, the pond, the basket) so examples stay consistent
across agents. Below: scene `s1` "The Idea" — `g1` is a 6-shot montage,
`g2` is the canonical 1-shot oner (the cylinder-peek discovery).

```
# Scene s1 — The Idea
scene_id: s1
target_seconds: 45
cast: [char_01]
location_ref_id: loc_01

## Generation g1 — 0.0-15.0s
duration_seconds: 15.0
panel_grid: 3x3

### Shot 1 — 0.0-2.5s (continuous)
panels: [1]
characters_present: [char_01]
shot_size: medium_closeup
composition: visual_hierarchy, negative_space
focus: shallow_focus
acting_beat: proud beam → chest puff → contented sniff
layout: low-angle MCU, basket held up foreground, gerberas soft behind
screen_direction: held
camera_angle: low_angle
action: Ollie sits on the mossy boulder cradling his bark basket adorned with a spiral seashell and pink blossoms, beaming proudly.
camera: Slow Push In.
audio: soft contented sniff, shell clinking in basket, meadow birds, gentle breeze.
dialogue:

### Shot 2 — 2.5-5.0s (hard_cut)
panels: [2, 3]
characters_present: []
shot_size: wide
composition: leading_lines, depth
acting_beat: stillness → sparkle on water → settled glass
layout: glassy pond fills midground, clover and gerberas foreground, ledge receding left
screen_direction: left_to_right
camera_angle: low_angle
action: Establishing shot of the pristine pond edge framed by clovers and orange gerberas, light sparkling on the water.
camera: Push In toward water.
audio: water gently lapping on pebbles, summer insects.
dialogue:

### Shot 3 — 5.0-8.0s (hard_cut)
panels: [4]
characters_present: [char_01]
shot_size: medium
composition: rule_of_thirds, look_room
acting_beat: careful walk → pause → look down at reflection
layout: Ollie on the right third approaching the ledge, pond left, look-room toward water
screen_direction: left_to_right
camera_angle: eye_level
action: Ollie cradles his basket and waddles up to the flat rock ledge, looking down at his reflection in the water.
camera: Slow Dolly Right.
audio: little paw steps on moss, playful woodwind.
dialogue:

### Shot 4 — 8.0-10.5s (cut_on_action)
panels: [5, 6]
characters_present: [char_01]
shot_size: closeup
composition: center, visual_hierarchy
acting_beat: buzz past ear → sharp turn → hind foot slips
layout: dragonfly crosses frame-right, Ollie's head snapping to follow, basket edge slipping from paws
screen_direction: left_to_right
camera_angle: eye_level
action: A glowing green dragonfly buzzes around Ollie's ears; he turns quickly to track it and accidentally nudges the rock — his hind foot slips.
camera: Orbiting Track.
audio: dragonfly wing flutter, giggle of surprise, playful chime accent.
dialogue:

### Shot 5 — 10.5-13.0s (match_cut)
panels: [7]
characters_present: [char_01]
shot_size: wide
composition: depth, screen_direction
acting_beat: basket tips → shell spills → splash down
layout: basket tumbling frame-center into the pond, Ollie lunging left
screen_direction: left_to_right
camera_angle: high_angle
action: The basket tips over the ledge — the shell and pink blossoms spill, tumbling into the pond with a splash.
camera: Tilt Down following the basket's fall.
audio: SPLASH as the basket hits water, sudden comedic pause in the score.
dialogue:

### Shot 6 — 13.0-15.0s (reaction_cut)
panels: [8, 9]
characters_present: [char_01]
shot_size: closeup
composition: center, visual_hierarchy
acting_beat: gasp → drop to knees → lean forward over the water
layout: Ollie's face centered, wide-eyed, pond shimmer behind
screen_direction: held
camera_angle: eye_level
action: Ollie gasps and drops to his knees at the water's edge, leaning forward over the shallows where the hollow cylinder bobs.
camera: Push In.
audio: Ollie's gasp "Ah!", water ripples, inquisitive celesta.
dialogue:

## Generation g2 — 15.0-30.0s
duration_seconds: 15.0
panel_grid: 2x3

### Shot 1 — 15.0-30.0s (continuous)
panels: [1, 2, 3, 4, 5, 6]
characters_present: [char_01]
shot_size: medium_closeup
composition: frame_within_frame, visual_hierarchy, depth
focus: shallow_focus
acting_beat: curious lean-in → eyes widen → grinning lightbulb moment
layout: Ollie prone on the ledge foreground-right, cylinder rim framing his face, waterline behind
screen_direction: left_to_right
camera_angle: low_angle
action: Unbroken continuous master take: Ollie lies prone at the pond edge, lifts the hollow wooden cylinder to his eye, peers through at the shimmering underwater world — light refractions, swaying weeds — and his eyes widen into a grinning lightbulb moment.
camera: Slow Push In with small amplitude at slow speed, drifting toward the cylinder opening.
audio: muffled underwater hum through the tube, water lap, a single inquisitive celesta note.
dialogue:

## Scene-end handoff -> scene s2
on_screen: [char_01]
mood: wonder
transition: hard_cut
```

### Field notes

- **Header names are exact.** The parser matches `## Generation gK — a-b s`,
  `### Shot N — a-b s (transition)`, and `## Scene-end handoff -> scene <next>`.
  Times are **scene-relative seconds** (may have one decimal).
- **transition** takes the full 8-value grammar above. For the FIRST shot of
  a generation it is load-bearing for the renderer: `hard_cut` opens the
  generation fresh (no tail ref, no `<Video 1>` in the video prompt); any
  other value means the previous generation's rendered tail is attached and
  `<Video 1>` must be declared.
- **`action`** is a single line: concrete, visible, present-tense events in
  order. This becomes the Minimax timeline text, so write what the camera
  sees — expressions, physical beats, props — not inner thoughts.
- **`dialogue`**: `cid: "line"` (comma-separate multiple). Leave empty when
  silent. Keep lines short — the model lip-syncs and voices them.
- **Handoff block:** `on_screen`, `mood`, `transition` (full 8-value
  grammar). The handoff `transition` is load-bearing for the renderer:
  `hard_cut` means the next scene's g1 opens fresh — no tail ref attached,
  no `<Video 1>` in its video prompt. Any other value attaches the tail.
  It must agree with the next scene's g1 shot-1 `transition` (a `hard_cut`
  handoff followed by a `continuous` shot 1 is a validator error). For the
  LAST scene, still emit the block pointing at a sentinel (`-> scene end`).
