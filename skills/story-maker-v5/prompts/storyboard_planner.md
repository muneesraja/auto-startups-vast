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
- **Dynamic Shot Depth & Story-First Pacing (MANDATORY)**: Before assigning cuts, the Director
  must analyze the scene beats, dialogue, and physical choreography to determine
  the natural dramatic pacing and shot depth:
  * **1-Shot Master Take / Oner (10.0s – 15.0s)**: When the narrative beat is a continuous
    physical sequence (e.g., continuous sliding down a cavern, sovereign entrance, unbroken
    falling action, high-stakes continuous tracking, or sustained emotional dialogue), the shot
    **MUST NOT be cut**. Author it as an unbroken single-shot Master Take (10.0–15.0s) filling
    the entire generation.
  * **Asymmetric 2-Shot Dynamic (2 shots per 15s)**: Unequal dramatic division based on
    action/reaction or statement/rebuttal (e.g. 11.5s setup + 3.5s punchy reaction reveal;
    9.0s statement + 6.0s rebuttal; 5.0s confrontation + 10.0s lethal whisper and freeze).
  * **Dynamic Action Arc (3 shots per 15s)**: High-stakes physical sequences with varying tempo
    (e.g. 6.0s drift/approach + 2.5s shock impact + 6.5s smoke/standoff).
  * **Rapid Montage (4+ shots per 15s)**: Reserved strictly for high-tempo preparation,
    chaotic impacts, or rapid flashbacks.
  * **STRICT PROHIBITION**: Never mechanically slice every generation into arbitrary equal intervals
    (e.g. 2 equal 7.5s slices or 4 equal 3.75s slices). Never default blindly to 2 shots per generation
    or 4 shots per scene. Vary shot durations organically to establish a living cinematic rhythm.
- **Multi-Character Prop Staging & Separation (MANDATORY)**:
  * When multiple characters are dining, eating, or using tools simultaneously, **allocate individual props/vessels** in distinct spatial zones (e.g. "two steaming ceramic noodle bowls, one positioned directly in front of each brother").
  * In `action:` describe each character interacting with their own dedicated prop and utensils (e.g., "Lebo scoops noodles from his bowl frame-left; Thabo holds his bowl frame-right with both hands").
  * **Never stage multiple characters eating out of one single bowl simultaneously**—this creates visual crowding and limb distortion in image/video generation. (Single props are strictly reserved for physical tug-of-war conflict).
- **Dialogue Progression & Anti-Loop Rule**:
  * Dialogue must move forward with every cut. Never repeat the same blame, accusation, or question across consecutive shots (e.g., do not repeat "He broke it! / No, he broke it!" when a parent enters after an argument).
  * **Authority Arrival Pivot:** When an authority figure enters, immediately pivot the dialogue from mutual squabbling to a shared plea, appeal, excuse, or silence, allowing the newcomer to deliver a knowing, witty response ("I know what you two really want") that triggers the resolution.
- **10-Second Commercial Button Formula (for Branded Stories/Ads)**:
  * Structure commercial button generations (10.0–15.0s total) for maximum brand elegance and authentic swagger:
    - **Shot 1 (Setup & Hook, 2.0–3.0s)**: Characters reacting, smelling food, or locking eyes with the hero product.
    - **Shot 2 (Authentic Slogan / Maternal Swagger, 5.0–7.0s)**: Speaker delivers the core tagline/motto in natural, regional vernacular inside `dialogue:` with confident posture and warm lighting.
    - **Shot 3 (Sensory Crunch / Brand Button, 3.0–5.0s)**: Close-up on the hero product/satisfying crunch, beaming smile, and held brand tableau.

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
  * Each 5-15s video generation (`g1`, `g2`, ...) is anchored by exactly one storyboard sheet.
  * **Dynamic Shot Pacing (2 Minimum to 8 Maximum per Generation)**:
    - Never force a static 2-shot or 4-shot structure. Choose shot counts based on dramatic pacing:
      - **Slow-Paced / Emotional / Intimate / Tension (2 Shots Minimum)**:
        - E.g. 7.5s + 7.5s, or 6.0s + 9.0s.
        - **MANDATORY HIGH DETAIL**: When planning only 2 shots, the shot descriptions MUST be super high in detail so that 15 seconds never feels static or boring! `acting_beat:` must describe multi-phase progression (e.g. `initial stillness → breathing catches → eyes widen → subtle lip tremor → tear spills → head lowers in defeat`), `camera:` must feature continuous evolving motion (`Push In slow with subtle parallax drift`), and `audio:` must have layered atmospheric sound (room tone, flickering flames, breath, fabric shifts).
      - **Moderate Dramatic Pace / Dialogue / Discovery (3 to 4 Shots)**:
        - Balanced cuts averaging 3.5s to 5.0s per shot.
      - **Fast-Paced / Action / Comedy / Chase / Climax (5 to 8 Shots Maximum)**:
        - Rapid cuts averaging 1.5s to 3.0s per shot for relentless momentum.
  * **Storyboard Grid Selection (Default/Min 3x2, Max 3x3)**:
    - **Default / Minimum Grid**: `3x2` (6 panels, 1920×720 widescreen cells). Ideal for 2 to 4 shots (each shot claims 1 to 3 panels showing progressive key poses/micro-beats).
    - **Maximum Grid**: `3x3` (9 panels, 1280×720 true 16:9 cells). Ideal for 5 to 8 shots (each shot claims 1 to 2 panels).
    - **Alternative**: `2x3` (6 panels, 1280×1080) for scenes emphasizing vertical architecture or tall characters.
    - `panel_grid: RxC` must satisfy `R * C == total_panels` (6 to 9 panels). Grids outside [6, 9] are rejected by the validator.
  * **Cross-Generation Seam Alignment Rule (CRITICAL)**:
    - Because `render_all.py` extracts a 3-second tail from `gK` and conditions `gK+1` on it, the **closing shot of `gK` and the opening shot of `gK+1` MUST match in physical posture, camera framing, and actor positioning**.
    - Never end `gK` on a standing close-up face and start `gK+1` on a wide shot of the character kneeling in a different room! Match-cut the physical and spatial state across generation seams.
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
focus: shallow_focus
acting_beat: held breath → eyes widen → curious lean-in
layout: eye-level macro, face silhouette against dark basement negative space
screen_direction: held
camera_angle: eye_level
action: Extreme close-up on the toddler's wide brown eyes peering curiously into the dark dusty basement.
camera: Push In fast on eyes.
audio: Heavy breathing, ambient basement hum.
dialogue:

### Shot 2 — 1.5-3.0s (cut_on_action)
panels: [2]
characters_present: [char_01]
shot_size: wide
composition: leading_lines, depth
acting_beat: excited bounce → quick waddle-run → glance back
layout: low tracking position, tiny feet foreground, boxes receding down corridor
screen_direction: left_to_right
camera_angle: low_angle
action: Low-angle tracking shot of the toddler's tiny feet in mismatched socks padding through dust past cardboard boxes.
camera: Low Angle Tracking Shot at fast speed.
audio: Soft padding footsteps on dust.
dialogue:

### Shot 3 — 3.0-5.0s (reaction_cut)
panels: [3, 4]
characters_present: [char_01]
shot_size: medium
composition: rule_of_thirds, leading_lines
acting_beat: reach for canvas → push aside → awestruck pause in gold light
layout: curtain edge foreground, toddler left third, glowing egg deep midground
screen_direction: left_to_right
camera_angle: three_quarter
action: The toddler pushes aside a hanging canvas sheet; a golden light shaft illuminates a large speckled glowing egg.
camera: Handheld whip pan right to reveal the glowing egg.
audio: Fabric rustle, faint magical shimmer hum.
dialogue:

### Shot 4 — 5.0-6.5s (reaction_cut)
panels: [5]
characters_present: [char_01]
shot_size: closeup
composition: center, visual_hierarchy
acting_beat: breath catches → mouth falls open → eyes glisten
layout: centered lit face, darkness falling off around cheeks
screen_direction: held
action: Close-up on the toddler's illuminated face, mouth agape in wonder.
camera: Static close-up with subtle shake.
audio: Toddler gasps.
dialogue:

### Shot 5 — 6.5-8.5s (hard_cut)
panels: [6, 7]
characters_present: [char_01]
shot_size: extreme_closeup
composition: center, depth
acting_beat: shell trembles → crack snaps → pieces burst
layout: egg fills frame, crack line bisecting the shell
screen_direction: held
action: A bright crack snaps across the eggshell and pieces burst open.
camera: Push In fast to egg center.
audio: Sharp crack sound, wet pop.
dialogue:

### Shot 6 — 8.5-10.5s (cut_on_action)
panels: [8]
characters_present: [char_02]
shot_size: medium
composition: rule_of_thirds, negative_space
acting_beat: stumble → blink → delighted grin
layout: tiny dino low in frame against open floor, shell fragments framing edges
screen_direction: bottom_to_top
action: The tiny green baby dinosaur stumbles out of the shell, blinks its huge yellow eyes, and smiles.
camera: Tilt Up from shell to dino's face.
audio: Dino cheerful chirp, playful pizzicato cue.
dialogue:

### Shot 7 — 10.5-15.0s (reaction_cut)
panels: [9]
characters_present: [char_01, char_02]
shot_size: medium
composition: center, visual_hierarchy
acting_beat: dino looks up and squeaks → toddler startles → shocked retreat
layout: two-shot with dino low-center and toddler recoiling frame-right
screen_direction: left_to_right
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
shot_size: medium
composition: center, depth
camera_angle: three_quarter
acting_beat: cautious approach → gentle pet → mutual settle
layout: quiet two-shot in dusty light, characters low-center
screen_direction: held
action: Unbroken continuous master take: the toddler approaches cautiously, gently pets the baby dinosaur's snout, and they settle together in the golden light.
camera: Tracking Shot moving slowly inward, then Push In with small amplitude at slow speed.
audio: Soft rustle of clothing, gentle dino purr, warm atmospheric ambient tone.
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
