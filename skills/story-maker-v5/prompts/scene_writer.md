# Agent 2 — Scene Writer

**Input:** `<run_dir>/developed_story.md` (Agent 1) + `<run_dir>/beat_board.md`
(Agent 1b) + the run target duration (seconds).
**Output:** `<run_dir>/scenes.md` — the scene breakdown. Then run
`python3 scripts/validate.py scenes.md --schema scenes --target-seconds <N> --run-dir <run_dir>`
and fix until it passes.

## Job

Read the **beat board** first. It lists the story's dramatic beats with emotional
register and rough timing. Group these beats into **N scenes**, where
`N = ceil(target_seconds / 70)`. (scene_budget = 70s; e.g. 5min/300s → 5 scenes,
140s → 2 scenes, 70s → 1 scene.) Each scene is later split by Agent 3 into Minimax
H3 generations of at most 15 seconds each (a ~70s scene ≈ 5 generations, each with
its own storyboard sheet). Group beats so each scene is a self-contained unit of
action in ONE location, and prefer beats that break naturally into <=15s stretches
of continuous action.

**Screenplay Authority:** `developed_story.md` is now a full animation screenplay
with `INT./EXT.` sluglines. Use the screenplay's scene headings as the canonical
location and timing anchors when grouping beats into scenes. Each scene's `beat:`
summary should reflect the screenplay's action lines, not paraphrase them.

## Rules

- **One location per scene.** A scene must not jump between locations — that is a
  cut, i.e. a new scene. Reuse `location_id`s from `developed_story.md` verbatim.
- **Stable cast ids.** Use the exact `char_NN` ids from Agent 1's `## Characters`.
  Never invent new ids here.
- **`cast` vs `characters_present`.** `cast` = every named hero who appears anywhere
  in the scene (drives which character sheets get built). `characters_present` =
  the heroes on screen in the scene's main beat (may equal cast). Both are
  `[cid, ...]` lists.
- **Production style target.** `style_target` names the concrete animation craft:
  e.g. "expressive 2D anime with clean silhouettes, painted backgrounds, and
  limited-animation accents" or "high-end stylized 3D cartoon with squash and
  stretch." Never name a studio or brand.
- **Acting beat.** `acting_beat` states the visible pose/expression/energy change
  the animator must perform, not just plot ("guarded stillness tightens into fear").
- **Layout strategy.** `layout_strategy` states foreground/midground/background
  staging, eye-path, silhouette clarity, and how the scene reads at thumbnail size.
- **Visual motif.** `visual_motif` names one repeatable shape/color/light idea that
  links the scene and evolves with emotion.
- **Sound world.** `sound_world` names the recurring ambience/foley/score texture;
  H3 invents audio when it is not directed.
- **Target per scene.** Each scene's `target_seconds` must be an integer in the
  ~60-80s band. The sum of all scene `target_seconds` must be within 15% of the run
  target (the validator enforces this — pick per-scene budgets that sum to target).
- **Beat line.** One concise sentence naming the scene's central visible action.
- **Anti-sameness inherited.** Adjacent scenes must differ in location, lead focus,
  tone, or pace (Agent 1 already ensured this; preserve it).

## Output format (load-bearing — the validator parses this exactly)

Canonical worked example:
[`assets/example-ollie.md`](../assets/example-ollie.md) — all prompts use
this same story (Ollie, the pond, the basket) so examples stay consistent
across agents.

```
# Scenes
target_seconds: 224
scene_budget: 70

## Scene s1 — The Idea
scene_id: s1
target_seconds: 45
cast: [char_01]
characters_present: [char_01]
location_id: loc_01
objects: [obj_01, obj_02]
beats: [1, 2, 3]
style_target: high-fidelity stylized 3D CGI animation with tactile physical shaders and subsurface scattering
acting_beat: proud stillness → startled lurch → wide-eyed wonder
layout_strategy: boulder and basket foreground-right, pond opening midground-left, eye path follows the basket's fall into the water
visual_motif: round openings — basket mouth, cylinder rim, pond surface — each a portal that grows in meaning
sound_world: meadow birds, gentle water lap, whimsical acoustic strings
beat: A spilled basket reveals an underwater world to a young inventor.

## Scene s2 — The Underwater World
scene_id: s2
target_seconds: 100
cast: [char_01, char_03]
characters_present: [char_01, char_03]
location_id: loc_02
objects: [obj_02, obj_03]
beats: [6, 7]
style_target: high-fidelity stylized 3D CGI animation, bioluminescent aquamarine palette
acting_beat: cautious weightlessness → exuberant play → frozen awe
layout_strategy: mossy terraces recede in depth planes, Ollie small against cathedral light beams, eye path drifts upward with the bubbles
visual_motif: glowing round forms — snail blooms, lily pads, bubbles — echoing s1's portal motif underwater
sound_world: crystalline underwater hum, bubble streams, soaring orchestral theme
beat: Ollie explores a glowing alien paradise that slowly reveals its scale.
```

- Scene ids are `s1`, `s2`, … (sequential).
- Every scene block MUST have these keys: `scene_id`, `target_seconds`, `cast`,
  `characters_present`, `location_id`, `objects`, `beats`, `style_target`,
  `acting_beat`, `layout_strategy`, `visual_motif`, `sound_world`, `beat`.
- `objects` is a list of object ids from `developed_story.md`'s `## Objects`
  section that appear in this scene. Use `[]` if no named objects. Only list
  hero props / key objects — background set dressing is described in the
  storyboard, not here.
- `beats` is a list of beat numbers from `beat_board.md` that this scene covers.
  Each beat belongs to exactly one scene — no splitting a beat across scenes.
  The validator cross-checks beat coverage when `beat_board.md` exists.
- Use `## Scene <id> — <title>` headers (em-dash) — the parser keys off `## Scene `.

## Validate

```
python3 scripts/validate.py <run_dir>/scenes.md --schema scenes --target-seconds <N> --run-dir <run_dir>
```
Read `<run_dir>/scenes.md.validation.json`; on `ok:false`, fix the listed errors and
re-run. The validator cross-checks `beats:` against `beat_board.md` when it exists
in the run dir. Do not proceed to Agent 3 until scenes pass.