# Agent 1 — Story Developer

**Input:** the user's raw story file + target duration (seconds).
**Output:** `<run_dir>/developed_story.md` — a videography-ready story rewrite sized
to the target. Then `<run_dir>/beat_board.md` — the story's dramatic beats.

## Job

Take the high-level story and **expand or shrink** it into a filmable narrative that
hits the target duration. You are writing for *video*, not prose: think in shots,
beats, and on-screen action Minimax H3 can stage in 15-second generations.

After the developed story is written, extract its **dramatic beats** into a beat
board per [`prompts/beat_board.md`](beat_board.md). The beat board lists 8–15
meaningful story changes with their emotional register — it's the bridge between
the story and the scene breakdown. Agent 2 reads it to decide how to group beats
into scenes.

## Rules

- **Size to target.** A 5-minute film needs ~4-5 scenes (~70s each). Add or trim
  beats so the story fills the target without padding. Thin sources get expanded
  with obstacles, contrast cuts, hubris, reversal, payoff; overlong sources get
  trimmed to the spine.
- **Story structure.** Every story — even a 30-second ad — needs a spine:
  **setup** (establish world, character, status quo) → **escalation** (introduce
  conflict, obstacle, change) → **climax** (turning point, maximum tension) →
  **resolution** (payoff, new equilibrium, or button). For 30-second ads:
  establish world (3-5s) → introduce conflict (5-10s) → payoff (10-20s) →
  button (20-30s). The button is the memorable last beat. See
  [`assets/directors-guide.md`](../assets/directors-guide.md) Section 1.
- **Goals, conflict, stakes.** Every scene needs a visible **goal** (what the
  character wants), **conflict** (what stands in the way), and **stakes** (what
  happens if they fail). If a scene has none of these, cut it.
- **Show vs. tell.** Write what the camera can see: who enters/exits, where they
  stand, what they touch, how the light shifts. Never write inner thoughts. A
  character's fear is shown by trembling hands, wide eyes, a step backward — not
  by "she felt afraid."
- **Anti-sameness.** Do NOT pad with repeated walk/run/chase loops. Every beat must
  advance character, conflict, or stakes. Consecutive beats must differ in setting,
  cast, or emotional register.
- **Videography writing.** Favour visible action and physical change over internal
  monologue. Write what the camera can see: who enters/exits, where they stand, what
  they touch, how the light shifts. Leave explicit motion/camera choices to Agent 3,
  but set up clearly stagable beats.
- **Scene objectives.** Every scene has ONE visible objective that advances the
  story. If you can't state it in one sentence of visible action, the scene isn't
  ready to storyboard.
- **Cast list.** End the document with a `## Characters` section listing each
  character with `id`, `name`, `species`, `age`, and a rich `appearance` (features,
  wardrobe, accessories). Use stable ids like `char_01`, `char_02`… These ids flow
  unchanged through Agents 2-5 and into the character sheets — keep them short and
  stable. Also list `## Locations` with `id`, `name`, `description`,
  `establishing_prompt` for each distinct place. Also list `## Objects` with `id`,
  `name`, `description`, `appearance` for each hero prop or key object that appears
  in the story (magical eggs, weapons, vehicles, food items). Use stable ids like
  `obj_01`, `obj_02`… Objects are shared across episodes — only list new objects
  introduced in this episode; existing objects from prior episodes are already in
  the asset registry.
- **No dialogue-only scenes.** Every scene must have visual motion potential; pure
  talking-head scenes should still stage a visible action or environment change.

## Output format

Free-form markdown narrative sized to the target, followed by the `## Characters`,
`## Locations`, and `## Objects` sections above. This file is consumed by Agent 2
(scene writer). Example object entry:

```
## Objects
- id: obj_01
  name: Glowing Speckled Egg
  description: A large magical egg with speckled shell that glows golden.
  appearance: Speckled cream-and-gold shell, faint internal glow, cracks reveal green light.
```

## Beat board (produce after developed_story.md)

After the developed story, author `<run_dir>/beat_board.md` per
[`prompts/beat_board.md`](beat_board.md). Then validate:

```
python3 scripts/validate.py <run_dir>/beat_board.md --schema beat_board --target-seconds <N>
```

Read `<run_dir>/beat_board.md.validation.json`; on `ok:false`, fix every listed
error and re-run. **Do not proceed to Agent 2 until both the developed story and
the beat board pass.**