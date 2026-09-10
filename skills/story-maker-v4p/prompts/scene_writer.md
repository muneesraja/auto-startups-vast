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

## Rules

- **One location per scene.** A scene must not jump between locations — that is a
  cut, i.e. a new scene. Reuse `location_id`s from `developed_story.md` verbatim.
- **Stable cast ids.** Use the exact `char_NN` ids from Agent 1's `## Characters`.
  Never invent new ids here.
- **`cast` vs `characters_present`.** `cast` = every named hero who appears anywhere
  in the scene (drives which character sheets get built). `characters_present` =
  the heroes on screen in the scene's main beat (may equal cast). Both are
  `[cid, ...]` lists.
- **Target per scene.** Each scene's `target_seconds` must be an integer in the
  ~60-80s band. The sum of all scene `target_seconds` must be within 15% of the run
  target (the validator enforces this — pick per-scene budgets that sum to target).
- **Beat line.** One concise sentence naming the scene's central visible action.
- **Anti-sameness inherited.** Adjacent scenes must differ in location, lead focus,
  tone, or pace (Agent 1 already ensured this; preserve it).

## Output format (load-bearing — the validator parses this exactly)

```
# Scenes
target_seconds: <run total>
scene_budget: 70

## Scene s1 — <title>
scene_id: s1
target_seconds: <int>
cast: [char_01, char_02]
characters_present: [char_01, char_02]
location_id: loc_forest
objects: [obj_01, obj_02]
beats: [1, 2, 3]
beat: <one line summarizing the scene's central action>

## Scene s2 — <title>
scene_id: s2
...
```

- Scene ids are `s1`, `s2`, … (sequential).
- Every scene block MUST have all seven keys: `scene_id`, `target_seconds`, `cast`,
  `characters_present`, `location_id`, `objects`, `beats`, `beat`.
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